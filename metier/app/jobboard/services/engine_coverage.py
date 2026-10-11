"""Coverage is an observed catalogue snapshot, never a market-size estimate."""

from collections import Counter, defaultdict
from datetime import timedelta

from django.db.models import Count
from django.utils import timezone

from jobboard.models import BoardSchedule, DiscoveryQuery, OfferMergeDecision
from jobboard.services.engine_filters import fresh_sources

QUERY_PROVIDERS = {"jobspy", "eures", "wttj", "jobtech", "bundesagentur", "nav"}


def query_state(query, now):
    if not query.enabled:
        return "disabled"
    if query.lease_expires_at and query.lease_expires_at > now:
        return "running"
    if query.last_error_code:
        return "error"
    if query.truncated:
        return "truncated"
    if query.next_run_at < now - timedelta(hours=1):
        return "overdue"
    if getattr(query, "provider", "") == "nav" and query.cursor.startswith("tail:"):
        return "watching"
    if query.cursor:
        return "remaining"
    return "cycle_finished" if query.last_success_at else "not_started"


def coverage_metrics(visible):
    now = timezone.now()
    published = list(
        fresh_sources(now)
        .filter(offer__in=visible)
        .order_by()
        .values("board__provider")
        .annotate(offers=Count("offer_id", distinct=True))
    )
    queries = defaultdict(Counter)
    errors = defaultdict(Counter)
    for query in DiscoveryQuery.objects.all().iterator():
        provider = "jobspy" if query.provider.startswith("jobspy_") else query.provider
        queries[provider][query_state(query, now)] += 1
        if query.enabled and query.last_error_code:
            errors[provider][query.last_error_code] += 1
    boards = defaultdict(Counter)
    for schedule in (
        BoardSchedule.objects.select_related("board")
        .filter(board__enabled=True)
        .iterator()
    ):
        provider = schedule.board.provider
        boards[provider]["enabled"] += 1
        if schedule.paused:
            boards[provider]["paused"] += 1
        # Query imports are partial by design and not polled by the ATS scheduler.
        if provider not in QUERY_PROVIDERS and not schedule.paused:
            if schedule.last_error_code not in ("", "partial_snapshot"):
                boards[provider]["error"] += 1
                errors[provider][schedule.last_error_code] += 1
            elif schedule.next_run_at < now - timedelta(hours=1) and not (
                schedule.lease_expires_at and schedule.lease_expires_at > now
            ):
                boards[provider]["overdue"] += 1
    counts = {item["board__provider"]: item["offers"] for item in published}
    providers = [
        {
            "provider": provider,
            "offers": counts.get(provider, 0),
            "queries": dict(queries[provider]),
            "boards": dict(boards[provider]),
            "errors": [
                {"code": code, "count": count}
                for code, count in sorted(errors[provider].items())
            ],
        }
        for provider in sorted(set(counts) | set(queries) | set(boards))
    ]
    from jobboard.services.ats_probing import metrics

    return {
        "ats_queue": metrics(),
        "measured_at": now,
        "published_offers": visible.count(),
        "providers": providers,
        "deduplication": dict(
            OfferMergeDecision.objects.values_list("status").annotate(count=Count("pk"))
        ),
        "counting_note": "Distinct published offer IDs; unresolved duplicates may remain. Country and source totals overlap.",
    }
