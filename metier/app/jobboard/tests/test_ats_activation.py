import json
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from jobboard.integrations.greenhouse_catalogue import CatalogueImportError
from jobboard.models import BoardSchedule, Company, SourceBoard, SourceCandidate

MODULE = "jobboard.management.commands.activate_ats_candidates"


class ActivationTests(TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.report = Path(self.directory.name) / "report.json"
        self.candidate = SourceCandidate.objects.create(
            url="https://job-boards.greenhouse.io/example",
            provider="greenhouse",
            board_key="example",
            company_name="Example",
        )

    def run_command(self, **kwargs):
        call_command(
            "activate_ats_candidates",
            ids=[self.candidate.pk],
            report=str(self.report),
            stdout=StringIO(),
            **kwargs,
        )
        return json.loads(self.report.read_text())

    def configure(self, *args, **kwargs):
        board = SourceBoard.objects.create(
            provider="greenhouse",
            board_key="example",
            company=Company.objects.create(name="Example"),
            base_url=self.candidate.url,
        )
        BoardSchedule.objects.create(board=board)
        self.candidate.board = board
        self.candidate.save()
        return self.candidate

    def test_preview_does_not_import(self):
        with patch(f"{MODULE}.register_source") as register:
            report = self.run_command()
        register.assert_not_called()
        self.assertEqual(report["sources"][0]["status"], "preview")

    def test_existing_board_is_preserved(self):
        self.configure()
        with self.assertRaises(CommandError):
            self.run_command(execute=True)
        self.assertFalse(BoardSchedule.objects.get().paused)

    def test_budget_and_missing_ids(self):
        with self.assertRaises(CommandError):
            call_command(
                "activate_ats_candidates", ids=list(range(11)), report=str(self.report)
            )
        with self.assertRaises(CommandError):
            call_command(
                "activate_ats_candidates", ids=[999999], report=str(self.report)
            )

    def test_no_target_pauses_schedule(self):
        with patch(f"{MODULE}.register_source", side_effect=self.configure):
            report = self.run_command(execute=True)
        self.assertTrue(BoardSchedule.objects.get().paused)
        self.assertEqual(report["sources"][0]["status"], "paused_no_target_internships")

    def test_target_keeps_schedule_and_attributes_only_board_ids(self):
        with (
            patch(f"{MODULE}.register_source", side_effect=self.configure),
            patch(f"{MODULE}.open_offers") as offers,
        ):
            offers.return_value.values_list.return_value = [1, 2]
            visible = offers.return_value.filter.return_value.distinct.return_value
            visible.values_list.return_value = [2, 3]
            visible.filter.return_value.distinct.return_value.values_list.return_value = [
                3
            ]
            report = self.run_command(execute=True)
        self.assertFalse(BoardSchedule.objects.get().paused)
        row = report["sources"][0]
        self.assertEqual(row["new_visible_offer_ids"], [3])
        self.assertEqual(row["new_target_offer_ids"], [3])
        self.assertEqual(row["status"], "active")

    def test_failure_is_reported_and_next_candidate_runs(self):
        second = SourceCandidate.objects.create(
            url="https://job-boards.greenhouse.io/second",
            provider="greenhouse",
            board_key="second",
            company_name="Second",
        )
        with patch(
            f"{MODULE}.register_source",
            side_effect=CatalogueImportError("upstream_invalid_response"),
        ) as register:
            call_command(
                "activate_ats_candidates",
                ids=[self.candidate.pk, second.pk],
                execute=True,
                report=str(self.report),
                stdout=StringIO(),
            )
        self.assertEqual(register.call_count, 2)
        report = json.loads(self.report.read_text())
        self.assertEqual([r["status"] for r in report["sources"]], ["failed", "failed"])

    def test_country_from_explicit_location_text_keeps_source(self):
        from django.utils import timezone

        from jobboard.models import Location, Offer, OfferSource
        from jobboard.services.engine_quality import enrich_offer

        def configure_with_stage(*args, **kwargs):
            candidate = self.configure()
            offer = Offer.objects.create(
                company=candidate.board.company,
                title="Marketing Internship",
                description="Internship in marketing.",
                status="open",
            )
            offer.locations.add(
                Location.objects.create(
                    name="London, United Kingdom", canonical_key="london-uk-test"
                )
            )
            OfferSource.objects.create(
                board=candidate.board,
                offer=offer,
                external_id="test",
                content_hash="a" * 64,
                origin_url="https://job-boards.greenhouse.io/example/jobs/1",
                last_checked_at=timezone.now(),
                source_status="active",
            )
            enrich_offer(offer)
            return candidate

        with patch(f"{MODULE}.register_source", side_effect=configure_with_stage):
            report = self.run_command(execute=True)
        self.assertEqual(report["sources"][0]["status"], "active")
        self.assertEqual(len(report["sources"][0]["target_offer_ids"]), 1)
