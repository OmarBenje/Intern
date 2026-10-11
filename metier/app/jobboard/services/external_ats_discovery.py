"""Admit operator-reviewed public search leads independently of existing offers."""

import hashlib
from collections import Counter
from datetime import date, timedelta

from django.db import transaction
from django.utils import timezone

from jobboard.api.catalogue import open_offers
from jobboard.models import (
    AtsProbe,
    Company,
    DiscoveryQuery,
    DiscoveryResult,
    SourceBoard,
    SourceCandidate,
)
from jobboard.services.engine_collection import register_source
from jobboard.services.engine_quality import EUROPE_COUNTRIES
from jobboard.services.offer_source_discovery import canonical_board


def identity(parsed):
    return parsed["provider"], parsed["instance"], parsed["board_key"].casefold()


def validate_leads(leads):
    if not isinstance(leads, list) or not 1 <= len(leads) <= 100:
        raise ValueError("Expected 1..100 reviewed leads")
    validated = []
    for lead in leads:
        if not isinstance(lead, dict):
            raise TypeError("Invalid lead")
        for field in (
            "company",
            "country",
            "url",
            "evidence_url",
            "title",
            "excerpt",
            "reviewed_at",
        ):
            if not isinstance(lead.get(field), str) or not lead[field].strip():
                raise ValueError(f"Missing {field}")
        if len(lead["company"]) > 240 or any(
            len(lead[f]) > 2048 for f in ("url", "evidence_url", "title", "excerpt")
        ):
            raise ValueError("Lead field too long")
        reviewed = date.fromisoformat(lead["reviewed_at"])
        if (
            not timezone.localdate() - timedelta(days=7)
            <= reviewed
            <= timezone.localdate()
        ):
            raise ValueError("Evidence review must be within the last seven days")
        if lead["country"] not in EUROPE_COUNTRIES:
            raise ValueError("Expected European country")
        parsed = canonical_board(lead["url"])
        if identity(parsed) != identity(canonical_board(lead["evidence_url"])):
            raise ValueError("Evidence must belong to the same ATS portal")
        validated.append((lead, parsed))
    return validated


@transaction.atomic
def discover_external(leads, apply=False):
    validated = validate_leads(leads)
    counts = Counter(
        c
        for codes in open_offers().values_list("enrichment__country_codes", flat=True)
        for c in set(codes or []) & EUROPE_COUNTRIES
    )
    report = {
        "apply": apply,
        "country_counts_before": {
            code: counts[code] for code in sorted(EUROPE_COUNTRIES)
        },
        "started_at": timezone.now().isoformat(),
        "enrolled": [],
        "skipped": [],
    }
    known_companies = {
        n.strip().casefold() for n in Company.objects.values_list("name", flat=True)
    }
    known_boards = {
        (b.provider, b.instance, b.board_key.casefold())
        for b in SourceBoard.objects.all()
    }
    seen, employers = set(), set()
    for lead, parsed in sorted(
        validated,
        key=lambda item: (counts[item[0]["country"]], item[0]["company"].casefold()),
    ):
        key, name = identity(parsed), lead["company"].strip().casefold()
        candidates = SourceCandidate.objects.filter(
            provider=key[0], instance=key[1], board_key__iexact=key[2]
        )
        reason = None
        if key in seen or name in employers:
            reason = "duplicate_in_batch"
        elif key in known_boards:
            reason = "known_board"
        elif name in known_companies:
            reason = "known_employer"
        elif candidates.exclude(company_name__iexact=lead["company"].strip()).exists():
            reason = "conflicting_employer_identity"
        elif AtsProbe.objects.filter(candidate__in=candidates).exists():
            reason = "already_queued"
        seen.add(key)
        employers.add(name)
        if reason:
            report["skipped"].append(
                {
                    "company": lead["company"],
                    "url": parsed["canonical"],
                    "reason": reason,
                }
            )
            continue
        row = dict(lead, url=parsed["canonical"])
        if apply:
            candidate = candidates.first() or register_source(
                parsed["canonical"], lead["company"].strip(), enable=False
            )
            probe, created = AtsProbe.objects.get_or_create(candidate=candidate)
            if not created:
                report["skipped"].append(dict(row, reason="already_queued"))
                continue
            query, _ = DiscoveryQuery.objects.get_or_create(
                provider="external_ats_review",
                country=lead["country"],
                language="en",
                domain="all",
                term="reviewed-public-internships",
                defaults={"enabled": False},
            )
            DiscoveryResult.objects.create(
                query=query,
                external_id=hashlib.sha256(candidate.url.encode()).hexdigest(),
                source_url=candidate.url,
                company_name=lead["company"],
                candidate=candidate,
                payload=dict(lead, method="reviewed_public_search"),
                attribution=lead["evidence_url"],
                status=candidate.status,
                last_seen_at=timezone.now(),
            )
            row.update(probe_id=probe.pk, candidate_id=candidate.pk)
        report["enrolled"].append(row)
    report.update(
        input_count=len(leads),
        capacity=100,
        unused_capacity=100 - len(report["enrolled"]),
    )
    return report
