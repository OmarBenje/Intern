"""Bounded, explicit registry pilots with attributable publication reports."""

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.utils import timezone

from jobboard.api.catalogue import open_offers
from jobboard.integrations.greenhouse_catalogue import CatalogueImportError
from jobboard.models import BoardSchedule, SourceBoard, SourceCandidate
from jobboard.services.engine_collection import register_source
from jobboard.services.engine_quality import EUROPE_COUNTRIES

TARGET_COUNTRIES = tuple(sorted(EUROPE_COUNTRIES))


class Command(BaseCommand):
    help = "Preview or pilot up to 10 explicit ATS candidates; pause sources without target-country internships."

    def add_arguments(self, parser):
        parser.add_argument("--ids", nargs="+", type=int, required=True)
        parser.add_argument(
            "--countries",
            nargs="+",
            choices=TARGET_COUNTRIES,
            default=list(TARGET_COUNTRIES),
        )
        parser.add_argument("--execute", action="store_true")
        parser.add_argument("--report", required=True)

    def handle(self, *args, **options):
        ids = list(dict.fromkeys(options["ids"]))
        if not 1 <= len(ids) <= 10:
            raise CommandError("Select 1 to 10 candidates")
        candidates = list(SourceCandidate.objects.filter(pk__in=ids).order_by("pk"))
        if len(candidates) != len(ids):
            raise CommandError("Unknown candidate ID")
        # Never change an existing board or its operator-selected schedule.
        if any(
            c.board_id
            or c.status != "candidate"
            or SourceBoard.objects.filter(
                provider=c.provider, instance=c.instance, board_key=c.board_key
            ).exists()
            for c in candidates
        ):
            raise CommandError("Only unconfigured candidates can be piloted")
        path = Path(options["report"])
        report = {
            "started_at": timezone.now().isoformat(),
            "countries": options["countries"],
            "execute": options["execute"],
            "sources": [],
            "counting_note": "Visible offer IDs, not guaranteed unique vacancies across sources. Other workers excluded from source counts.",
        }

        def save():
            temporary = path.with_suffix(path.suffix + ".tmp")
            temporary.write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n"
            )
            temporary.replace(path)

        save()  # Verify report destination before any mutation.
        for candidate in candidates:
            entry = {
                "candidate_id": candidate.pk,
                "company": candidate.company_name,
                "url": candidate.url,
                "provider": candidate.provider,
                "status": "preview",
            }
            report["sources"].append(entry)
            if options["execute"]:
                before = set(open_offers().values_list("pk", flat=True))
                entry["status"] = "running"
                save()
                try:
                    candidate = register_source(
                        candidate.url, candidate.company_name, enable=True
                    )
                    visible = (
                        open_offers()
                        .filter(sources__board_id=candidate.board_id)
                        .distinct()
                    )
                    country_filter = Q(pk__in=[])
                    for country in options["countries"]:
                        country_filter |= Q(
                            enrichment__country_codes__contains=[country]
                        )
                    target = visible.filter(country_filter).distinct()
                    visible_ids = set(visible.values_list("pk", flat=True))
                    target_ids = set(target.values_list("pk", flat=True))
                    if not target_ids:
                        BoardSchedule.objects.filter(
                            board_id=candidate.board_id
                        ).update(paused=True)
                    entry.update(
                        board_id=candidate.board_id,
                        status="active"
                        if target_ids
                        else "paused_no_target_internships",
                        visible_offer_ids=sorted(visible_ids),
                        target_offer_ids=sorted(target_ids),
                        new_visible_offer_ids=sorted(visible_ids - before),
                        new_target_offer_ids=sorted(target_ids - before),
                    )
                except CatalogueImportError as exc:
                    entry.update(status="failed", error_code=exc.code)
                finally:
                    save()
            save()
            self.stdout.write(json.dumps(entry, ensure_ascii=False))
        report["finished_at"] = timezone.now().isoformat()
        save()
