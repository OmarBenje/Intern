import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from jobboard.integrations.greenhouse_catalogue import CatalogueImportError
from jobboard.services.ats_registry import PROVIDERS, import_registry


class Command(BaseCommand):
    help = "Import pinned ats-scrapers inventories as candidates; optional bounded pilot activation."

    def add_arguments(self, parser):
        parser.add_argument(
            "--providers", nargs="+", choices=PROVIDERS, default=list(PROVIDERS)
        )
        parser.add_argument("--limit", type=int, default=500)
        parser.add_argument("--offset", type=int, default=0)
        parser.add_argument("--company-pattern", default="")
        parser.add_argument("--activate-limit", type=int, default=0)
        parser.add_argument("--report")

    def handle(self, *args, **options):
        try:
            report = import_registry(
                options["providers"],
                options["limit"],
                options["offset"],
                options["company_pattern"],
                options["activate_limit"],
            )
        except (ValueError, CatalogueImportError) as exc:
            raise CommandError(str(exc)) from exc
        if options["report"]:
            Path(options["report"]).write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n"
            )
        self.stdout.write(
            json.dumps({k: v for k, v in report.items() if k != "sources"})
        )
