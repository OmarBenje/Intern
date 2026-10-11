"""Rebuild versioned projections without mutating lifecycle or deleting evidence."""

from django.core.management.base import BaseCommand
from django.db.models import Count, Max

from jobboard.models import Offer
from jobboard.services.engine_quality import enrich_offer, published_offers


class Command(BaseCommand):
    help = "Re-enrich retained offers and report strict publication eligibility (no network)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--all",
            action="store_true",
            help="Process all IDs present at command start in bounded batches.",
        )
        parser.add_argument(
            "--limit", type=int, default=1000, help="Maximum batch size (1–1000)."
        )
        parser.add_argument("--after-id", type=int, default=0)

    def handle(self, *args, **options):
        limit = max(1, min(options["limit"], 1000))
        cursor = max(0, options["after_id"])
        high_water = Offer.objects.aggregate(last=Max("pk"))["last"] or 0
        processed = 0
        while True:
            ids = list(
                Offer.objects.filter(pk__gt=cursor, pk__lte=high_water)
                .order_by("pk")
                .values_list("pk", flat=True)[:limit]
            )
            if not ids:
                break
            for identity in ids:
                offer = Offer.objects.filter(pk=identity).first()
                if offer:
                    enrich_offer(offer)
                    processed += 1
            cursor = ids[-1]
            if not options["all"]:
                break
        self.stdout.write(f"Processed {processed} offers; last offer ID: {cursor}.")
        self.stdout.write(
            f"Strictly eligible before freshness/expiry checks: {published_offers(Offer.objects.all()).count()}."
        )
        for row in (
            Offer.objects.values(
                "enrichment__classification", "enrichment__europe_status"
            )
            .annotate(count=Count("pk"))
            .order_by("enrichment__classification", "enrichment__europe_status")
        ):
            self.stdout.write(
                f"{row['enrichment__classification'] or 'unclassified'} / {row['enrichment__europe_status'] or 'unknown'}: {row['count']}"
            )
        if cursor < high_water:
            self.stdout.write(f"Next batch: --after-id {cursor}")
