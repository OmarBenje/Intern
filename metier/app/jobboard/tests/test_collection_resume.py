from datetime import timedelta
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from jobboard.integrations.eightfold_catalogue import _checkpoint, fetch_eightfold
from jobboard.integrations.greenhouse_catalogue import CatalogueImportError
from jobboard.models import BoardSchedule, Company, OfferSource, SourceBoard
from jobboard.services.catalogue import import_board

from .test_eightfold import detail


def response(data):
    return {"status": 200, "data": data}


def listing(jobs):
    return response({"count": len(jobs), "positions": jobs})


def limited():
    error = CatalogueImportError("upstream_rate_limited")
    error.retry_after = 18000
    return error


class ResumeTests(SimpleTestCase):
    def setUp(self):
        patcher = patch("jobboard.integrations.eightfold_catalogue.REQUEST_INTERVAL", 0)
        patcher.start()
        self.addCleanup(patcher.stop)

    def interrupted(self):
        with patch(
            "jobboard.integrations.eightfold_catalogue.read_json",
            side_effect=[
                listing([detail(), detail(id=456)]),
                response(detail()),
                limited(),
            ],
        ):
            return fetch_eightfold("microsoft")

    def test_detail_resume_skips_consumed_page_and_deduplicates_next_terms(self):
        first = self.interrupted()
        self.assertEqual([r["external_id"] for r in first], ["123"])
        self.assertEqual(first.checkpoint["pending"], ["456"])
        self.assertEqual(first.retry_after, 18000)
        with patch(
            "jobboard.integrations.eightfold_catalogue.read_json",
            side_effect=[
                response(detail(id=456)),
                listing([detail(), detail(id=456)]),
                listing([]),
                listing([]),
            ],
        ) as read:
            second = fetch_eightfold("microsoft", checkpoint=first.checkpoint)
        self.assertIn("position_id=456", read.call_args_list[0].args[0])
        self.assertEqual([r["external_id"] for r in second], ["456"])
        self.assertEqual(second.checkpoint, {})
        self.assertFalse(second.complete)
        self.assertEqual(first.checkpoint["pending"], ["456"])

    def test_search_failure_keeps_rows_and_cursor(self):
        with patch(
            "jobboard.integrations.eightfold_catalogue.read_json",
            side_effect=[
                listing([detail()]),
                response(detail()),
                limited(),
            ],
        ):
            rows = fetch_eightfold("microsoft")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows.checkpoint["term"], 1)
        self.assertEqual(rows.retry_after, 18000)

    def test_resume_search_at_saved_page(self):
        jobs = [detail(id=i, name="Senior engineer") for i in range(10)]
        with patch(
            "jobboard.integrations.eightfold_catalogue.read_json",
            side_effect=[
                response({"count": 11, "positions": jobs}),
                limited(),
            ],
        ):
            first = fetch_eightfold("microsoft")
        self.assertEqual(first.checkpoint["page"], 1)
        with patch(
            "jobboard.integrations.eightfold_catalogue.read_json",
            side_effect=[
                response({"count": 11, "positions": [detail(id=456)]}),
                response(detail(id=456)),
                listing([]),
                listing([]),
                listing([]),
            ],
        ) as read:
            second = fetch_eightfold("microsoft", checkpoint=first.checkpoint)
        self.assertIn("start=10", read.call_args_list[0].args[0])
        self.assertEqual(second[0]["external_id"], "456")
        self.assertEqual(second.checkpoint, {})

    def test_transient_server_failure_retains_detail(self):
        error = CatalogueImportError("upstream_http_error")
        error.status_code = 503
        with patch(
            "jobboard.integrations.eightfold_catalogue.read_json",
            side_effect=[
                listing([detail()]),
                error,
            ],
        ):
            rows = fetch_eightfold("microsoft")
        self.assertEqual(rows.checkpoint["pending"], ["123"])

    def test_expired_wrong_board_and_invalid_checkpoints_restart(self):
        state = self.interrupted().checkpoint
        for changes in [
            {"key": "nvidia"},
            {"started_at": 0},
            {"page": -1},
            {"pending": ["https://evil.test/"]},
            {"pending": ["999"]},
            {"seen": "invalid"},
            {"term": True},
        ]:
            with self.subTest(changes=changes):
                clean = _checkpoint("microsoft", dict(state, **changes))
                self.assertEqual(clean["term"], 0)
                self.assertEqual(clean["pending"], [])


class ResumeImportTests(TestCase):
    def setUp(self):
        self.board = SourceBoard.objects.create(
            provider="eightfold",
            board_key="microsoft",
            company=Company.objects.create(name="Microsoft"),
            enabled=True,
        )
        self.schedule = BoardSchedule.objects.create(board=self.board)

    def test_progress_and_retry_after_committed_with_offers(self):
        with (
            patch("jobboard.integrations.eightfold_catalogue.REQUEST_INTERVAL", 0),
            patch(
                "jobboard.integrations.eightfold_catalogue.read_json",
                side_effect=[
                    listing([detail(), detail(id=456)]),
                    response(detail()),
                    limited(),
                ],
            ),
        ):
            started = timezone.now()
            import_board(self.board.pk)
        self.schedule.refresh_from_db()
        self.assertEqual(self.schedule.collection_checkpoint["pending"], ["456"])
        self.assertGreaterEqual(
            self.schedule.next_run_at, started + timedelta(seconds=18000)
        )
        with (
            patch("jobboard.integrations.eightfold_catalogue.REQUEST_INTERVAL", 0),
            patch(
                "jobboard.integrations.eightfold_catalogue.read_json",
                side_effect=[
                    response(detail(id=456)),
                    listing([]),
                    listing([]),
                    listing([]),
                ],
            ) as read,
        ):
            import_board(self.board.pk)
        self.assertIn("position_id=456", read.call_args_list[0].args[0])
        self.schedule.refresh_from_db()
        self.assertEqual(self.schedule.collection_checkpoint, {})
        self.assertEqual(
            OfferSource.objects.filter(
                board=self.board, source_status="active"
            ).count(),
            2,
        )

    def test_lost_lease_does_not_commit_progress_or_rows(self):
        def read(url, **kwargs):
            if "position_details" in url:
                BoardSchedule.objects.filter(pk=self.schedule.pk).update(
                    lease_token=None
                )
                return response(detail())
            return listing([detail()])

        with (
            patch("jobboard.integrations.eightfold_catalogue.REQUEST_INTERVAL", 0),
            patch(
                "jobboard.integrations.eightfold_catalogue.read_json",
                side_effect=read,
            ),
            self.assertRaises(CatalogueImportError),
        ):
            import_board(self.board.pk)
        self.schedule.refresh_from_db()
        self.assertEqual(self.schedule.collection_checkpoint, {})
        self.assertFalse(OfferSource.objects.filter(board=self.board).exists())
