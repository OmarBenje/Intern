import json
import time
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections

from jobboard.services.ats_probing import enroll, metrics, run_one
from jobboard.services.ats_registry import PROVIDERS


class Command(BaseCommand):
    help = "Screen enrolled ATS candidates; --enroll admits a bounded new batch."

    def add_arguments(self, parser):
        parser.add_argument("--enroll", type=int, default=0)
        parser.add_argument(
            "--providers",
            nargs="+",
            choices=PROVIDERS,
            default=["greenhouse", "lever", "ashby"],
        )
        parser.add_argument("--limit", type=int, default=1)
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--probe-ids", nargs="+", type=int)
        parser.add_argument("--poll-interval", type=float, default=30)
        parser.add_argument("--report")

    def handle(self, *args, **options):
        if (
            not 0 <= options["enroll"] <= 100
            or not 1 <= options["limit"] <= 100
            or options["poll_interval"] < 1
        ):
            raise CommandError("Invalid budget")
        if options["enroll"]:
            self.stdout.write(
                json.dumps(
                    {"enrolled": enroll(options["enroll"], options["providers"])}
                )
            )
        while True:
            for _ in range(options["limit"]):
                close_old_connections()
                result = run_one(options["probe_ids"])
                if result is None:
                    break
                self.stdout.write(json.dumps(result, default=str))
                if options["report"]:
                    with Path(options["report"]).open("a") as report:
                        report.write(json.dumps(result, default=str) + "\n")
                time.sleep(1)
            self.stdout.write(json.dumps({"queue": metrics()}, default=str))
            if options["once"]:
                return
            time.sleep(options["poll_interval"])
