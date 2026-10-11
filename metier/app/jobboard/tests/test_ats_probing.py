from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from jobboard.integrations.greenhouse_catalogue import CatalogueImportError
from jobboard.models import AtsProbe, BoardSchedule, SourceCandidate
from jobboard.services.ats_probing import enroll, metrics, qualifies, run_one

MODULE = "jobboard.services.ats_probing"


def payload(location="Paris, France"):
    return {
        "meta": {"total": 1},
        "jobs": [
            {
                "id": 1,
                "title": "Marketing Internship",
                "content": "A six month internship.",
                "absolute_url": "https://job-boards.greenhouse.io/probetest/jobs/1",
                "location": {"name": location},
            }
        ],
    }


class ProbeTests(TestCase):
    def setUp(self):
        self.candidate = SourceCandidate.objects.create(
            url="https://job-boards.greenhouse.io/probetest",
            provider="greenhouse",
            board_key="probetest",
            company_name="Probe Test",
        )

    def test_enroll_is_bounded_idempotent(self):
        self.assertEqual(len(enroll(1)), 1)
        self.assertEqual(enroll(1), [])
        with self.assertRaises(ValueError):
            enroll(101)

    def test_empty_waits_seven_days_without_creating_board(self):
        enroll(1)
        with patch(
            f"{MODULE}.fetch_snapshot", return_value={"meta": {"total": 0}, "jobs": []}
        ):
            self.assertEqual(run_one()["state"], "waiting")
            self.assertIsNone(run_one())
        probe = AtsProbe.objects.get()
        self.assertGreater(probe.next_attempt_at, timezone.now() + timedelta(days=6))
        self.candidate.refresh_from_db()
        self.assertIsNone(self.candidate.board_id)

    def test_all_europe_including_france_activates(self):
        enroll(1)
        with (
            patch(f"{MODULE}.fetch_snapshot", return_value=payload()),
            patch("jobboard.services.catalogue.fetch_snapshot", return_value=payload()),
        ):
            result = run_one()
        self.assertEqual(result["state"], "active")
        self.assertEqual(len(result["visible_offer_ids"]), 1)
        self.assertFalse(BoardSchedule.objects.get().paused)
        self.assertIsNone(run_one())
        self.assertEqual(metrics()["visible_offers"], 1)

    def test_us_internship_does_not_activate(self):
        enroll(1)
        with patch(
            f"{MODULE}.fetch_snapshot", return_value=payload("Boston, United States")
        ):
            self.assertEqual(run_one()["state"], "waiting")
        self.assertFalse(BoardSchedule.objects.exists())

    def test_error_backoff_and_retry(self):
        enroll(1)
        with patch(
            f"{MODULE}.fetch_snapshot",
            side_effect=CatalogueImportError("upstream_invalid_response"),
        ):
            self.assertEqual(run_one()["state"], "error")
            self.assertIsNone(run_one())
        probe = AtsProbe.objects.get()
        self.assertGreater(
            probe.next_attempt_at, timezone.now() + timedelta(minutes=59)
        )
        probe.next_attempt_at = timezone.now() - timedelta(seconds=1)
        probe.save()
        with patch(
            f"{MODULE}.fetch_snapshot", return_value={"meta": {"total": 0}, "jobs": []}
        ):
            self.assertEqual(run_one()["state"], "waiting")
        probe.refresh_from_db()
        self.assertEqual(probe.attempts, 2)
        self.assertEqual(probe.error_code, "")

    def test_crashed_claim_is_recovered_after_lease_only(self):
        enroll(1)
        with (
            patch(
                f"{MODULE}.fetch_snapshot",
                side_effect=KeyboardInterrupt("simulated crash"),
            ),
            self.assertRaises(KeyboardInterrupt),
        ):
            run_one()
        self.assertIsNone(run_one())
        AtsProbe.objects.update(lease_expires_at=timezone.now() - timedelta(seconds=1))
        with patch(
            f"{MODULE}.fetch_snapshot", return_value={"meta": {"total": 0}, "jobs": []}
        ):
            self.assertEqual(run_one()["state"], "waiting")

    def test_structured_country_and_non_stage_gate(self):
        row = {
            "title": "Marketing Internship",
            "description": "Internship.",
            "location_details": [{"name": "Milan", "country": "Italy"}],
        }
        self.assertTrue(qualifies(row))
        self.assertFalse(qualifies(dict(row, title="Senior Marketing Director")))

    def test_stop_during_screening_prevents_activation(self):
        enroll(1)

        def stop_then_return(*args):
            AtsProbe.objects.update(enabled=False)
            return payload()

        with (
            patch(f"{MODULE}.fetch_snapshot", side_effect=stop_then_return),
            patch(f"{MODULE}.register_source") as register,
        ):
            run_one()
        register.assert_not_called()
        self.assertFalse(AtsProbe.objects.get().enabled)
        self.assertEqual(AtsProbe.objects.get().state, "stopped")

    def test_specific_batch_does_not_consume_other_candidates(self):
        ids = enroll(1)
        self.assertIsNone(run_one([ids[0] + 1]))
        self.assertEqual(AtsProbe.objects.get().attempts, 0)
