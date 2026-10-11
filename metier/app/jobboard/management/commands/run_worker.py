import time

from django.core.management.base import BaseCommand
from django.db import close_old_connections

from jobboard.services.worker import process_one


class Command(BaseCommand):
    help = "Consume the application outbox. --once processes at most one run."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--poll-interval", type=float, default=2)

    def handle(self, *args, **options):
        while True:
            close_old_connections()
            worked = process_one()
            if options["once"]:
                self.stdout.write(
                    "Processed one run." if worked else "No available run."
                )
                return
            if not worked:
                time.sleep(max(0.1, options["poll_interval"]))
