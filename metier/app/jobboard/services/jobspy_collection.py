"""Query-driven direct ingestion, independent from ATS discovery and board polling."""

import hashlib
import uuid
from collections import defaultdict
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from jobboard.integrations.greenhouse_catalogue import CatalogueImportError
from jobboard.integrations.jobspy_catalogue import (
    MAX_OFFSET,
    SITES,
    collect,
    normalize_record,
)
from jobboard.integrations.linkedin_discovery import COUNTRIES
from jobboard.integrations.public_catalogue import CatalogueSnapshot
from jobboard.models import (
    BoardSchedule,
    Company,
    DiscoveryQuery,
    DiscoveryResult,
    OfferSource,
    SourceBoard,
)
from jobboard.services.catalogue import import_board


def seed_queries(countries, sites):
    for country in countries:
        if country not in COUNTRIES or any(site not in SITES for site in sites):
            raise ValueError("invalid_jobspy_query")
        _, language, term = COUNTRIES[country]
        for site in sites:
            DiscoveryQuery.objects.get_or_create(
                provider="jobspy_" + site,
                country=country,
                language=language,
                domain="all",
                term=term,
                defaults={"auto_activate": True},
            )


def ingest(query, records):
    """Caller holds the query lease/row lock; common importer fences each board."""
    provider = (
        query.provider
        if query.provider in ("eures", "wttj", "jobtech", "bundesagentur", "nav")
        else "jobspy"
    )
    site = (
        provider
        if provider in ("eures", "wttj", "jobtech", "bundesagentur", "nav")
        else query.provider.removeprefix("jobspy_")
    )
    origin = (
        "https://europa.eu/eures" if provider == "eures" else f"https://www.{site}.com"
    )
    normalizer = normalize_record
    if provider == "eures":
        from jobboard.integrations.eures_catalogue import normalize_record as normalizer
    if provider == "wttj":
        from jobboard.integrations.wttj_catalogue import normalize_record as normalizer

        origin = "https://www.welcometothejungle.com"
    if provider == "jobtech":
        from jobboard.integrations.jobtech_catalogue import (
            normalize_record as normalizer,
        )

        origin = "https://arbetsformedlingen.se"
    if provider == "bundesagentur":
        from jobboard.integrations.bundesagentur_catalogue import (
            normalize_record as normalizer,
        )

        origin = "https://www.arbeitsagentur.de"
    if provider == "nav":
        from jobboard.integrations.nav_catalogue import normalize_record as normalizer

        origin = "https://arbeidsplassen.nav.no"
    groups = defaultdict(list)
    results = {}
    diagnostics = []
    for raw in records:
        identity = hashlib.sha256(str(raw.get("url", "")).encode()).hexdigest()
        row = None
        try:
            row, facts = normalizer(raw, site)
            state = (
                "qualified"
                if row
                else "out_of_scope"
                if facts["europe_status"] == "out_of_scope"
                or facts["classification"] == "not_internship"
                else "uncertain"
            )
            error = ""
        except (CatalogueImportError, ValueError, TypeError, AttributeError) as exc:
            state, error = "invalid", getattr(exc, "code", "invalid_jobspy_record")
            diagnostics.append({"code": error})
        if (
            provider in ("eures", "wttj", "jobtech", "bundesagentur", "nav")
            and row is None
            and isinstance(raw.get("id"), str)
        ):
            # A newly unqualified/removed detail must not leave yesterday's copy visible.
            OfferSource.objects.filter(
                board__provider=provider, external_id=raw["id"]
            ).update(source_status="unknown")
        result, _ = DiscoveryResult.objects.update_or_create(
            query=query,
            external_id=identity,
            defaults={
                "source_url": str(raw.get("url") or "")[:2048],
                "company_name": str(raw.get("company") or "")[:240],
                "payload": raw,
                "attribution": origin,
                "last_seen_at": timezone.now(),
                "last_attempt_at": timezone.now(),
                "status": state,
                "error_code": error,
            },
        )
        if row:
            groups[raw["company"].strip().casefold()].append(
                (raw["company"].strip(), row)
            )
            results[(raw["company"].strip().casefold(), row["external_id"])] = result
    imported = 0
    for name_key, entries in groups.items():
        name = entries[0][0]
        key = site + "-" + hashlib.sha256(name_key.encode()).hexdigest()
        board = SourceBoard.objects.filter(
            provider=provider, board_key=key, instance="global"
        ).first()
        if board and not board.enabled:
            for _, row in entries:
                result = results[(name_key, row["external_id"])]
                result.status = "source_disabled"
                result.save(update_fields=["status"])
            continue
        company = (
            board.company
            if board
            else Company.objects.filter(name__iexact=name).order_by("pk").first()
        )
        if not company:
            company = Company.objects.create(name=name)
        if not board:
            board = SourceBoard.objects.create(
                provider=provider,
                instance="global",
                board_key=key,
                company=company,
                base_url=origin,
                adapter_version=provider + "-v1"
                if provider in ("eures", "wttj", "jobtech", "bundesagentur", "nav")
                else "jobspy-7f0ff3ab25",
            )
        schedule, _ = BoardSchedule.objects.get_or_create(board=board)
        if schedule.paused:
            for _, row in entries:
                result = results[(name_key, row["external_id"])]
                result.status = "source_paused"
                result.save(update_fields=["status"])
            continue
        rows = {}
        for _, row in entries:
            # Exact existing employer URL + same employer/title: no title-only merge.
            direct = row["raw"].get("direct_url")
            duplicate = (
                OfferSource.objects.filter(
                    Q(origin_url=direct) | Q(apply_url=direct),
                    offer__company=company,
                    offer__title__iexact=row["title"],
                    source_status="active",
                    board__enabled=True,
                )
                .exclude(board=board)
                .exists()
                if direct
                else False
            )
            if duplicate:
                result = results[(name_key, row["external_id"])]
                result.status = "duplicate"
                result.save(update_fields=["status"])
            else:
                rows[row["external_id"]] = row
        if rows:
            run = import_board(
                board.pk,
                supplied_snapshot=CatalogueSnapshot(
                    rows.values(),
                    complete=False,
                    errors=[{"code": "query_snapshot_partial"}, *diagnostics],
                ),
            )
            imported += run.seen_count
            for identity in rows:
                result = results[(name_key, identity)]
                result.status = "imported"
                result.save(update_fields=["status"])
    return imported


