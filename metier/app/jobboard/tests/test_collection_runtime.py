import io
import signal
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from jobboard.management.commands.collection_status import collection_status
from jobboard.management.commands.run_collection_supervisor import Command
from jobboard.models import BoardSchedule, Company, DiscoveryQuery, SourceBoard


class QueueStatusTests(TestCase):
    def test_synthetic_boards_are_not_ats_work_and_leases_are_separate(self):
        company = Company.objects.create(name="Example")
        for provider in ("ashby", "wttj"):
            board = SourceBoard.objects.create(
                company=company, provider=provider, board_key=provider, enabled=True
            )
            BoardSchedule.objects.create(
                board=board,
                lease_expires_at=timezone.now() + timezone.timedelta(minutes=5)
                if provider == "ashby"
                else None,
            )
        DiscoveryQuery.objects.create(
            provider="wttj",
            country="FR",
            language="fr",
            domain="all",
            term="internship",
            enabled=True,
        )
        report = collection_status()
        self.assertEqual(report["ats"]["enabled"], 1)
        self.assertEqual(report["ats"]["ready"], 0)
        self.assertEqual(report["ats"]["leased"], 1)
        self.assertEqual(report["queries"]["wttj"]["ready"], 1)


class WorkerRolesTests(SimpleTestCase):
    def test_imports_do_not_run_slow_maintenance(self):
        with (
            patch(
                "jobboard.management.commands.run_catalogue_worker.schedule_due",
                return_value=1,
            ),
            patch(
                "jobboard.management.commands.run_catalogue_worker.process_one",
                return_value=True,
            ) as process,
            patch(
                "jobboard.management.commands.run_catalogue_worker.process_logo_jobs"
            ) as logos,
            patch("jobboard.management.commands.run_catalogue_worker.time.sleep"),
            patch("jobboard.services.engine_discovery.run_discovery") as discovery,
        ):
            call_command(
                "run_catalogue_worker",
                once=True,
                imports_only=True,
                limit=1,
                stdout=io.StringIO(),
            )
        process.assert_called_once()
        logos.assert_not_called()
        discovery.assert_not_called()

    def test_maintenance_does_not_schedule_imports(self):
        with (
            patch(
                "jobboard.management.commands.run_catalogue_worker.schedule_due"
            ) as schedule,
            patch(
                "jobboard.management.commands.run_catalogue_worker.process_logo_jobs",
                return_value=0,
            ),
            patch("jobboard.services.engine_discovery.run_discovery"),
            patch(
                "jobboard.services.automatic_employer_discovery.run_automatic_discovery",
                return_value={},
            ),
            patch("jobboard.services.content_duplicates.reconcile_duplicates", return_value={}) as deduplicate,
            patch("jobboard.services.engine_search_discovery.run_search_discovery"),
            patch("jobboard.services.engine_alerts.run_alerts"),
            patch("jobboard.services.engine_external.process_external_opportunities"),
        ):
            call_command(
                "run_catalogue_worker",
                once=True,
                maintenance_only=True,
                limit=1,
                stdout=io.StringIO(),
            )
        schedule.assert_not_called()
        deduplicate.assert_called_once_with(limit=100)

    def test_supervisor_restarts_exited_child_after_backoff(self):
        now = [100.0]
        first = MagicMock(pid=100)
        first.poll.return_value = 1
        first.returncode = 1
        second = MagicMock(pid=101)
        second.poll.return_value = 0
        starts = []

        def spawn(*args, **kwargs):
            starts.append(now[0])
            return first if len(starts) == 1 else second

        def sleep(seconds):
            now[0] += seconds
            if len(starts) == 2:
                signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)

        prefix = "jobboard.management.commands.run_collection_supervisor."
        with (
            TemporaryDirectory() as directory,
            patch(prefix + "worker_commands", return_value={"test": ["test_worker"]}),
            patch(prefix + "subprocess.Popen", side_effect=spawn),
            patch(prefix + "time.monotonic", side_effect=lambda: now[0]),
            patch(prefix + "time.sleep", side_effect=sleep),
        ):
            Command(stdout=io.StringIO(), stderr=io.StringIO()).run_workers(
                Path(directory), Path(directory)
            )
        self.assertEqual(starts, [100.0, 106.0])
