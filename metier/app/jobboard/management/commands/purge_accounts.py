from django.core.management.base import BaseCommand, CommandError

from jobboard.api.core import APIError
from jobboard.models import DeletionRequest
from jobboard.services.accounts import purge_account, recover_stopped_uploads


class Command(BaseCommand):
    help = "Purge requested inactive accounts; safely retry incomplete deletions."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument(
            "--recover-pending",
            nargs="+",
            type=int,
            metavar="DOCUMENT_ID",
            help="Exact pending uploads older than 24h to release, on inactive accounts awaiting deletion.",
        )
        parser.add_argument(
            "--confirm-upload-workers-stopped",
            action="store_true",
            help="Explicit operator confirmation that all writers for those uploads are stopped, including remote PUTs. Age alone does not prove this.",
        )

    def handle(self, *args, **options):
        recovery_ids = options.get("recover_pending")
        confirmed = options.get("confirm_upload_workers_stopped")
        if bool(recovery_ids) != bool(confirmed):
            raise CommandError(
                "Recovery requires exact --recover-pending IDs and --confirm-upload-workers-stopped."
            )
        if recovery_ids:
            try:
                recovered = recover_stopped_uploads(recovery_ids)
            except APIError as exc:
                raise CommandError(exc.message) from exc
            self.stdout.write(f"Recovered uploads: {recovered}")
        limit = min(max(options["limit"], 1), 1000)
        ids = list(
            DeletionRequest.objects.exclude(status="completed")
            .order_by("requested_at", "pk")
            .values_list("pk", flat=True)[:limit]
        )
        counts = {"completed": 0, "pending": 0, "failed": 0}
        for request_id in ids:
            counts[purge_account(request_id)] += 1
        self.stdout.write(" ".join(f"{key}={value}" for key, value in counts.items()))
