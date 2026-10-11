from django.core.management.base import BaseCommand, CommandError

from jobboard.models import OfferSource
from jobboard.services.engine_merges import (
    merge,
    propose_link_merges,
    propose_merges,
    reverse_merge,
)


class Command(BaseCommand):
    help = "Propose exact duplicates, or explicitly merge/reverse a reviewed decision."

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group()
        group.add_argument("--links", action="store_true")
        group.add_argument("--merge", type=int)
        group.add_argument("--reverse", type=int)
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--after-source-id", type=int, default=0)

    def handle(self, *args, **options):
        try:
            if options["links"]:
                self.stdout.write(
                    f"Proposed {propose_link_merges()} exact-link candidates."
                )
            elif options["merge"]:
                decision = merge(options["merge"])
                self.stdout.write(f"Decision {decision.pk}: {decision.status}")
            elif options["reverse"]:
                decision = reverse_merge(options["reverse"])
                self.stdout.write(f"Decision {decision.pk}: {decision.status}")
            else:
                limit = max(1, min(options["limit"], 1000))
                cursor = options["after_source_id"]
                source_ids = list(
                    OfferSource.objects.filter(
                        source_status="active", offer__status="open", pk__gt=cursor
                    )
                    .order_by("pk")
                    .values_list("pk", flat=True)[:limit]
                )
                count = propose_merges(limit, after_source_id=cursor)
                self.stdout.write(f"Proposed {count} candidates.")
                if source_ids:
                    self.stdout.write(f"Next batch: --after-source-id {source_ids[-1]}")
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
