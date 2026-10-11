"""Lightweight logo consumer for local setups without the full catalogue worker."""

import time

from django.core.management.base import BaseCommand
from django.db import close_old_connections

from jobboard.services.company_logos import process_logo_jobs


class Command(BaseCommand):
    help = "Automatically extract logos for new companies and retry failed downloads."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--poll-interval", type=float, default=10)

    def handle(self, *args, **options):
        while True:
            close_old_connections()
            count = process_logo_jobs(limit=5)
            if count or options["once"]:
                self.stdout.write(f"Processed {count} company logos.")
            if options["once"]:
                return
            time.sleep(max(1, options["poll_interval"]))
