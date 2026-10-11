"""Bounded admission of public feed evidence into the existing ATS probe queue."""

import hashlib
import re
import unicodedata
from collections import Counter
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from jobboard.integrations.greenhouse_catalogue import CatalogueImportError
from jobboard.models import (
    AtsProbe,
    Company,
    DiscoveryQuery,
    DiscoveryResult,
    SourceBoard,
    SourceCandidate,
)
from jobboard.services.ats_registry import REVISION
from jobboard.services.engine_collection import register_source
from jobboard.services.engine_quality import INTERN
from jobboard.services.offer_source_discovery import canonical_board

FEEDS = (
    "arbeitnow",
    "jobsearch_se",
    "linkedin_public",
    "wttj",
    "eures",
    "jobtech",
    "bundesagentur",
    "nav",
    "jobspy_linkedin",
    "jobspy_indeed",
)
DAILY_LIMIT = 50
SCAN_LIMIT = 500
PORTAL_HINT = r"ashbyhq|greenhouse|lever\.co|smartrecruiters|personio|recruitee|teamtailor|workable|myworkdayjobs|eightfold|careers\.microsoft|icims|taleo|successfactors"


def name_key(value):
    return "".join(
        c
        for c in unicodedata.normalize("NFKD", value).casefold()
        if c.isalnum() and not unicodedata.combining(c)
    )


def portal_evidence(result):
    raw = result.payload if isinstance(result.payload, dict) else {}
    registry = result.query.provider == "ats_registry"
    if registry:
        expected = f"https://raw.githubusercontent.com/kalil0321/ats-scrapers/{REVISION}/ats-companies/"
        if raw.get("revision") != REVISION or not str(
            raw.get("registry", "")
        ).startswith(expected):
            return None, "unverified_registry_revision"
    title = (
        "Portail public à vérifier"
        if registry
        else (raw.get("title") or raw.get("headline") or raw.get("name") or "")
    )
    if not registry and (
        not isinstance(title, str) or not re.search(INTERN, title, re.IGNORECASE)
    ):
        return None, "no_internship_title"
    company = result.company_name.strip()
    if not company or len(company) > 240:
        return None, "missing_employer"
    urls = [result.source_url]
    for field in (
        "apply_url",
        "application_url",
        "direct_url",
        "job_url_direct",
        "job_url",
        "url",
    ):
        urls.append(raw.get(field))
    application = raw.get("application_details")
    if isinstance(application, dict):
        urls.append(application.get("url"))
    # A previously resolved candidate is usable only when the public URL itself
    # corroborates the same portal. No blind admission of registry name matches.
    choices = {}
    for url in urls:
        if not isinstance(url, str) or len(url) > 2048:
            continue
        try:
            parsed = canonical_board(url)
        except (ValueError, CatalogueImportError):
            continue
        identity = (
            parsed["provider"],
            parsed["instance"],
            parsed["board_key"].casefold(),
        )
        choices[identity] = (parsed, url)
    if len(choices) != 1:
        return None, "ambiguous_portals" if choices else "no_supported_direct_link"
    parsed, evidence_url = next(iter(choices.values()))
    if name_key(company) != name_key(parsed["board_key"]):
        return None, "employer_identity_needs_review"
    if any(
        word in parsed["canonical"].casefold()
        for word in ("/internal", "/employee", "/contingent")
    ):
        return None, "non_public_board"
    return (parsed, evidence_url, title), ""


