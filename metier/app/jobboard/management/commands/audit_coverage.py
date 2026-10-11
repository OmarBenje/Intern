import json

from django.core.management.base import BaseCommand
from django.core.serializers.json import DjangoJSONEncoder
from django.utils import timezone

from jobboard.api.catalogue import open_offers
from jobboard.models import DiscoveryQuery
from jobboard.services.engine_coverage import coverage_metrics, query_state


class Command(BaseCommand):
    help = "Read-only coverage and pagination diagnostics, without summing overlapping source totals."

    def handle(self, *args, **options):
        report = coverage_metrics(open_offers())
        report["query_details"] = [
            {
                "id": q.pk,
                "provider": q.provider,
                "country": q.country,
                "state": query_state(q, timezone.now()),
                "cursor": q.cursor,
                "last_success_at": q.last_success_at,
                "next_run_at": q.next_run_at,
                "error": q.last_error_code,
                "source_total": q.total_available,
            }
            for q in DiscoveryQuery.objects.order_by("pk")
        ]
        self.stdout.write(
            json.dumps(report, cls=DjangoJSONEncoder, ensure_ascii=False, indent=2)
        )
