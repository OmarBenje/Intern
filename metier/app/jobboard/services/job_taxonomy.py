"""Deterministic, offline occupation classification and strict SQL facets."""

import hashlib
import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from django.db import transaction
from django.db.models import Exists, OuterRef, Q

SEED_PATH = Path(__file__).resolve().parent.parent / "data" / "job-taxonomy-v1.json"
SEED = json.loads(SEED_PATH.read_text())
VERSION = SEED["version"] + "-rules3"
DOMAIN_SLUGS = {d["slug"] for d in SEED["domains"]}
SUBDOMAINS = {
    s["slug"]: {**s, "domain": d["slug"]}
    for d in SEED["domains"]
    for s in d["subdomains"]
}
CLASSIFIED = ("classified", "broad")


def normalize(text):
    return re.sub(
        r"\s+",
        " ",
        "".join(
            c
            for c in unicodedata.normalize("NFKD", text.casefold())
            if not unicodedata.combining(c)
        ),
    ).strip()


@lru_cache(maxsize=1)
def patterns():
    aliases = {}
    for slug, data in SUBDOMAINS.items():
        for alias in data["aliases"]:
            if alias:
                aliases.setdefault(normalize(alias), []).append(slug)
    # Match the longest occupation phrase first in one pass over each text.
    expression = (
        r"(?<!\w)(?:"
        + "|".join(re.escape(a) for a in sorted(aliases, key=lambda a: (-len(a), a)))
        + r")(?!\w)"
    )
    return re.compile(expression), aliases


def candidates(text, field):
    normalized = normalize(text)
    expression, aliases = patterns()
    found = {}
    for match in expression.finditer(normalized):
        for slug in aliases[match.group()]:
            if slug not in found or found[slug]["specificity"] < len(match.group()):
                data = SUBDOMAINS[slug]
                found[slug] = {
                    "slug": slug,
                    "domain": data["domain"],
                    "generalist": data["generalist"],
                    "field": field,
                    "matched_term": match.group(),
                    "evidence_text": text[:1500],
                    "specificity": len(match.group()),
                    "start": match.start(),
                    "end": match.end(),
                }
    result = list(found.values())
    # A precise compound (accounts payable, product marketing) supersedes its
    # contained generic alias (accounting, product). Cross-domain unrelated
    # candidates remain ambiguous instead of winning by dictionary order.
    return [
        c
        for c in result
        if not any(
            c["matched_term"] != other["matched_term"]
            and c["matched_term"] in other["matched_term"]
            for other in result
        )
    ]


def classify(title, description=""):
    from .engine_quality import plain_text

    title = plain_text(title)
    hits = candidates(title, "offer.title")
    # Topic suffixes ("Full-stack Developer - Data Transformation") describe
    # the project rather than a second occupation. Keep a precise leading role.
    for segment in re.split(r"\s[-–—]\s", title):
        leading = candidates(segment, "offer.title")
        if any(not c["generalist"] for c in leading):
            hits = leading
            break
        if leading:
            break
    if any(c["slug"] == "event-management" for c in hits):
        hits = [c for c in hits if c["slug"] != "project-management"]
    if any(c["domain"] == "legal-compliance" for c in hits):
        hits = [c for c in hits if c["slug"] != "sales-customer-generalist"]
    if any(c["domain"] != "engineering" for c in hits):
        hits = [c for c in hits if c["slug"] != "engineering-generalist"]
    precise = [c for c in hits if not c["generalist"]]
    broad = [c for c in hits if c["generalist"]]
    if precise:
        broad = [c for c in broad if c["matched_term"] != "design"]
    if precise and {c["domain"] for c in broad} - {c["domain"] for c in precise}:
        return {
            "status": "needs_review",
            "primary": None,
            "secondary": [],
            "candidates": hits,
        }
    # Description fallback only reads explicit responsibility/task sentences.
    # A skills list or the employer's industry description is not a mission.
    if not precise:
        raw = re.sub(
            r"</(?:li|p|div|h[1-6])>|<br\s*/?>", "\n", description, flags=re.IGNORECASE
        )
        task_hits = []
        mission_section = False
        for sentence in re.split(r"[\n.!?]", raw)[:120]:
            sentence = plain_text(sentence)
            if re.search(
                r"\b(?:responsibilities|your role|your tasks|missions|aufgaben|what you will do)\b",
                sentence,
                re.IGNORECASE,
            ):
                mission_section = True
            elif re.search(
                r"\b(?:requirements|qualifications|benefits|about us|compétences|profil recherché|voraussetzungen)\b",
                sentence,
                re.IGNORECASE,
            ):
                mission_section = False
            if re.search(
                r"\b(?:develop|build|design|analyse|analyze|manage|conduct|support|implement|assess|maintain|développer|concevoir|analyser|gérer|réaliser|contribuer|entwickeln|analysieren)\b",
                sentence,
                re.IGNORECASE,
            ):
                task_hits.extend(
                    c
                    for c in candidates(sentence, "offer.description")
                    if not c["generalist"] and (broad or mission_section)
                )
        if not broad:
            # Unknown titles require corroboration in multiple responsibility
            # sentences, not a single incidental task in a long description.
            task_hits = [
                c
                for c in task_hits
                if len(
                    {h["evidence_text"] for h in task_hits if h["slug"] == c["slug"]}
                )
                >= 2
            ]
        task_hits = list({c["slug"]: c for c in task_hits}.values())
        # A broad title constrains fallback to the known family; avoids a single
        # incidental task turning Marketing Intern into a software internship.
        families = {c["domain"] for c in broad}
        if families:
            task_hits = [c for c in task_hits if c["domain"] in families]
        precise = task_hits
    if precise:
        precise = sorted(
            {c["slug"]: c for c in precise}.values(),
            key=lambda c: (c["start"], -c["specificity"], c["slug"]),
        )
        # Different explicit duties in a title with a conjunction support a
        # secondary association. Description conflicts require review.
        transverse = (
            len(precise) <= 2
            and all(c["field"] == "offer.title" for c in precise)
            and re.search(
                r"\s(?:and|et|und|&)\s|/",
                title[
                    min(c["start"] for c in precise) : max(c["end"] for c in precise)
                ],
                re.IGNORECASE,
            )
        )
        if len(precise) > 1 and not transverse:
            return {
                "status": "needs_review",
                "primary": None,
                "secondary": [],
                "candidates": precise,
            }
        return {
            "status": "classified",
            "primary": precise[0]["slug"],
            "secondary": [c["slug"] for c in precise[1:]],
            "candidates": precise,
        }
    families = {c["domain"] for c in broad}
    if len(families) == 1:
        return {
            "status": "broad",
            "primary": broad[0]["slug"],
            "secondary": [],
            "candidates": broad,
        }
    return {
        "status": "needs_review" if broad else "unclassified",
        "primary": None,
        "secondary": [],
        "candidates": broad,
    }


