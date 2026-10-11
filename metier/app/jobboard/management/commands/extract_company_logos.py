from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count, Q

from jobboard.integrations.greenhouse_catalogue import CatalogueImportError
from jobboard.models import Company
from jobboard.services.company_logos import cache_logo, extract_logo


class Command(BaseCommand):
    help = "Extract and cache company logos from their registered employer pages."

    def add_arguments(self, parser):
        parser.add_argument("--company-id", type=int)
        parser.add_argument(
            "--page-url", help="Verified employer page, for a single company"
        )
        parser.add_argument(
            "--image-url", help="Verified employer logo, for a single company"
        )
        parser.add_argument("--refresh", action="store_true")
        parser.add_argument(
            "--provider",
            help="Limit to companies with this source provider, e.g. wttj.",
        )
        parser.add_argument(
            "--limit", type=int, default=25, help="Bound the run (default 25)."
        )

    def handle(self, *args, **options):
        if (options["page_url"] or options["image_url"]) and not options["company_id"]:
            raise CommandError("An explicit source requires --company-id.")
        if not 1 <= options["limit"] <= 500:
            raise CommandError("--limit must be between 1 and 500.")
        companies = Company.objects.annotate(offer_count=Count("offers")).order_by(
            "-offer_count", "pk"
        )
        if options["provider"]:
            companies = companies.filter(
                source_boards__provider=options["provider"]
            ).distinct()
        if options["company_id"]:
            companies = companies.filter(pk=options["company_id"])
        elif not options["refresh"]:
            companies = companies.filter(
                Q(logo_object_key__isnull=True) | Q(logo_object_key="")
            )
        successful = failed = 0
        for company in companies[: options["limit"]]:
            try:
                if options["image_url"]:
                    cache_logo(company, options["image_url"])
                else:
                    extract_logo(company, page_url=options["page_url"])
                successful += 1
                self.stdout.write(f"OK {company.pk}: {company.name}")
            except CatalogueImportError as exc:
                failed += 1
                self.stderr.write(f"MISSING {company.pk}: {company.name}: {exc}")
        self.stdout.write(f"Cached: {successful}; missing: {failed}")
