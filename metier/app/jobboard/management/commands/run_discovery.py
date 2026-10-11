import json

from django.core.management.base import BaseCommand

from jobboard.models import DiscoveryQuery
from jobboard.services.engine_search_discovery import run_search_discovery


class Command(BaseCommand):
    help = "Run one bounded discovery batch or inspect durable progress; activation validates a pilot import."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")
        parser.add_argument(
            "--provider", choices=["linkedin_public", "arbeitnow", "jobsearch_se"]
        )
        parser.add_argument("--status", action="store_true")
        parser.add_argument("--limit", type=int, default=2)
        parser.add_argument("--resolve-limit", type=int, default=8)
        parser.add_argument("--activate", action="store_true")
        parser.add_argument("--activation-limit", type=int, default=3)

    def handle(self, *args, **options):
        if options["status"]:
            self.stdout.write(
                json.dumps(
                    list(
                        DiscoveryQuery.objects.values(
                            "id",
                            "provider",
                            "country",
                            "language",
                            "domain",
                            "term",
                            "cursor",
                            "result_count",
                            "total_available",
                            "truncated",
                            "last_success_at",
                            "last_error_code",
                            "auto_activate",
                            "next_run_at",
                        )
                    ),
                    default=str,
                )
            )
            return
        processed = run_search_discovery(
            options["limit"],
            options["resolve_limit"],
            activate=options["activate"],
            activation_limit=options["activation_limit"],
            provider=options["provider"],
        )
        self.stdout.write(
            f"Processed {processed} feed queries; results are discovery leads, not published jobs."
        )
