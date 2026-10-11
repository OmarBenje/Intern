import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from jobboard.integrations.greenhouse_catalogue import CatalogueImportError
from jobboard.services.external_ats_discovery import discover_external


class Command(BaseCommand):
    help = "Preview or enrol up to 100 operator-reviewed public ATS leads."

    def add_arguments(self, parser):
        parser.add_argument("--input", required=True)
        parser.add_argument("--report", required=True)
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        try:
            content = Path(options["input"]).read_text()
            if len(content) > 1024 * 1024:
                raise ValueError("Manifest exceeds 1 MiB")
            leads = json.loads(content)
            with Path(options["report"]).open("x") as output:
                result = discover_external(leads, apply=options["apply"])
                output.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        except (OSError, ValueError, TypeError, CatalogueImportError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            f"Selected {len(result['enrolled'])}; skipped {len(result['skipped'])}; apply={options['apply']}"
        )
