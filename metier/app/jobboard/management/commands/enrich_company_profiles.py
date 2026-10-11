import json

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Exists, OuterRef, Prefetch

from jobboard.models import Company, CompanyProfile, Offer, OfferSource, SourceRevision
from jobboard.services.company_profiles import enrich_company_from_offer


class Command(BaseCommand):
    help = "Enrich company presentations from stored offers, or import reviewed sourced profiles. No network."

    def add_arguments(self, parser):
        parser.add_argument("--company-id", type=int)
        parser.add_argument(
            "--import-file",
            help="JSON list of {company_id, facts, sections}; merge by key.",
        )

    def handle(self, *args, **options):
        if options["import_file"]:
            return self.import_profiles(options["import_file"])
        sources = OfferSource.objects.filter(
            source_status="active", board__enabled=True
        )
        offers = (
            Offer.objects.filter(Exists(sources.filter(offer_id=OuterRef("pk"))))
            .select_related("company")
            .prefetch_related(
                Prefetch(
                    "sources", queryset=sources.order_by("-last_checked_at", "-pk")
                )
            )
            .order_by("company_id", "-published_at", "-pk")
        )
        if options["company_id"]:
            offers = offers.filter(company_id=options["company_id"])
        covered = set(
            CompanyProfile.objects.filter(
                sections__contains=[{"key": "presentation"}]
            ).values_list("company_id", flat=True)
        )
        examined, enriched = set(), set()
        for offer in offers.iterator(chunk_size=100):
            if offer.company_id in covered:
                continue
            examined.add(offer.company_id)
            for source in offer.sources.all():
                revision = (
                    SourceRevision.objects.filter(source=source).order_by("-pk").first()
                )
                if enrich_company_from_offer(offer, source, revision):
                    enriched.add(offer.company_id)
                    covered.add(offer.company_id)
                    break
        self.stdout.write(
            json.dumps(
                {
                    "companies_examined": len(examined),
                    "presentations_added": len(enriched),
                    "presentations_available": len(covered),
                    "companies_total": Company.objects.count(),
                }
            )
        )

    def import_profiles(self, path):
        try:
            with open(path) as stream:
                rows = json.load(stream)
        except (OSError, ValueError) as exc:
            raise CommandError("Cannot read the reviewed profile JSON.") from exc
        if not isinstance(rows, list):
            raise CommandError("Expected a list of company profiles.")
        with transaction.atomic():
            for row in rows:
                if not isinstance(row, dict) or type(row.get("company_id")) is not int:
                    raise CommandError(
                        "Each profile needs an exact integer company_id."
                    )
                company = (
                    Company.objects.select_for_update()
                    .filter(pk=row["company_id"])
                    .first()
                )
                if not company:
                    raise CommandError("Unknown company_id.")
                if row.get("company_name") and row["company_name"] != company.name:
                    raise CommandError(
                        "company_id does not match the reviewed company_name."
                    )
                profile, _ = CompanyProfile.objects.get_or_create(company=company)
                for field in ("facts", "sections"):
                    incoming = row.get(field, [])
                    if not isinstance(incoming, list) or not all(
                        isinstance(entry, dict) for entry in incoming
                    ):
                        raise CommandError(
                            "Facts and sections must be lists of sourced entries."
                        )
                    keys = {entry.get("key") for entry in incoming}
                    previous = getattr(profile, field)
                    setattr(
                        profile,
                        field,
                        [entry for entry in previous if entry.get("key") not in keys]
                        + incoming,
                    )
                profile.full_clean()
                profile.save()
        self.stdout.write(f"Imported {len(rows)} reviewed company profiles.")
