from django.core.management.base import BaseCommand, CommandError

from jobboard.integrations.greenhouse_catalogue import CatalogueImportError
from jobboard.integrations.public_html import validate_url
from jobboard.models import SourceDiscoverySeed


class Command(BaseCommand):
    help = "Approve an exact employer hostname for daily public career-page discovery."

    def add_arguments(self, parser):
        parser.add_argument("url")
        parser.add_argument("--allowed-host", required=True)
        parser.add_argument("--company", required=True)

    def handle(self, *args, **options):
        host = options["allowed_host"].strip().lower()
        company = options["company"].strip()
        try:
            validate_url(options["url"], {host})
            if not company or len(company) > 240 or len(host) > 253:
                raise ValueError("Invalid company or hostname")
        except (CatalogueImportError, ValueError) as exc:
            raise CommandError(str(exc)) from exc
        seed, _ = SourceDiscoverySeed.objects.update_or_create(
            url=options["url"],
            defaults={"allowed_host": host, "company_name": company, "enabled": True},
        )
        self.stdout.write(f"Discovery seed {seed.pk}: enabled for {host}")