@transaction.atomic
def run_automatic_discovery():
    now = timezone.now()
    query, _ = DiscoveryQuery.objects.get_or_create(
        provider="auto_employer_discovery",
        country="",
        language="en",
        domain="all",
        term="public-feed-portals",
        defaults={"enabled": True},
    )
    query = DiscoveryQuery.objects.select_for_update().get(pk=query.pk)
    now = timezone.now()
    if not query.enabled or query.next_run_at > now:
        return {"state": "not_due", "enrolled": []}
    today = now.date().isoformat()
    try:
        day, admitted, cursor = query.cursor.split("|")
        admitted, cursor = int(admitted), int(cursor)
        if admitted < 0 or cursor < 0:
            raise ValueError
    except ValueError:
        day, admitted, cursor = today, 0, 0
    if day != today:
        admitted, cursor = 0, 0
    if admitted >= DAILY_LIMIT:
        query.next_run_at = (now + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        query.save(update_fields=["next_run_at"])
        return {"state": "daily_limit", "enrolled": []}
    # Skip records without a structured ATS-link hint before spending the scan
    # budget. This is only a prefilter; canonical_board remains authoritative.
    portal_filter = Q(source_url__iregex=PORTAL_HINT)
    for field in (
        "apply_url",
        "application_url",
        "direct_url",
        "job_url_direct",
        "job_url",
        "url",
        "application_details__url",
    ):
        portal_filter |= Q(**{f"payload__{field}__iregex": PORTAL_HINT})
    rows = list(
        DiscoveryResult.objects.filter(
            Q(query__provider__in=FEEDS, query__enabled=True)
            | Q(query__provider="ats_registry"),
            pk__gt=cursor,
        )
        .filter(
            Q(query__provider="ats_registry")
            | Q(last_seen_at__gte=now - timedelta(days=7))
        )
        .filter(
            Q(query__provider="ats_registry")
            | Q(payload__title__iregex=r"intern|stage|praktik|tiroc|pasant|est.gio")
            | Q(payload__headline__iregex=r"intern|stage|praktik|tiroc|pasant|est.gio")
            | Q(payload__name__iregex=r"intern|stage|praktik|tiroc|pasant|est.gio")
        )
        .filter(portal_filter)
        .select_related("query")
        .order_by("pk")[:SCAN_LIMIT]
    )
    counts, enrolled, reviews = Counter(), [], []
    for result in rows:
        cursor = result.pk
        evidence, reason = portal_evidence(result)
        if evidence:
            parsed, url, title = evidence
            candidates = SourceCandidate.objects.filter(
                provider=parsed["provider"],
                instance=parsed["instance"],
                board_key__iexact=parsed["board_key"],
            )
            if SourceBoard.objects.filter(
                provider=parsed["provider"],
                instance=parsed["instance"],
                board_key__iexact=parsed["board_key"],
            ).exists():
                reason = "known_board"
            elif Company.objects.filter(
                name__iexact=result.company_name.strip()
            ).exists():
                reason = "known_employer"
            elif candidates.exclude(
                company_name__iexact=result.company_name.strip()
            ).exists():
                reason = "conflicting_employer_identity"
            elif candidates.exclude(status="candidate").exists():
                reason = "candidate_not_eligible"
            elif AtsProbe.objects.filter(candidate__in=candidates).exists():
                reason = "already_queued"
            else:
                candidate = candidates.first() or register_source(
                    parsed["canonical"], result.company_name.strip(), enable=False
                )
                probe, created = AtsProbe.objects.get_or_create(candidate=candidate)
                if created:
                    DiscoveryResult.objects.update_or_create(
                        query=query,
                        external_id=hashlib.sha256(candidate.url.encode()).hexdigest(),
                        defaults={
                            "candidate": candidate,
                            "company_name": candidate.company_name,
                            "source_url": candidate.url,
                            "attribution": url,
                            "status": "queued",
                            "payload": {
                                "method": "public_feed_exact_portal_name_v1",
                                "registry_revision": REVISION
                                if result.query.provider == "ats_registry"
                                else None,
                                "evidence_result_id": result.pk,
                                "evidence_provider": result.query.provider,
                                "evidence_url": url,
                                "title": title,
                                "country_hint": result.query.country,
                                "observed_at": result.last_seen_at.isoformat(),
                            },
                            "last_seen_at": now,
                        },
                    )
                    admitted += 1
                    enrolled.append(
                        {
                            "probe_id": probe.pk,
                            "company": candidate.company_name,
                            "url": candidate.url,
                        }
                    )
                    reason = "enrolled"
                else:
                    reason = "already_queued"
        counts[reason] += 1
        if len(reviews) < 20 and reason in {
            "employer_identity_needs_review",
            "ambiguous_portals",
            "conflicting_employer_identity",
        }:
            reviews.append({"result_id": result.pk, "reason": reason})
        if admitted >= DAILY_LIMIT:
            break
    query.cursor = f"{today}|{admitted}|{cursor}"
    query.last_success_at = now
    query.result_count = query.results.count()
    query.next_run_at = (
        now + timedelta(minutes=5)
        if len(rows) == SCAN_LIMIT and admitted < DAILY_LIMIT
        else (now + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
    )
    query.save(
        update_fields=["cursor", "last_success_at", "result_count", "next_run_at"]
    )
    return {
        "state": "completed",
        "scanned": sum(counts.values()),
        "counts": dict(counts),
        "enrolled": enrolled,
        "review_samples": reviews,
        "admitted_today": admitted,
        "next_run_at": query.next_run_at.isoformat(),
    }
