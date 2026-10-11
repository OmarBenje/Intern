"""Report actual schedulable queues, not synthetic imported boards."""

import json

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from jobboard.models import AtsProbe, BoardSchedule, DiscoveryQuery, OutboxMessage

QUERY_PROVIDERS = ("jobspy", "eures", "wttj", "jobtech", "bundesagentur", "nav")


def queue_stats(queryset, now, date_field="next_run_at"):
    due = queryset.filter(**{date_field + "__lte": now})
    leased = Q(lease_expires_at__gt=now)
    oldest = (
        due.exclude(leased)
        .order_by(date_field)
        .values_list(date_field, flat=True)
        .first()
    )
    return {
        "enabled": queryset.count(),
        "due": due.count(),
        "leased": queryset.filter(leased).count(),
        "ready": due.exclude(leased).count(),
        "oldest_delay_seconds": max(0, int((now - oldest).total_seconds()))
        if oldest
        else 0,
    }


def collection_status():
    now = timezone.now()
    queries = DiscoveryQuery.objects.filter(enabled=True)
    boards = BoardSchedule.objects.filter(
        paused=False, board__enabled=True, board__company__isnull=False
    ).exclude(board__provider__in=QUERY_PROVIDERS)
    return {
        "measured_at": now.isoformat(),
        "ats": queue_stats(boards, now),
        "queries": {
            provider: queue_stats(queries.filter(provider=provider), now)
            for provider in queries.values_list("provider", flat=True).distinct()
        },
        "probes": queue_stats(
            AtsProbe.objects.filter(enabled=True).exclude(
                state__in=["active", "stopped"]
            ),
            now,
            "next_attempt_at",
        ),
        "outbox_pending": OutboxMessage.objects.filter(
            topic="board.sync", processed_at__isnull=True
        ).count(),
    }


class Command(BaseCommand):
    help = "Read-only collection queue health by actual scheduling owner."

    def handle(self, *args, **options):
        self.stdout.write(json.dumps(collection_status(), indent=2))
