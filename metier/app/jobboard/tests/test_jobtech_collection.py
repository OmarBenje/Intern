from datetime import timedelta
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from jobboard.integrations.greenhouse_catalogue import CatalogueImportError
from jobboard.integrations.jobtech_catalogue import (
    JobtechPage,
    collect,
    normalize_record,
    profile_record,
)
from jobboard.models import DiscoveryQuery, OfferSource
from jobboard.services.jobspy_collection import ingest
from jobboard.services.jobtech_collection import run_queries, seed_queries


def record(**changes):
    return dict(
        {
            "id": "12345",
            "url": "https://arbetsformedlingen.se/platsbanken/annonser/12345",
            "company": "Example JobTech",
            "title": "Marketing internship",
            "description": "An internship working on marketing and research with our Stockholm team.",
            "locations": [
                {"country": "Sverige", "country_code": "199", "city": "Stockholm"}
            ],
            "removed": False,
            "deadline": (timezone.now() + timedelta(days=30)).isoformat(),
        },
        **changes,
    )


class JobtechNormalizationTests(SimpleTestCase):
    def test_taxonomy_is_not_iso_or_query_country(self):
        row, _ = normalize_record(record())
        self.assertEqual(row["location_details"][0]["country"], "SE")
        for location in [
            {"country": "Sverige"},
            {"country_code": "199"},
            {"country": "USA", "country_code": "US", "city": "Boston"},
        ]:
            self.assertIsNone(normalize_record(record(locations=[location]))[0])

    def test_swedish_proof_and_non_internships(self):
        row, _ = normalize_record(
            record(
                title="Praktik inom marknadsföring",
                description="Under praktikperioden arbetar du tillsammans med vårt team i Stockholm.",
            )
        )
        self.assertIsNotNone(row)
        for title, text in [
            (
                "Senior marketing manager",
                "You will supervise interns during their internship.",
            ),
            (
                "LIA consultant",
                "An experienced consultant working with many different customers.",
            ),
            (
                "Praktik",
                "A company providing many different services for customers in Sweden.",
            ),
        ]:
            self.assertIsNone(
                normalize_record(record(title=title, description=text))[0]
            )

    def test_swedish_remote_does_not_infer_eligibility_from_office(self):
        self.assertIsNone(
            normalize_record(
                record(
                    title="Praktikant 100 % distans",
                    description="Under praktikperioden arbetar du tillsammans med vårt team i Stockholm.",
                )
            )[0]
        )

    def test_removed_expired_and_missing_deadline_rejected(self):
        for changes in [
            {"removed": True},
            {"removed": None},
            {"deadline": None},
            {"deadline": (timezone.now() - timedelta(days=1)).isoformat()},
        ]:
            with self.assertRaises(CatalogueImportError):
                normalize_record(record(**changes))

    def test_identity_and_contact_minimization(self):
        detail = {
            "id": "123",
            "headline": "Internship",
            "employer": {"name": "Example", "email": "private@example.org"},
            "description": {"text": "Description"},
            "application_contacts": [{"name": "Private"}],
        }
        self.assertNotIn("private", str(profile_record("123", detail)).lower())
        with self.assertRaises(CatalogueImportError):
            profile_record("124", detail)

    def test_empty_and_failed_detail(self):
        with patch(
            "jobboard.integrations.jobtech_catalogue.read_json",
            return_value={"total": {"value": 0}, "hits": []},
        ):
            self.assertEqual(collect("internship").next_cursor, "")
        with (
            patch(
                "jobboard.integrations.jobtech_catalogue.read_json",
                side_effect=[
                    {"total": {"value": 1}, "hits": [{"id": "123"}]},
                    CatalogueImportError("upstream_rate_limited"),
                ],
            ),
            self.assertRaisesMessage(CatalogueImportError, "upstream_rate_limited"),
        ):
            collect("internship")

    def test_offset_limit_reports_truncation(self):
        hits = [{"id": str(i)} for i in range(20)]
        with patch(
            "jobboard.integrations.jobtech_catalogue.read_json",
            side_effect=[{"total": {"value": 3000}, "hits": hits}, *hits],
        ):
            result = collect("praktik", 2000)
        self.assertTrue(result.truncated)
        self.assertEqual(result.next_cursor, "")


class JobtechCollectionTests(TestCase):
    def setUp(self):
        seed_queries(["SE"])
        self.query = DiscoveryQuery.objects.get(provider="jobtech", term="internship")

    def test_idempotence_expiry_and_retraction(self):
        raw = record()
        ingest(self.query, [raw])
        ingest(self.query, [raw])
        source = OfferSource.objects.get(board__provider="jobtech")
        self.assertIsNotNone(source.offer.expires_at)
        self.assertEqual(source.offer.enrichment.classification, "confirmed")
        ingest(self.query, [record(removed=True)])
        source.refresh_from_db()
        self.assertEqual(source.source_status, "unknown")

    def test_cursor_retry_and_lease(self):
        with patch(
            "jobboard.services.jobtech_collection.collect",
            return_value=JobtechPage([record()], "20", 26),
        ):
            self.assertEqual(run_queries(query_id=self.query.pk)[0]["imported"], 1)
        self.query.refresh_from_db()
        self.assertEqual(self.query.total_available, 26)
        DiscoveryQuery.objects.filter(pk=self.query.pk).update(
            next_run_at=timezone.now()
        )
        with patch(
            "jobboard.services.jobtech_collection.collect",
            side_effect=CatalogueImportError("upstream_rate_limited"),
        ):
            run_queries(query_id=self.query.pk)
        self.query.refresh_from_db()
        self.assertEqual(self.query.cursor, "20")
        self.assertIsNone(self.query.lease_token)

    def test_lost_lease_cannot_import(self):
        def steal(*args):
            DiscoveryQuery.objects.filter(pk=self.query.pk).update(
                lease_expires_at=timezone.now() - timedelta(seconds=1)
            )
            return JobtechPage([record()], "", 1)

        with patch("jobboard.services.jobtech_collection.collect", side_effect=steal):
            self.assertEqual(
                run_queries(query_id=self.query.pk)[0]["error"], "lease_lost"
            )
        self.assertFalse(OfferSource.objects.exists())
