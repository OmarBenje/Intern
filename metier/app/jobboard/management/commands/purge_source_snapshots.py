from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from jobboard.models import OfferSource, SourceRevision


class Command(BaseCommand):
    help = "Redact source payloads older than 30 days; retain hashes, revision IDs and extracted evidence."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=1000)

    def handle(self, *args, **options):
        now = timezone.now()
        limit = max(1, min(options["limit"], 10000))
        ids = list(
            SourceRevision.objects.filter(created_at__lt=now - timedelta(days=30))
            .exclude(payload={})
            .order_by("pk")
            .values_list("pk", flat=True)[:limit]
        )
        # Explicit retention exception: metadata remains immutable, payload is redacted.
        revised = SourceRevision.objects.filter(pk__in=ids).update(payload={})
        ids = list(
            OfferSource.objects.filter(raw_expires_at__lte=now)
            .exclude(raw_payload={})
            .order_by("pk")
            .values_list("pk", flat=True)[:limit]
        )
        sources = OfferSource.objects.filter(pk__in=ids).update(raw_payload={})
        self.stdout.write(
            f"Redacted {revised} revisions and {sources} current payloads."
        )
