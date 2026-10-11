import json
import subprocess
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from jobboard.integrations.greenhouse_catalogue import CatalogueImportError
from jobboard.integrations.jobspy_catalogue import collect, normalize_record
from jobboard.integrations.public_catalogue import CatalogueSnapshot
from jobboard.models import (
    BoardSchedule,
    DiscoveryQuery,
    DiscoveryResult,
    Offer,
    OfferSource,
    SourceBoard,
)
from jobboard.services.ats_registry import import_registry
from jobboard.services.catalogue import import_board
from jobboard.services.engine_collection import schedule_due
from jobboard.services.jobspy_collection import ingest, run_queries, seed_queries


def record(**overrides):
    return {
        "id": "li-123",
        "title": "Software Engineering Internship",
        "company": "Example Employer",
        "url": "https://www.linkedin.com/jobs/view/example-123?trackingId=abc",
        "direct_url": None,
        "description": "A six month internship developing software with our engineering team.",
        "location": "Paris, Île-de-France, France",
        "country": "France",
        "job_types": ["internship"],
        "remote": False,
        **overrides,
    }


class JobSpyNormalizationTests(SimpleTestCase):
    def test_public_identity_and_explicit_country(self):
        row, facts = normalize_record(record(), "linkedin")
        self.assertEqual(row["external_id"], "123")
        self.assertEqual(row["url"], "https://www.linkedin.com/jobs/view/123")
        self.assertEqual(row["location_details"][0]["country"], "FR")
        self.assertEqual(facts["classification"], "confirmed")

    def test_no_query_country_fallback_remote_or_false_contracts(self):
        for raw in [
            record(country="", location="Paris"),
            record(country="US", location="Paris, TX, US"),
            record(remote=True),
            record(title="Software Engineering Apprenticeship"),
            record(title="Working Student"),
        ]:
            self.assertIsNone(normalize_record(raw, "linkedin")[0])
        self.assertEqual(
            normalize_record(
                record(country="worldwide", location="London, United Kingdom"),
                "linkedin",
            )[0]["location_details"][0]["country"],
            "GB",
        )

    def test_missing_description_and_foreign_url_rejected(self):
        for raw in [
            record(description=None),
            record(description="Intern"),
            record(url="https://evil.test/jobs/view/123"),
            record(url="https://www.linkedin.com@evil.test/jobs/view/123"),
        ]:
            with self.assertRaises(CatalogueImportError):
                normalize_record(raw, "linkedin")

    def test_indeed_source_country_and_id(self):
        row, _ = normalize_record(
            record(
                url="https://fr.indeed.com/viewjob?jk=abcd&tracking=foo", country="FR"
            ),
            "indeed",
        )
        self.assertEqual(row["external_id"], "abcd")
        self.assertEqual(row["url"], "https://www.indeed.com/viewjob?jk=abcd")

    @patch("jobboard.integrations.jobspy_catalogue.subprocess.run")
    def test_bounded_subprocess_and_no_seven_day_window(self, run):
        run.return_value = SimpleNamespace(
            returncode=0, stdout=json.dumps([record()]), stderr=""
        )
        self.assertEqual(len(collect("linkedin", "FR", "stage", offset=20, limit=5)), 1)
        options = json.loads(run.call_args.kwargs["input"])
        self.assertEqual(options["offset"], 20)
        self.assertEqual(run.call_args.kwargs["timeout"], 180)
        self.assertNotIn("hours_old", options)
        with self.assertRaises(CatalogueImportError):
            collect("linkedin", "US", "internship")

    @patch("jobboard.integrations.jobspy_catalogue.subprocess.run")
    def test_empty_error_timeout_and_bad_json_are_not_success(self, run):
        for response in [
            SimpleNamespace(returncode=0, stdout="[]"),
            SimpleNamespace(returncode=1, stdout=""),
            SimpleNamespace(returncode=0, stdout="bad"),
        ]:
            run.return_value = response
            with self.assertRaises(CatalogueImportError):
                collect("indeed", "FR", "stage")
        run.side_effect = subprocess.TimeoutExpired("jobspy", 180)
        with self.assertRaises(CatalogueImportError):
            collect("linkedin", "FR", "stage")


