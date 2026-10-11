from django.core.management.base import BaseCommand

from jobboard.services.engine_search_discovery import seed_queries


class Command(BaseCommand):
    help = "Idempotently enable 16 real no-key feed queries (Arbeitnow and Sweden JobSearch)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--linkedin",
            action="store_true",
            help="Opt in to bounded public guest LinkedIn country searches; login gates stop discovery.",
        )
        parser.add_argument(
            "--auto-activate",
            action="store_true",
            help="Persist automatic validated pilot imports for discovered supported ATS boards.",
        )

    def handle(self, *args, **options):
        self.stdout.write(
            f"Configured {seed_queries(auto_activate=options['auto_activate'], linkedin=options['linkedin'])} queries. Public search grids are discovery leads, not proof of complete national coverage."
        )
