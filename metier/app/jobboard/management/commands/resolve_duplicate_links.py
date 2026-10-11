import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from jobboard.services.engine_filters import fresh_sources
from jobboard.services.job_link_evidence import resolve


class Command(BaseCommand):
    help = (
        "Resolve public employer links for the ambiguous groups of a duplicate audit."
    )

    def add_arguments(self, parser):
        parser.add_argument("--input", required=True)
        parser.add_argument("--report", required=True)

    def handle(self, *args, **options):
        groups = json.loads(Path(options["input"]).read_text())["title_only_groups"]
        ids = {i for group in groups for i in group}
        if not 1 <= len(ids) <= 200:
            raise CommandError("Expected 1..200 offer IDs")
        path = Path(options["report"])
        if path.exists():
            raise CommandError("Use a new report filename")
        path.write_text("")
        blocked = set()
        for source in (
            fresh_sources()
            .filter(offer_id__in=ids)
            .select_related("board", "offer__company")
            .order_by("pk")
        ):
            result = resolve(source, blocked)
            with path.open("a") as f:
                f.write(json.dumps(result, ensure_ascii=False) + "\n")
            self.stdout.write(
                json.dumps({k: result[k] for k in ["source_id", "status", "error"]})
            )
