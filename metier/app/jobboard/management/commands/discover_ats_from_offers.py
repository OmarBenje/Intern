import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from jobboard.services.offer_source_discovery import discover_from_offers


class Command(BaseCommand):
    help = (
        "Enrol up to 100 ATS leads evidenced by current European internship postings."
    )

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=50)
        parser.add_argument("--registry", action="store_true")
        parser.add_argument(
            "--prioritize",
            action="store_true",
            help="Rank all leads by low country coverage, one new portal per employer.",
        )
        parser.add_argument("--report", required=True)

    def handle(self, *args, **options):
        path = Path(options["report"])
        if path.exists():
            raise CommandError(
                "Use a fresh report path to preserve the previous evidence"
            )
        path.write_text("{}\n")
        try:
            report = discover_from_offers(
                options["limit"], options["registry"], options["prioritize"]
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        self.stdout.write(
            json.dumps({k: v for k, v in report.items() if k != "enrolled"})
        )
