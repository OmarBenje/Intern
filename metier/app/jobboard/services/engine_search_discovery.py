"""Durable, leased feed discovery. Feed matches are leads, never publishable offers."""

import time
import uuid
from datetime import timedelta
from urllib.parse import urljoin, urlsplit, urlunsplit

from django.db import transaction
from django.db.models import Case, F, IntegerField, Min, Q, Value, When
from django.utils import timezone

from jobboard.integrations.discovery_feeds import fetch_page
from jobboard.integrations.greenhouse_catalogue import CatalogueImportError
from jobboard.integrations.public_html import PublicHTMLParser, fetch_html, validate_url
from jobboard.models import DiscoveryQuery, DiscoveryResult, SourceCandidate

from .engine_collection import parse_source_url, register_source

SUPPORTED_HOSTS = {
    "boards.greenhouse.io",
    "job-boards.greenhouse.io",
    "jobs.ashbyhq.com",
    "jobs.lever.co",
    "jobs.eu.lever.co",
    "careers.smartrecruiters.com",
    "jobs.smartrecruiters.com",
}
UNSUPPORTED_SUFFIXES = {
    "myworkdayjobs.com": "workday",
    "successfactors.eu": "successfactors",
    "successfactors.com": "successfactors",
    "taleo.net": "taleo",
    "icims.com": "icims",
    "teamtailor.com": "teamtailor",
    "join.com": "join",
    "comeet.com": "comeet",
}


def candidate_from_url(url, company):
    parts = urlsplit(url)
    host = parts.hostname or ""
    validate_url(url, {host})
    pieces = parts.path.strip("/").split("/")
    from jobboard.integrations.icims_catalogue import BOARDS as ICIMS_BOARDS
    from jobboard.integrations.successfactors_catalogue import BOARDS
    from jobboard.integrations.taleo_catalogue import HOST as TALEO_HOST

    if host in {
        allowed for allowed, _ in (*BOARDS.values(), *ICIMS_BOARDS.values())
    } | {TALEO_HOST}:
        canonical = parse_source_url(
            urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
        )["canonical"]
        return register_source(canonical, company or host)
    canonical = None
    if host in SUPPORTED_HOSTS and pieces[0]:
        canonical = f"https://{host}/{pieces[0]}"
    elif host.endswith((".jobs.personio.de", ".jobs.personio.com", ".recruitee.com")):
        canonical = f"https://{host}"
    if host.endswith(".myworkdayjobs.com"):
        canonical = parse_source_url(
            urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
        )["canonical"]
    if canonical:
        return register_source(canonical, company or host)
    for suffix, provider in UNSUPPORTED_SUFFIXES.items():
        if host == suffix or host.endswith("." + suffix):
            # Vendor marketing pages and authenticated dashboards are not employer
            # career boards, even when a feed links to them.
            prefix = host.removesuffix("." + suffix) if host != suffix else ""
            if prefix in (
                "",
                "www",
                "app",
                "api",
                "auth",
                "admin",
                "login",
                "accounts",
            ) or any(
                segment.casefold()
                in (
                    "dashboard",
                    "admin",
                    "login",
                    "signin",
                    "auth",
                    "oauth",
                    "settings",
                )
                for segment in pieces
            ):
                raise CatalogueImportError("not_employer_careers")
            canonical = (
                f"https://{host}"
                if provider == "teamtailor"
                else urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
            )
            candidate, _ = SourceCandidate.objects.get_or_create(
                url=canonical,
                defaults={
                    "provider": provider,
                    "board_key": host[:240],
                    "company_name": (company or host)[:240],
                    "status": "unsupported_provider",
                },
            )
            return candidate
    return None


def resolve_result(result, deadline):
    try:
        result.error_code = ""
        candidate = candidate_from_url(result.source_url, result.company_name)
        if candidate:
            return candidate
        host = urlsplit(result.source_url).hostname
        # Every hop remains on this exact public host; the fetcher pins validated DNS.
        final_url, html = fetch_html(result.source_url, {host}, deadline=deadline)
        if result.query.provider == "linkedin_public":
            from jobboard.integrations.linkedin_discovery import VisibleLinks

            parser = VisibleLinks()
        else:
            parser = PublicHTMLParser()
        parser.feed(html)
        for href in parser.links[:1000]:
            try:
                candidate = candidate_from_url(
                    urljoin(final_url, href), result.company_name
                )
                if candidate:
                    return candidate
            except (CatalogueImportError, ValueError):
                continue
    except (CatalogueImportError, ValueError) as exc:
        result.error_code = getattr(exc, "code", "invalid_discovery_url")
    if result.query.provider == "linkedin_public" and not result.error_code:
        result.error_code = "linkedin_no_public_employer_link"
    return None


