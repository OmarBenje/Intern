"""Prioritise public ATS leads using already published European internships."""

import hashlib
import re
from collections import Counter
from urllib.parse import urlsplit, urlunsplit

from django.utils import timezone

from jobboard.api.catalogue import open_offers
from jobboard.integrations.greenhouse_catalogue import CatalogueImportError
from jobboard.models import (
    AtsProbe,
    DiscoveryQuery,
    DiscoveryResult,
    SourceBoard,
)
from jobboard.services.ats_registry import PROVIDERS, read_inventory
from jobboard.services.engine_collection import parse_source_url, register_source
from jobboard.services.engine_filters import fresh_sources
from jobboard.services.engine_quality import EUROPE_COUNTRIES


def canonical_board(url):
    parts = urlsplit(url)
    # Do not turn an unsafe input into an apparently safe candidate.
    if (
        parts.scheme != "https"
        or parts.username
        or parts.password
        or parts.port not in (None, 443)
    ):
        raise CatalogueImportError("unsupported_source_url")
    path = parts.path
    if parts.hostname in {
        "boards.greenhouse.io",
        "job-boards.greenhouse.io",
        "jobs.lever.co",
        "jobs.eu.lever.co",
        "jobs.ashbyhq.com",
    }:
        path = "/" + path.strip("/").split("/")[0]
    if parts.hostname and parts.hostname.endswith(".teamtailor.com"):
        path = ""
    return parse_source_url(urlunsplit((parts.scheme, parts.netloc, path, "", "")))


def discover_from_offers(limit=50, use_registry=False, prioritize=False):
    if not 1 <= limit <= 100:
        raise ValueError("limit must be 1..100")
    query, _ = DiscoveryQuery.objects.get_or_create(
        provider="offer_ats_links",
        country="",
        language="en",
        domain="all",
        term="europe-internships",
        defaults={"enabled": False},
    )
    report = {
        "enrolled": [],
        "known_boards": 0,
        "already_queued": 0,
        "registry_errors": [],
        "started_at": timezone.now().isoformat(),
    }
    country_counts = Counter(
        country
        for codes in open_offers().values_list("enrichment__country_codes", flat=True)
        for country in set(codes or []) & EUROPE_COUNTRIES
    )
    report["country_counts_before"] = dict(sorted(country_counts.items()))
    report["prioritized"] = prioritize
    leads = []
    enrolled_employers = set()
    known = {
        (b.provider, b.instance, b.board_key.casefold())
        for b in SourceBoard.objects.all()
    }
    seen = set()
    sources = list(
        fresh_sources()
        .filter(offer__in=open_offers())
        .select_related("offer__company", "offer__enrichment")
        .order_by("pk")[:20000]
    )

    def priority(source):
        countries = set(source.offer.enrichment.country_codes) & EUROPE_COUNTRIES
        return min((country_counts[c] for c in countries), default=10**9)

    if prioritize:
        sources.sort(key=lambda source: (priority(source), source.pk))
    employers = {}
    for source in sources:
        name = source.offer.company.name.strip()
        # Exact names only. No fuzzy matching, no manufactured career URLs.
        employers.setdefault(name.casefold(), source)

    def accept(url, source, method, registry=None):
        if prioritize:
            leads.append((url, source, method, registry))
        else:
            admit(url, source, method, registry)

    def admit(url, source, method, registry=None):
        if len(report["enrolled"]) >= limit:
            return
        try:
            parsed = canonical_board(url)
        except (ValueError, CatalogueImportError):
            return
        identity = (
            parsed["provider"],
            parsed["instance"],
            parsed["board_key"].casefold(),
        )
        if identity in seen:
            return
        seen.add(identity)
        if identity in known:
            report["known_boards"] += 1
            return
        company = source.offer.company.name
        if prioritize and company.casefold() in enrolled_employers:
            return
        candidate = register_source(parsed["canonical"], company, enable=False)
        # Preserve existing failed/active probes and their rate limits.
        probe, created = AtsProbe.objects.get_or_create(candidate=candidate)
        evidence = {
            "method": method,
            "offer_id": source.offer_id,
            "source_id": source.pk,
            "origin_url": source.origin_url,
            "observed_url": url,
            "registry": registry,
            "seed_countries": sorted(
                set(source.offer.enrichment.country_codes) & EUROPE_COUNTRIES
            ),
            "priority_country_count": priority(source),
            "identity_note": "Name matches are leads, not proof of employer identity.",
        }
        DiscoveryResult.objects.update_or_create(
            query=query,
            external_id=hashlib.sha256(candidate.url.encode()).hexdigest(),
            defaults={
                "source_url": candidate.url,
                "company_name": company,
                "candidate": candidate,
                "payload": evidence,
                "attribution": source.origin_url,
                "status": candidate.status,
                "last_seen_at": timezone.now(),
            },
        )
        if created:
            enrolled_employers.add(company.casefold())
            report["enrolled"].append(
                {
                    "probe_id": probe.pk,
                    "candidate_id": candidate.pk,
                    "company": company,
                    "url": candidate.url,
                    **evidence,
                }
            )
        else:
            report["already_queued"] += 1

    for source in sources:
        raw = source.raw_payload
        urls = [source.apply_url, source.origin_url, raw.get("direct_url", "")]
        # Description hyperlinks are only leads; fetching uses fixed ATS adapters.
        urls += re.findall(r'https://[^\s<>"\)\]]+', raw.get("description", "") or "")
        for url in urls:
            if isinstance(url, str):
                accept(url, source, "posting_link")
        if len(report["enrolled"]) >= limit:
            break
    if use_registry and len(report["enrolled"]) < limit:
        for provider in PROVIDERS:
            try:
                origin, sha, rows = read_inventory(provider)
            except CatalogueImportError as exc:
                report["registry_errors"].append(
                    {"provider": provider, "code": exc.code}
                )
                continue
            for row in rows:
                source = employers.get((row.get("name") or "").strip().casefold())
                if source:
                    accept(
                        row.get("url", ""),
                        source,
                        "exact_registry_name",
                        {"url": origin, "sha256": sha},
                    )
                if len(report["enrolled"]) >= limit:
                    break
            if len(report["enrolled"]) >= limit:
                break
    if prioritize:
        # Rank all providers together, so inventory ordering cannot consume the budget.
        leads.sort(
            key=lambda lead: (
                priority(lead[1]),
                lead[2] != "posting_link",
                lead[1].pk,
                lead[0],
            )
        )
        for args in leads:
            admit(*args)
            if len(report["enrolled"]) >= limit:
                break
    report.update(
        scanned_sources=len(sources),
        qualifying_employers=len(employers),
        target=limit,
        shortfall=limit - len(report["enrolled"]),
        finished_at=timezone.now().isoformat(),
    )
    return report
