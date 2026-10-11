"""Durable NAV country cursors, query leases and bounded retry scheduling."""

import uuid
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from jobboard.integrations.greenhouse_catalogue import CatalogueImportError
from jobboard.integrations.nav_catalogue import collect
from jobboard.models import DiscoveryQuery, OfferSource
from jobboard.services.jobspy_collection import ingest


def seed_queries(countries):
    if countries != ["NO"]:
        raise ValueError("invalid_nav_country")
    if not DiscoveryQuery.objects.filter(provider="nav").exists():
        DiscoveryQuery.objects.create(
            provider="nav",
            country="NO",
            language="no",
            domain="all",
            term=(timezone.now() - timedelta(days=184)).date().isoformat(),
            auto_activate=True,
        )


def run_queries(limit=1, query_id=None):
    summaries = []
    for _ in range(max(1, min(limit, 31))):
        now, token = timezone.now(), uuid.uuid4()
        with transaction.atomic():
            queries = (
                DiscoveryQuery.objects.select_for_update(skip_locked=True)
                .filter(
                    provider="nav",
                    enabled=True,
                    next_run_at__lte=now,
                )
                .filter(Q(lease_expires_at__isnull=True) | Q(lease_expires_at__lte=now))
            )
            if query_id is not None:
                queries = queries.filter(pk=query_id)
            query = queries.order_by("next_run_at", "pk").first()
            if not query:
                break
            query.lease_token, query.lease_expires_at = (
                token,
                now + timedelta(minutes=10),
            )
            query.save(update_fields=["lease_token", "lease_expires_at"])
        try:
            page = collect(
                query.term,
                query.cursor,
                known_ids=set(
                    OfferSource.objects.filter(board__provider="nav").values_list(
                        "external_id", flat=True
                    )
                ),
            )
            with transaction.atomic():
                locked = DiscoveryQuery.objects.select_for_update().get(pk=query.pk)
                if (
                    locked.lease_token != token
                    or locked.lease_expires_at <= timezone.now()
                    or not locked.enabled
                ):
                    raise CatalogueImportError("lease_lost")
                imported = ingest(locked, page.records)
                if page.at_tail:
                    # A fully consumed change feed also confirms unchanged active ads.
                    OfferSource.objects.filter(
                        board__provider="nav",
                        board__enabled=True,
                        source_status="active",
                    ).update(last_checked_at=timezone.now())
                locked.cursor = page.next_cursor
                locked.truncated = page.truncated
                locked.total_available = page.total
                locked.result_count = locked.results.count()
                locked.last_success_at = timezone.now()
                locked.last_error_code = ""
                locked.failure_count = 0
                locked.next_run_at = timezone.now() + (
                    timedelta(minutes=2) if page.at_tail else timedelta(seconds=10)
                )
                locked.lease_token = locked.lease_expires_at = None
                locked.save()
            summaries.append(
                {
                    "query_id": query.pk,
                    "country": query.country,
                    "seen": len(page.records),
                    "events_scanned": page.scanned,
                    "at_tail": page.at_tail,
                    "imported": imported,
                    "source_total": page.total,
                    "next_cursor": page.next_cursor,
                    "truncated": page.truncated,
                }
            )
        except (CatalogueImportError, ValueError, TypeError) as exc:
            code = getattr(exc, "code", "nav_invalid_response")
            delay = max(
                getattr(exc, "retry_after", None) or 0,
                min(86400, 1800 * 2 ** min(query.failure_count, 6)),
            )
            DiscoveryQuery.objects.filter(pk=query.pk, lease_token=token).update(
                last_error_code=code,
                failure_count=query.failure_count + 1,
                next_run_at=timezone.now() + timedelta(seconds=delay),
                lease_token=None,
                lease_expires_at=None,
            )
            summaries.append(
                {"query_id": query.pk, "country": query.country, "error": code}
            )
    return summaries
