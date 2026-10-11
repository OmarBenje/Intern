"""Report logo coverage without network I/O; repair confirmed bad digests on request."""

import json

from django.core.management.base import BaseCommand
from django.db.models import Count, Q
from django.db.models.functions import Right
from django.utils import timezone

from jobboard.models import Company
from jobboard.services.company_logos import REJECTED_LOGO_DIGESTS


class Command(BaseCommand):
    help = "JSON logo audit (read-only by default); --repair requeues confirmed platform logos."

    def add_arguments(self, parser):
        parser.add_argument(
            "--repair",
            action="store_true",
            help="Requeue only confirmed platform digests; keep storage objects.",
        )

    def handle(self, *args, **options):
        if options["repair"]:
            for digest in REJECTED_LOGO_DIGESTS:
                Company.objects.filter(
                    logo_object_key__endswith=f"/{digest}.png"
                ).update(
                    logo_object_key=None,
                    logo_source_url="",
                    logo_source_kind="",
                    logo_fetched_at=None,
                    logo_attempts=0,
                    logo_next_attempt_at=timezone.now(),
                    logo_last_error="platform_logo_rejected",
                )
        companies = Company.objects.all()
        cached = companies.exclude(
            Q(logo_object_key__isnull=True) | Q(logo_object_key="")
        )
        shared = list(
            cached.annotate(digest=Right("logo_object_key", 68))
            .values("digest")
            .annotate(count=Count("pk"))
            .filter(count__gt=1)
            .order_by("-count", "digest")
        )
        report = {
            "observed_at": timezone.now().isoformat(),
            "companies": companies.count(),
            "cached": cached.count(),
            "missing": companies.count() - cached.count(),
            "with_domain": companies.exclude(
                Q(domain__isnull=True) | Q(domain="")
            ).count(),
            "with_provenance": cached.exclude(logo_source_url="").count(),
            "rejected_cached": cached.filter(
                Q(
                    *[
                        Q(logo_object_key__endswith=f"/{digest}.png")
                        for digest in REJECTED_LOGO_DIGESTS
                    ],
                    _connector=Q.OR,
                )
            ).count(),
            "shared_digests": shared,
            "errors": list(
                companies.exclude(logo_last_error="")
                .values("logo_last_error")
                .annotate(count=Count("pk"))
                .order_by("-count")[:20]
            ),
        }
        self.stdout.write(json.dumps(report, indent=2))