class JobSpyCollectionTests(TestCase):
    def setUp(self):
        seed_queries(["FR"], ["linkedin"])
        self.query = DiscoveryQuery.objects.get(provider="jobspy_linkedin")

    def test_ingestion_is_idempotent_across_queries_and_keeps_unknown(self):
        ingest(self.query, [record(), record()])
        seed_queries(["GB"], ["linkedin"])
        ingest(DiscoveryQuery.objects.get(country="GB"), [record()])
        self.assertEqual(Offer.objects.count(), 1)
        self.assertEqual(OfferSource.objects.count(), 1)
        self.assertEqual(Offer.objects.get().company.name, "Example Employer")
        ingest(
            self.query,
            [
                record(
                    url="https://www.linkedin.com/jobs/view/456",
                    location="Paris",
                    country="",
                )
            ],
        )
        self.assertTrue(DiscoveryResult.objects.filter(status="uncertain").exists())
        self.assertEqual(Offer.objects.count(), 1)

    def test_jobspy_boards_never_enter_board_polling_and_require_partial_input(self):
        ingest(self.query, [record()])
        board = SourceBoard.objects.get()
        BoardSchedule.objects.filter(board=board).update(
            next_run_at=timezone.now() - timedelta(minutes=1)
        )
        self.assertEqual(schedule_due(), 0)
        with self.assertRaises(CatalogueImportError):
            import_board(board.pk)
        BoardSchedule.objects.filter(board=board).update(
            lease_token=None, lease_expires_at=None
        )
        with self.assertRaises(CatalogueImportError):
            import_board(board.pk, supplied_snapshot=CatalogueSnapshot([]))
        import_board(board.pk, supplied_snapshot=CatalogueSnapshot([], complete=False))
        self.assertEqual(OfferSource.objects.get().source_status, "active")

    def test_disabled_source_not_reenabled(self):
        ingest(self.query, [record()])
        SourceBoard.objects.update(enabled=False)
        ingest(self.query, [record()])
        self.assertFalse(SourceBoard.objects.get().enabled)
        self.assertEqual(DiscoveryResult.objects.get().status, "source_disabled")

    @patch("jobboard.services.jobspy_collection.collect")
    def test_cursor_and_empty_failure_preserve_existing_offers(self, collect):
        collect.return_value = [record()]
        run_queries(query_id=self.query.pk)
        self.query.refresh_from_db()
        self.assertEqual(self.query.cursor, "1")
        last_success = self.query.last_success_at
        DiscoveryQuery.objects.filter(pk=self.query.pk).update(
            next_run_at=timezone.now()
        )
        collect.side_effect = CatalogueImportError("jobspy_empty_unconfirmed")
        run_queries(query_id=self.query.pk)
        self.query.refresh_from_db()
        self.assertEqual(self.query.last_success_at, last_success)
        self.assertEqual(self.query.last_error_code, "jobspy_empty_unconfirmed")
        self.assertEqual(OfferSource.objects.get().source_status, "active")

    @patch("jobboard.services.jobspy_collection.collect")
    def test_lost_lease_cannot_publish(self, collect):
        def response(*args):
            DiscoveryQuery.objects.filter(pk=self.query.pk).update(lease_token=None)
            return [record()]

        collect.side_effect = response
        run_queries(query_id=self.query.pk)
        self.assertFalse(Offer.objects.exists())


class RegistryTests(TestCase):
    @patch("jobboard.services.ats_registry.read_inventory")
    def test_registry_keeps_provenance_deduplicates_and_validates_provider(self, read):
        read.return_value = (
            "https://raw.githubusercontent.com/registry.csv",
            "abc",
            [
                {
                    "name": "Example",
                    "slug": "example",
                    "url": "https://jobs.lever.co/example",
                },
                {"name": "Bad", "url": "https://evil.test/example"},
                {"name": "Wrong provider", "url": "https://jobs.ashbyhq.com/example"},
            ],
        )
        report = import_registry(["lever"])
        self.assertEqual(report["registered"], 1)
        self.assertEqual(report["invalid"], 2)
        self.assertEqual(SourceBoard.objects.count(), 0)
        import_registry(["lever"])
        result = DiscoveryResult.objects.get()
        self.assertEqual(result.payload["sha256"], "abc")
        self.assertFalse(result.query.enabled)

    @patch("jobboard.services.ats_registry.read_inventory")
    def test_registry_offset_is_resumable(self, read):
        read.return_value = (
            "https://raw.githubusercontent.com/registry.csv",
            "abc",
            [
                {"name": "First", "url": "https://jobs.lever.co/first"},
                {"name": "Second", "url": "https://jobs.lever.co/second"},
            ],
        )
        report = import_registry(["lever"], limit=1)
        self.assertEqual(report["next_offset"], 1)
        import_registry(["lever"], limit=1, offset=1)
        self.assertEqual(DiscoveryResult.objects.count(), 2)
