import json
from collections import Counter
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from jobboard.api.catalogue import open_offers
from jobboard.models import Offer
from jobboard.services.engine_quality import (
    EXTRACTOR_VERSION,
    enrich_offer,
    extract_facts,
)


class Command(BaseCommand):
    help = "Audit retained internship classifications; --apply refreshes changed projections only."

    def add_arguments(self, parser):
        parser.add_argument("--report", required=True)
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        path = Path(options["report"])
        if path.exists():
            raise CommandError("Use a fresh report path")
        before = set(open_offers().values_list("pk", flat=True))
        report = {
            "version": EXTRACTOR_VERSION,
            "applied": options["apply"],
            "before_visible_ids": sorted(before),
            "changes": [],
            "counts": {},
        }
        counts = Counter()
        # Snapshot IDs: a concurrent importer must not make this audit unbounded.
        ids = list(Offer.objects.values_list("pk", flat=True))
        path.write_text(json.dumps(report))
        for start in range(0, len(ids), 250):
            for offer in (
                Offer.objects.filter(pk__in=ids[start : start + 250])
                .select_related("enrichment")
                .prefetch_related("locations")
            ):
                new = extract_facts(
                    offer.title,
                    offer.description,
                    contract_type=offer.contract_type,
                    locations=[
                        {"name": loc.name, "country_code": loc.country_code}
                        for loc in offer.locations.all()
                    ],
                    work_mode=offer.work_mode,
                )
                old = getattr(offer, "enrichment", None)
                counts[new["classification"]] += 1
                if (
                    not old
                    or old.classification != new["classification"]
                    or any(
                        old.facts.get("classification", {}).get(key)
                        != new["facts"]["classification"].get(key)
                        for key in ("value", "reason", "evidence_text")
                    )
                ):
                    change = {
                        "id": offer.pk,
                        "title": offer.title,
                        "lifecycle": offer.status,
                        "before": old.classification if old else None,
                        "after": new["classification"],
                        "was_visible": offer.pk in before,
                        "evidence": new["facts"]["classification"],
                    }
                    if options["apply"]:
                        actual = enrich_offer(offer)
                        change["after"] = actual.classification
                        change["evidence"] = actual.facts["classification"]
                    report["changes"].append(change)
            report["processed"] = min(start + 250, len(ids))
            report["counts"] = dict(counts)
            path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        after = set(open_offers().values_list("pk", flat=True))
        report.update(
            after_visible_ids=sorted(after),
            removed_visible_ids=sorted(before - after),
            added_visible_ids=sorted(after - before),
        )
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        self.stdout.write(
            json.dumps(
                {
                    "processed": len(ids),
                    "counts": dict(counts),
                    "changed_classifications": sum(
                        r["before"] != r["after"] for r in report["changes"]
                    ),
                    "removed_visible": len(before - after),
                    "added_visible": len(after - before),
                }
            )
        )
