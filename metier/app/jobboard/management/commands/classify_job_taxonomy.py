"""Resumable reclassification. Dry runs never seed or mutate the database."""

import json
from collections import Counter

from django.core.management.base import BaseCommand
from django.db.models import Q

from jobboard.models import JobSubdomain, Offer, SourceRevision
from jobboard.services.job_taxonomy import (
    VERSION,
    assign_taxonomy,
    classify,
    seed_taxonomy,
)


class Command(BaseCommand):
    help = "Classify job functions offline; --dry-run reports without writes."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--limit", type=int, default=0)
        parser.add_argument("--after-id", type=int, default=0)
        parser.add_argument(
            "--all",
            action="store_true",
            help="Check source hashes of already classified offers too.",
        )

    def handle(self, *args, **options):
        if not options["dry_run"]:
            seed_taxonomy()
        vocabulary = dict(JobSubdomain.objects.values_list("slug", "pk"))
        qs = Offer.objects.filter(pk__gt=options["after_id"]).order_by("pk")
        if not options["all"]:
            qs = qs.filter(~Q(taxonomy_version=VERSION) | Q(taxonomy_manual=True))
        if options["limit"] > 0:
            qs = qs[: options["limit"]]
        counts, examples, last_id = Counter(), [], options["after_id"]
        for offer in qs.iterator(chunk_size=200):
            if options["dry_run"]:
                result = classify(offer.title, offer.description)
                status = (
                    "manual_preserved" if offer.taxonomy_manual else result["status"]
                )
                if len(examples) < 12:
                    examples.append(
                        {"id": offer.pk, "primary": result["primary"], "status": status}
                    )
            else:
                revisions = list(
                    SourceRevision.objects.filter(source__offer_id=offer.pk).order_by(
                        "-created_at", "-pk"
                    )[:5]
                )
                status = assign_taxonomy(
                    offer, vocabulary=vocabulary, revisions=revisions
                )
            counts[status] += 1
            last_id = offer.pk
            if sum(counts.values()) % 500 == 0:
                self.stderr.write(
                    f"{sum(counts.values())} processed; last ID {last_id}"
                )
        self.stdout.write(
            json.dumps(
                {
                    "version": VERSION,
                    "dry_run": options["dry_run"],
                    "counts": counts,
                    "last_id": last_id,
                    "examples": examples,
                },
                ensure_ascii=False,
            )
        )