def run_queries(limit=1, query_id=None):
    summaries = []
    for _ in range(max(1, min(limit, 20))):
        now, token = timezone.now(), uuid.uuid4()
        with transaction.atomic():
            candidates = (
                DiscoveryQuery.objects.select_for_update(skip_locked=True)
                .filter(
                    provider__in=["jobspy_" + site for site in SITES],
                    enabled=True,
                    next_run_at__lte=now,
                )
                .filter(Q(lease_expires_at__isnull=True) | Q(lease_expires_at__lte=now))
            )
            if query_id is not None:
                candidates = candidates.filter(pk=query_id)
            query = candidates.order_by("next_run_at", "pk").first()
            if not query:
                break
            query.lease_token, query.lease_expires_at = (
                token,
                now + timedelta(minutes=10),
            )
            query.save(update_fields=["lease_token", "lease_expires_at"])
        try:
            offset = int(query.cursor or 0)
            records = collect(
                query.provider.removeprefix("jobspy_"),
                query.country,
                query.term,
                offset,
            )
            with transaction.atomic():
                locked = DiscoveryQuery.objects.select_for_update().get(pk=query.pk)
                if (
                    locked.lease_token != token
                    or locked.lease_expires_at <= timezone.now()
                    or not locked.enabled
                ):
                    raise CatalogueImportError("lease_lost")
                imported = ingest(locked, records)
                next_offset = offset + len(records)
                locked.cursor = (
                    str(next_offset) if records and next_offset < MAX_OFFSET else ""
                )
                locked.truncated = bool(records)
                locked.result_count = locked.results.count()
                locked.last_success_at = timezone.now()
                locked.last_error_code = ""
                locked.failure_count = 0
                locked.next_run_at = timezone.now() + (
                    timedelta(minutes=5) if locked.cursor else timedelta(hours=12)
                )
                locked.lease_token = locked.lease_expires_at = None
                locked.save()
            summaries.append(
                {
                    "query_id": query.pk,
                    "provider": query.provider,
                    "country": query.country,
                    "seen": len(records),
                    "imported": imported,
                }
            )
        except (CatalogueImportError, ValueError, TypeError) as exc:
            code = getattr(exc, "code", "invalid_jobspy_response")
            updates = {
                "last_error_code": code,
                "failure_count": query.failure_count + 1,
                "next_run_at": timezone.now()
                + timedelta(
                    seconds=max(
                        getattr(exc, "retry_after", None) or 0,
                        min(86400, 1800 * 2 ** min(query.failure_count, 6)),
                    )
                ),
                "lease_token": None,
                "lease_expires_at": None,
            }
            if code == "jobspy_empty_unconfirmed":
                updates["next_run_at"] = timezone.now() + timedelta(hours=12)
            DiscoveryQuery.objects.filter(pk=query.pk, lease_token=token).update(
                **updates
            )
            summaries.append(
                {
                    "query_id": query.pk,
                    "provider": query.provider,
                    "country": query.country,
                    "error": code,
                }
            )
    return summaries
