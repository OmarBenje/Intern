from django.core.management.base import BaseCommand, CommandError

from jobboard.integrations.greenhouse_catalogue import CatalogueImportError
from jobboard.services.engine_collection import register_source


class Command(BaseCommand):
    help = "Register a public ATS board URL; --enable validates by pilot import and schedules collection."

    def add_arguments(self, parser):
        parser.add_argument("url")
        parser.add_argument("--company", required=True)
        parser.add_argument("--enable", action="store_true")

    def handle(self, *args, **options):
        try:
            candidate = register_source(
                options["url"], options["company"], options["enable"]
            )
        except (CatalogueImportError, ValueError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            f"Source candidate {candidate.pk}: {candidate.status}; board={candidate.board_id}"
        )