@transaction.atomic
def seed_taxonomy():
    from jobboard.models import JobDomain, JobSubdomain

    for data in SEED["domains"]:
        domain, _ = JobDomain.objects.update_or_create(
            slug=data["slug"], defaults={k: data[k] for k in ("name", "position")}
        )
        for sub in data["subdomains"]:
            JobSubdomain.objects.update_or_create(
                slug=sub["slug"],
                defaults={
                    "domain": domain,
                    **{
                        k: sub[k] for k in ("name", "aliases", "position", "generalist")
                    },
                },
            )


def input_hash(offer):
    return hashlib.sha256(
        json.dumps([offer.title, offer.description], ensure_ascii=False).encode()
    ).hexdigest()


@transaction.atomic
def assign_taxonomy(offer, *, vocabulary=None, revisions=()):
    from jobboard.models import JobSubdomain, Offer

    # Lock serializes a reclassification with imports and manual corrections.
    offer = Offer.objects.select_for_update().get(pk=offer.pk)
    digest = input_hash(offer)
    if offer.taxonomy_input_hash == digest and offer.taxonomy_version == VERSION:
        return offer.taxonomy_status
    if offer.taxonomy_manual:
        if offer.taxonomy_input_hash != digest:
            Offer.objects.filter(pk=offer.pk).update(taxonomy_status="needs_review")
        return (
            "needs_review"
            if offer.taxonomy_input_hash != digest
            else offer.taxonomy_status
        )
    classification = classify(offer.title, offer.description)
    provided_vocabulary = vocabulary is not None
    vocabulary = (
        vocabulary
        if vocabulary is not None
        else dict(JobSubdomain.objects.values_list("slug", "pk"))
    )
    for candidate in classification["candidates"]:
        for revision in revisions:
            if candidate["matched_term"] in normalize(
                json.dumps(revision.payload, ensure_ascii=False)
            ):
                candidate["source_revision_id"] = revision.pk
                break
    primary = vocabulary.get(classification["primary"])
    if classification["primary"] and primary is None:
        if provided_vocabulary:
            raise ValueError("Taxonomy vocabulary missing; apply migrations first.")
        # Reference data may have been flushed (e.g. a TransactionTestCase or
        # database restore). Imports rebuild it idempotently on first use.
        seed_taxonomy()
        vocabulary = dict(JobSubdomain.objects.values_list("slug", "pk"))
        primary = vocabulary[classification["primary"]]
    Offer.objects.filter(pk=offer.pk).update(
        job_subdomain_id=primary,
        taxonomy_status=classification["status"],
        taxonomy_version=VERSION,
        taxonomy_input_hash=digest,
        taxonomy_evidence={
            "method": "occupation-phrases",
            "candidates": classification["candidates"],
        },
    )
    offer.secondary_subdomains.set([vocabulary[s] for s in classification["secondary"]])
    return classification["status"]


def filter_taxonomy(queryset, criteria):
    domains, subs = criteria.get("domains", []), criteria.get("subdomains", [])
    if not domains and not subs:
        return queryset
    from jobboard.models import Offer

    secondary = Offer.secondary_subdomains.through.objects.filter(
        offer_id=OuterRef("pk")
    )
    condition = Q(job_subdomain__domain__slug__in=domains) | Q(
        job_subdomain__slug__in=subs
    )
    secondary = secondary.filter(
        Q(jobsubdomain__domain__slug__in=domains) | Q(jobsubdomain__slug__in=subs)
    )
    return (
        queryset.alias(taxonomy_secondary_match=Exists(secondary))
        .filter(
            taxonomy_status__in=CLASSIFIED,
        )
        .filter(condition | Q(taxonomy_secondary_match=True))
    )


def validate_selection(domains, subdomains):
    if set(domains) - DOMAIN_SLUGS or set(subdomains) - SUBDOMAINS.keys():
        raise ValueError("Unknown domain or subdomain.")
    # All choices in the job-function facet are OR alternatives, even across
    # parents. Parent + its child is redundant, not a contradictory AND filter.
    return list(dict.fromkeys(domains)), [
        s for s in dict.fromkeys(subdomains) if SUBDOMAINS[s]["domain"] not in domains
    ]