def seed_queries(auto_activate=False, linkedin=False):
    definitions = [("arbeitnow", "", "de", "all", "")]
    for language, term in [("sv", "praktik"), ("en", "internship"), ("en", "intern")]:
        for domain, word in [
            ("all", ""),
            ("engineering", "engineering"),
            ("business", "business"),
            ("marketing", "marketing"),
            ("research", "research"),
        ]:
            definitions.append(
                ("jobsearch_se", "SE", language, domain, f"{term} {word}".strip())
            )
    if linkedin:
        from jobboard.integrations.linkedin_discovery import COUNTRIES

        definitions.extend(
            ("linkedin_public", country, language, "all", term)
            for country, (_, language, term) in COUNTRIES.items()
        )
    for provider, country, language, domain, term in definitions:
        query, _ = DiscoveryQuery.objects.get_or_create(
            provider=provider,
            country=country,
            language=language,
            domain=domain,
            term=term,
        )
        if auto_activate and not query.auto_activate:
            query.auto_activate = True
            query.save(update_fields=["auto_activate"])
    return len(definitions)


def partition_capped_linkedin_query(query, cursor):
    """Queue one non-recursive domain layer only after the actual 150-lead cap."""
    if (
        query.provider != "linkedin_public"
        or query.domain != "all"
        or not cursor
        or int(cursor) < 150
    ):
        return 0
    from jobboard.integrations.linkedin_discovery import DOMAIN_SEARCH_TERMS

    language = query.language if query.language in {"fr", "de"} else "en"
    term_index = {"fr": 0, "de": 1, "en": 2}[language]
    internship_term = {"fr": "stage", "de": "Praktikum", "en": "internship"}[language]
    created_count = 0
    for domain, terms in DOMAIN_SEARCH_TERMS.items():
        _, created = DiscoveryQuery.objects.get_or_create(
            provider="linkedin_public",
            country=query.country,
            language=language,
            domain=domain,
            term=f"{internship_term} {terms[term_index]}",
            defaults={
                "auto_activate": query.auto_activate,
                "next_run_at": timezone.now() + timedelta(minutes=5),
            },
        )
        created_count += int(created)
    return created_count


