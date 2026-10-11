"""Conservative content matching; summary/full-text pairs require explicit review."""

import re
import unicodedata
from collections import defaultdict
from difflib import SequenceMatcher

from jobboard.models import OfferMergeDecision
from jobboard.services.targeted_merges import compatible, fingerprint


def words(value):
    value = unicodedata.normalize("NFKD", value.casefold())
    return " ".join(
        re.findall(r"\w+", "".join(c for c in value if not unicodedata.combining(c)))
    )


def requisitions_conflict(a, b):
    refs = {
        s.external_requisition_id
        for o in (a, b)
        for s in o.sources.all()
        if s.external_requisition_id
    }
    if len(refs) > 1:
        return True

    # Workday exposes a requisition, not a publication UUID, as external_id.
    def workday_refs(offer):
        result = defaultdict(set)
        for source in offer.sources.all():
            if source.board.provider == "workday":
                result[source.board_id].add(source.external_id)
        return result

    left, right = workday_refs(a), workday_refs(b)
    return any(left[key] != right[key] for key in left.keys() & right.keys())


def matches(a, b):
    if a.company_id != b.company_id or not compatible(a, b):
        return False
    if requisitions_conflict(a, b):
        return False
    left, right = words(a.description), words(b.description)
    if min(len(left.split()), len(right.split())) < 80:
        return False
    # Only nearly identical full documents. Never compare a summary to a full job.
    if min(len(left), len(right)) / max(len(left), len(right)) < 0.95:
        return False
    # Numbers can distinguish dates, duration, salary or seniority.
    if re.findall(r"\d+", left) != re.findall(r"\d+", right):
        return False
    return (
        left == right
        or SequenceMatcher(None, left, right, autojunk=False).ratio() >= 0.98
    )


def decision_for(a, b, *, reviewed=False):
    return OfferMergeDecision.objects.get_or_create(
        canonical_offer=a,
        duplicate_offer=b,
        defaults={
            "evidence": {
                "method": "reviewed_content_duplicate"
                if reviewed
                else "content_duplicate",
                "canonical_fingerprint": fingerprint(a),
                "duplicate_fingerprint": fingerprint(b),
            }
        },
    )[0]


def reconcile_duplicates(*, company_id=None, limit=100):
    from jobboard.api.catalogue import open_offers
    from jobboard.services.engine_merges import merge
    from jobboard.services.targeted_merges import ATS

    query = (
        open_offers()
        .select_related("company")
        .prefetch_related("locations", "sources__board")
    )
    if company_id is not None:
        query = query.filter(company_id=company_id)
    groups = defaultdict(list)
    for offer in query.iterator(chunk_size=200):
        groups[(offer.company_id, words(offer.title))].append(offer)
    merged, skipped = [], []
    for group in groups.values():
        group.sort(
            key=lambda o: (
                not any(s.board.provider in ATS for s in o.sources.all()),
                -len(o.description),
                o.pk,
            )
        )
        survivors = []
        for offer in group:
            for canonical in survivors:
                if not matches(canonical, offer):
                    continue
                decision = decision_for(canonical, offer)
                if decision.status != "candidate":
                    continue  # An operator reversal must not be silently overridden.
                try:
                    merge(decision.pk)
                except ValueError as exc:
                    skipped.append({"offer": offer.pk, "reason": str(exc)})
                    continue
                merged.append(offer.pk)
                # Reload sources before comparing another member of the group.
                canonical._prefetched_objects_cache.pop("sources", None)
                break
            else:
                survivors.append(offer)
            if len(merged) >= limit:
                return {"merged": merged, "skipped": skipped}
    return {"merged": merged, "skipped": skipped}
