import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from jobboard.services.engine_merges import merge
from jobboard.services.targeted_merges import propose_targeted


class Command(BaseCommand):
    help = (
        "Audit an explicit batch of offer IDs and optionally merge proven identities."
    )

    def add_arguments(self, parser):
        parser.add_argument("--input", required=True)
        parser.add_argument("--report", required=True)
        parser.add_argument("--merge", action="store_true")

    def handle(self, *args, **options):
        data = json.loads(Path(options["input"]).read_text())
        ids = {i for row in data["sources"] for i in row["new_visible_offer_ids"]}
        if not ids or len(ids) > 1000:
            raise CommandError("Expected 1 to 1000 offer IDs")
        report = propose_targeted(ids)
        report["target_ids"] = sorted(ids)
        report["merged"] = []
        report["skipped"] = []
        path = Path(options["report"])
        path.write_text(json.dumps(report, indent=2) + "\n")
        if options["merge"]:
            for decision_id in report["decision_ids"]:
                try:
                    merge(decision_id)
                    report["merged"].append(decision_id)
                except ValueError as exc:
                    report["skipped"].append(
                        {"decision_id": decision_id, "reason": str(exc)}
                    )
                path.write_text(json.dumps(report, indent=2) + "\n")
        self.stdout.write(
            json.dumps(
                {
                    k: v
                    for k, v in report.items()
                    if k not in ["target_ids", "title_only_groups"]
                }
            )
        )
