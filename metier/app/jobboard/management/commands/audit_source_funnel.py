import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from jobboard.services.source_funnel import audit_sources


class Command(BaseCommand):
    help = "Audit enabled sources and publication exclusions without changing offers."

    def add_arguments(self, parser):
        parser.add_argument("--report", required=True)

    def handle(self, *args, **options):
        try:
            with Path(options["report"]).open("x") as output:
                report = audit_sources()
                output.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        except OSError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            json.dumps({"boards": len(report["boards"]), "totals": report["totals"]})
        )
