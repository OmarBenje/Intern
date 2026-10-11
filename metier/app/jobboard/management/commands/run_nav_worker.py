import json
import time

from django.core.management.base import BaseCommand, CommandError
from django.db import OperationalError, close_old_connections

from jobboard.services.nav_collection import run_queries, seed_queries


class Command(BaseCommand):
    help = "Collect NAV internships with durable country cursors."

    def add_arguments(self, parser):
        parser.add_argument("--seed-countries", nargs="+")
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--limit", type=int, default=1)
        parser.add_argument("--query-id", type=int)
        parser.add_argument("--poll-interval", type=float, default=30)

    def handle(self, *args, **options):
        if options["seed_countries"]:
            try:
                seed_queries(options["seed_countries"])
            except ValueError as exc:
                raise CommandError(str(exc)) from exc
        while True:
            close_old_connections()
            try:
                result = run_queries(options["limit"], options["query_id"])
            except OperationalError as exc:
                if options["once"]:
                    raise CommandError("database_unavailable") from exc
                self.stderr.write(
                    "Database unavailable; retrying after the polling interval."
                )
                close_old_connections()
                time.sleep(max(1, options["poll_interval"]))
                continue
            if result:
                self.stdout.write(json.dumps(result))
            if options["once"]:
                return
            time.sleep(max(1, options["poll_interval"]))
