import json

from django.core.management.base import BaseCommand

from jobboard.services.automatic_employer_discovery import run_automatic_discovery


class Command(BaseCommand):
    help = (
        "Admit fresh public feed evidence to ATS probes under the shared daily quota."
    )

    def handle(self, *args, **options):
        self.stdout.write(json.dumps(run_automatic_discovery(), ensure_ascii=False))