def run_search_discovery(
    limit=2, resolve_limit=8, activate=False, activation_limit=3, provider=None
):
    activations_left = max(0, min(activation_limit, 10))
    processed = 0
    for _ in range(max(0, min(limit, 16))):
        now, token = timezone.now(), uuid.uuid4()
        with transaction.atomic():
            query = (
                DiscoveryQuery.objects.select_for_update(skip_locked=True)
                .filter(**({"provider": provider} if provider else {}))
                .filter(enabled=True, next_run_at__lte=now)
                .exclude(provider__startswith="jobspy_")
                .exclude(
                    provider__in=[
                        "ats_registry",
                        "eures",
                        "wttj",
                        "jobtech",
                        "bundesagentur", "nav",
                    ]
                )
                .filter(Q(lease_expires_at__isnull=True) | Q(lease_expires_at__lte=now))
                .order_by("next_run_at", "pk")
                .first()
            )
            if not query:
                break
            query.lease_token, query.lease_expires_at = (
                token,
                now + timedelta(minutes=15),
            )
            query.save(update_fields=["lease_token", "lease_expires_at"])
        updates = {"lease_token": None, "lease_expires_at": None}
        try:
            deadline = time.monotonic() + 90
            page = fetch_page(query, deadline)
            if not DiscoveryQuery.objects.filter(
                pk=query.pk, lease_token=token
            ).exists():
                continue
            for row in page.records:
                if not row["id"] or len(row["id"]) > 300:
                    raise CatalogueImportError("invalid_discovery_identity")
                result, _ = DiscoveryResult.objects.update_or_create(
                    query=query,
                    external_id=row["id"],
                    defaults={
                        "source_url": str(row["url"] or "")[:2048],
                        "company_name": str(row["company"] or "")[:240],
                        "payload": row["raw"],
                        "attribution": "https://www.arbeitnow.com"
                        if query.provider == "arbeitnow"
                        else (
                            "https://www.linkedin.com/jobs/"
                            if query.provider == "linkedin_public"
                            else "https://arbetsformedlingen.se"
                        ),
                        "last_seen_at": timezone.now(),
                    },
                )
            # Resolve backlog too, so a page larger than the HTTP budget is not forgotten.
            backlog = (
                DiscoveryResult.objects.filter(
                    query=query, status__in=["pending", "unresolved"]
                )
                .annotate(
                    internship_priority=Case(
                        When(
                            Q(
                                payload__title__iregex=r"intern|praktik|stage|tiroc|pasant|est.gio"
                            )
                            | Q(
                                payload__headline__iregex=r"intern|praktik|stage|tiroc|pasant|est.gio"
                            ),
                            then=Value(0),
                        ),
                        default=Value(1),
                        output_field=IntegerField(),
                    )
                )
                .order_by(
                    F("last_attempt_at").asc(nulls_first=True),
                    "internship_priority",
                    "pk",
                )[: max(0, min(resolve_limit, 30))]
            )
            for result in backlog:
                if time.monotonic() >= deadline:
                    break
                candidate = resolve_result(result, deadline)
                result.candidate = candidate
                result.status = (
                    candidate.status
                    if candidate
                    else (
                        "needs_access"
                        if result.error_code.startswith("linkedin_")
                        else "unresolved"
                    )
                )
                result.last_attempt_at = timezone.now()
                result.save(
                    update_fields=[
                        "candidate",
                        "status",
                        "error_code",
                        "last_attempt_at",
                    ]
                )
            if activate or query.auto_activate:
                candidates = (
                    SourceCandidate.objects.filter(
                        status="candidate",
                        probe__isnull=True,
                        discoveryresult__query=query,
                        discoveryresult__status__in=["candidate", "validation_failed"],
                    )
                    .filter(
                        Q(board__isnull=True)
                        | Q(board__engine_schedule__next_run_at__lte=timezone.now())
                    )
                    .annotate(last_activation=Min("discoveryresult__last_attempt_at"))
                    .order_by(F("last_activation").asc(nulls_first=True), "pk")[
                        :activations_left
                    ]
                )
                for candidate in candidates:
                    # Each board import may last ten minutes. Renew only our live lease
                    # before starting another; a replacement worker fences us out.
                    if not DiscoveryQuery.objects.filter(
                        pk=query.pk,
                        lease_token=token,
                        lease_expires_at__gt=timezone.now(),
                    ).update(lease_expires_at=timezone.now() + timedelta(minutes=15)):
                        break
                    activations_left -= 1
                    try:
                        register_source(
                            candidate.url, candidate.company_name, enable=True
                        )
                        DiscoveryResult.objects.filter(
                            query=query, candidate=candidate
                        ).update(
                            status="validated",
                            error_code="",
                            last_attempt_at=timezone.now(),
                        )
                    except CatalogueImportError as exc:
                        DiscoveryResult.objects.filter(
                            query=query, candidate=candidate
                        ).update(
                            status="validation_failed",
                            error_code=exc.code,
                            last_attempt_at=timezone.now(),
                        )
            updates.update(
                cursor=page.next_cursor,
                truncated=bool(page.next_cursor),
                total_available=page.total,
                result_count=query.results.count(),
                last_success_at=timezone.now(),
                last_error_code="",
                failure_count=0,
                next_run_at=now
                + (
                    timedelta(minutes=5)
                    if (
                        page.next_cursor
                        and not (
                            query.provider == "linkedin_public"
                            and int(page.next_cursor) >= 150
                        )
                    )
                    or query.results.filter(last_attempt_at__isnull=True).exists()
                    or (
                        (activate or query.auto_activate)
                        and query.results.filter(
                            status__in=["candidate", "validation_failed"]
                        ).exists()
                    )
                    else timedelta(days=1)
                ),
            )
            if (
                query.provider == "linkedin_public"
                and page.next_cursor
                and int(page.next_cursor) >= 150
            ):
                partition_capped_linkedin_query(query, page.next_cursor)
                updates["next_run_at"] = now + timedelta(days=1)
        except (CatalogueImportError, ValueError, TypeError, KeyError) as exc:
            failures = query.failure_count + 1
            if (
                query.provider == "linkedin_public"
                and getattr(exc, "code", "") == "linkedin_rate_limited"
            ):
                from django.db.models.functions import Greatest

                cooldown = now + timedelta(
                    seconds=max(
                        3600,
                        getattr(exc, "retry_after", None) or 0,
                        min(86400, 900 * 2 ** min(failures, 7)),
                    )
                )
                DiscoveryQuery.objects.filter(
                    provider="linkedin_public", enabled=True
                ).update(next_run_at=Greatest("next_run_at", cooldown))
            else:
                cooldown = now + timedelta(
                    minutes=min(1440, 15 * 2 ** min(failures, 7))
                )
            updates.update(
                failure_count=failures,
                last_error_code=getattr(exc, "code", "invalid_discovery_feed"),
                next_run_at=cooldown,
            )
        DiscoveryQuery.objects.filter(pk=query.pk, lease_token=token).update(**updates)
        processed += 1
    return processed
