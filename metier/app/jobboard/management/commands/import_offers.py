from django.core.management.base import BaseCommand, CommandError

from jobboard.integrations.greenhouse_catalogue import CatalogueImportError
from jobboard.models import SourceBoard
from jobboard.services.catalogue import import_board


class Command(BaseCommand):
    help = (
        "Import the full public Greenhouse catalogue for an existing configured board."
    )

    def add_arguments(self, parser):
        parser.add_argument("--board-id", type=int, required=True)

    def handle(self, *args, **options):
        try:
            run = import_board(options["board_id"])
        except (CatalogueImportError, SourceBoard.DoesNotExist) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            self.style.SUCCESS(f"Import {run.pk}: {run.seen_count} offers reconciled.")
        )
