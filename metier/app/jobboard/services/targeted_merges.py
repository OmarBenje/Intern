"""Cross-feed merge proposals require a job-specific link, never title similarity alone."""

import hashlib
import json
import re
from collections import defaultdict
from urllib.parse import parse_qs, urlsplit

from jobboard.api.catalogue import open_offers
from jobboard.models import OfferMergeDecision
from jobboard.services.engine_filters import fresh_sources
from jobboard.services.engine_merges import canonical_job_url

ATS = {
    "greenhouse",
    "lever",
    "ashby",
    "workday",
    "smartrecruiters",
    "personio",
    "recruitee",
    "teamtailor",
    "workable",
}


def normalized(value):
    return " ".join(value.casefold().split())


def job_link(value):
    link = canonical_job_url(value)
    if not link:
        return None
    url = urlsplit(link)
    # Keep the complete query: two gh_jid values must never collapse together.
    if re.fullmatch(r"\d+", parse_qs(url.query).get("gh_jid", [""])[0]):
        return link
    if re.search(r"/(?:jobs?|j)/\d+(?:[-/]|$)", url.path):
        return link
    if re.search(
        r"/[0-9a-f]{8}-[0-9a-f-]{27,36}(?:/application)?$", url.path, re.IGNORECASE
    ):
        return link.removesuffix("/application")
    if (
        url.hostname
        and url.hostname.endswith(".myworkdayjobs.com")
        and re.search(r"/job/.+_[A-Za-z0-9-]+$", url.path)
    ):
        return link
    return None


def links(offer, fresh=None):
    return {
        link
        for s in offer.sources.all()
        if fresh is None or s.pk in fresh
        for u in (
            s.origin_url,
            s.apply_url,
            s.raw_payload.get("direct_url", ""),
            *getattr(offer, "_resolved_source_links", {}).get(s.pk, []),
        )
        if (link := job_link(u))
    }


def location_keys(offer):
    # Remove an explicit country suffix only when the structured country agrees.
    result = set()
    for location in offer.locations.all():
        name = normalized(location.name)
        code = (location.country_code or "").casefold()
        if code and name.endswith(", " + code):
            name = name[: -(len(code) + 2)]
        result.add((name, code))
    return result


def compatible(a, b):
    return (
        normalized(a.company.name) == normalized(b.company.name)
        and normalized(a.title) == normalized(b.title)
        and bool(a.locations.all())
        and location_keys(a) == location_keys(b)
        and not (a.expires_at and b.expires_at and a.expires_at != b.expires_at)
        and not (
            a.work_mode != "unknown"
            and b.work_mode != "unknown"
            and a.work_mode != b.work_mode
        )
        and not (
            a.contract_type != "unknown"
            and b.contract_type != "unknown"
            and a.contract_type != b.contract_type
        )
    )


def fingerprint(offer):
    value = [
        offer.company_id,
        offer.company.name,
        offer.title,
        offer.description,
        offer.contract_type,
        offer.work_mode,
        str(offer.expires_at),
        sorted(
            (location.pk, location.name, location.country_code or "")
            for location in offer.locations.all()
        ),
        sorted(
            (
                s.pk,
                s.board_id,
                s.origin_url,
                s.apply_url,
                s.external_requisition_id or "",
                s.content_hash,
                tuple(
                    sorted(getattr(offer, "_resolved_source_links", {}).get(s.pk, []))
                ),
            )
            for s in offer.sources.all()
        ),
    ]
    return hashlib.sha256(json.dumps(value, ensure_ascii=False).encode()).hexdigest()


def validate_pair(a, b):
    from jobboard.services.job_link_evidence import attach_evidence

    attach_evidence([a, b])
    source_ids = [s.pk for s in a.sources.all()] + [s.pk for s in b.sources.all()]
    fresh = set(fresh_sources().filter(pk__in=source_ids).values_list("pk", flat=True))
    if (
        not a.description.strip()
        or not compatible(a, b)
        or not links(a, fresh) & links(b, fresh)
    ):
        return False
    sources = list(a.sources.all()) + list(b.sources.all())
    refs = {s.external_requisition_id for s in sources if s.external_requisition_id}
    return (
        len(refs) <= 1
        and all(
            {
                job_link(s.origin_url),
                job_link(s.apply_url),
                job_link(s.raw_payload.get("direct_url", "")),
                *(
                    job_link(u)
                    for u in getattr(b, "_resolved_source_links", {}).get(s.pk, [])
                ),
            }
            & links(a)
            for s in b.sources.all()
        )
        and any(s.board.provider in ATS for s in a.sources.all())
    )


def propose_targeted(ids):
    ids = set(ids)
    visible = list(
        open_offers()
        .select_related("company")
        .prefetch_related("locations", "sources__board")
        .order_by("pk")
    )
    from jobboard.services.job_link_evidence import attach_evidence

    attach_evidence(visible)
    fresh = set(fresh_sources().values_list("pk", flat=True))
    index = defaultdict(list)
    for offer in visible:
        for link in links(offer, fresh):
            if any(s.pk in fresh for s in offer.sources.all()):
                index[link].append(offer)
    decisions = []
    ambiguous = []
    pairs = set()
    for group in index.values():
        for left in group:
            for right in group:
                a, b = left, right
                key = tuple(sorted((a.pk, b.pk)))
                if a.pk == b.pk or not ids.intersection(key) or key in pairs:
                    continue
                pairs.add(key)
                # Prefer the employer ATS record. Never replace it with a summary.
                if not any(s.board.provider in ATS for s in a.sources.all()):
                    a, b = b, a
                if not validate_pair(a, b):
                    ambiguous.append(list(key))
                    continue
                decision, _ = OfferMergeDecision.objects.get_or_create(
                    canonical_offer=a,
                    duplicate_offer=b,
                    defaults={
                        "evidence": {
                            "method": "verified_job_link",
                            "link": min(links(a) & links(b)),
                            "canonical_fingerprint": fingerprint(a),
                            "duplicate_fingerprint": fingerprint(b),
                        }
                    },
                )
                decisions.append(decision.pk)
    # Weak matches are reported separately, never queued for automatic merging.
    titles = defaultdict(list)
    for offer in visible:
        titles[(normalized(offer.company.name), normalized(offer.title))].append(
            offer.pk
        )
    weak = [
        group for group in titles.values() if len(group) > 1 and ids.intersection(group)
    ]
    return {
        "decision_ids": sorted(set(decisions)),
        "conflicting_link_pairs": ambiguous,
        "title_only_groups": weak,
        "target_visible": sum(o.pk in ids for o in visible),
    }
