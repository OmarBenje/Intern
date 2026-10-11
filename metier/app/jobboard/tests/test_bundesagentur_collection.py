from datetime import timedelta
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from jobboard.integrations.bundesagentur_catalogue import (
    BundesagenturPage,
    collect,
    normalize_record,
    profile_record,
)
from jobboard.integrations.greenhouse_catalogue import CatalogueImportError
from jobboard.models import DiscoveryQuery, OfferSource
from jobboard.services.bundesagentur_collection import run_queries, seed_queries
from jobboard.services.jobspy_collection import ingest


def record(**changes):
    return dict(
        {
            "id": "10001-123-S",
            "url": "https://www.arbeitsagentur.de/jobsuche/jobdetail/10001-123-S",
            "company": "Example BA",
            "title": "Praktikum Marketing",
            "description": "During this internship you will work on marketing and research with our team.",
            "category": "PRAKTIKUM_TRAINEE",
            "locations": [{"city": "Berlin", "country": "DEUTSCHLAND"}],
            "publication_window": {
                "bis": (timezone.now() + timedelta(days=30)).date().isoformat()
            },
        },
        **changes,
    )


class BundesagenturNormalizationTests(SimpleTestCase):
    def test_country_evidence_not_query_or_city(self):
        self.assertEqual(
            normalize_record(record())[0]["location_details"][0]["country"], "DE"
        )
        for country in ["", "USA", "UNKNOWN"]:
            self.assertIsNone(
                normalize_record(
                    record(locations=[{"city": "Berlin", "country": country}])
                )[0]
            )

    def test_shared_category_and_incidental_mentions_do_not_prove_internship(self):
        for title in [
            "Werkstudent Marketing",
            "Sales Trainee",
            "Graduate Program",
            "Senior Developer",
        ]:
            self.assertIsNone(normalize_record(record(title=title))[0])
        self.assertIsNone(normalize_record(record(category="ARBEIT"))[0])
        self.assertIsNone(normalize_record(record(title="Remote Internship"))[0])

    def test_expired_future_and_malformed_dates(self):
        for window in [
            {"bis": "2020-01-01"},
            {"von": "2099-01-01"},
            {"bis": "invalid"},
        ]:
            with self.assertRaises(CatalogueImportError):
                normalize_record(record(publication_window=window))
        self.assertIsNotNone(normalize_record(record(publication_window={}))[0])

    def test_identity_and_minimized_locations(self):
        d = {
            "referenznummer": "10001-123-S",
            "firma": "Example",
            "stellenlokationen": [
                {
                    "adresse": {
                        "ort": "Berlin",
                        "land": "DEUTSCHLAND",
                        "strasse": "Private",
                    }
                }
            ],
            "kontakt": {"email": "private@example.org"},
        }
        self.assertNotIn("Private", str(profile_record("10001-123-S", d)))
        with self.assertRaises(CatalogueImportError):
            profile_record("other", d)

    def test_detail_404_advances_but_rate_limit_does_not(self):
        for error in ["bundesagentur_not_found", "bundesagentur_rate_limited"]:
            with patch(
                "jobboard.integrations.bundesagentur_catalogue.request_json",
                side_effect=[
                    {
                        "maxErgebnisse": 1,
                        "ergebnisliste": [{"referenznummer": "10001-123-S"}],
                    },
                    CatalogueImportError(error),
                ],
            ):
                if error.endswith("not_found"):
                    self.assertEqual(collect("Praktikum").records[0]["error"], error)
                else:
                    with self.assertRaises(CatalogueImportError):
                        collect("Praktikum")

    def test_search_filter_base64_and_empty(self):
        with patch(
            "jobboard.integrations.bundesagentur_catalogue.request_json",
            return_value={"maxErgebnisse": 0, "ergebnisliste": []},
        ) as read:
            self.assertEqual(collect("Praktikum").records, [])
        self.assertIn("angebotsart=34", read.call_args.args[0])
        with patch(
            "jobboard.integrations.bundesagentur_catalogue.request_json",
            side_effect=[
                {
                    "maxErgebnisse": 1,
                    "ergebnisliste": [{"referenznummer": "10001-123-S"}],
                },
                {"referenznummer": "10001-123-S", "stellenlokationen": []},
            ],
        ) as read:
            collect("Praktikum")
        self.assertIn("MTAwMDEtMTIzLVM%3D", read.call_args.args[0])

    def test_missing_page_not_silent_success(self):
        with (
            patch(
                "jobboard.integrations.bundesagentur_catalogue.request_json",
                return_value={"maxErgebnisse": 10, "ergebnisliste": []},
            ),
            self.assertRaises(CatalogueImportError),
        ):
            collect("Praktikum")


class BundesagenturCollectionTests(TestCase):
    def setUp(self):
        seed_queries(["DE"])
        self.query = DiscoveryQuery.objects.get(
            provider="bundesagentur", term="Praktikum"
        )

    def test_idempotence_expiry_and_retraction(self):
        raw = record()
        ingest(self.query, [raw])
        ingest(self.query, [raw])
        source = OfferSource.objects.get(board__provider="bundesagentur")
        self.assertIsNotNone(source.offer.expires_at)
        self.assertEqual(source.offer.enrichment.classification, "confirmed")
        ingest(self.query, [record(error="bundesagentur_not_found")])
        source.refresh_from_db()
        self.assertEqual(source.source_status, "unknown")

    def test_cursor_retry_and_lease(self):
        with patch(
            "jobboard.services.bundesagentur_collection.collect",
            return_value=BundesagenturPage([record()], "2", 26),
        ):
            self.assertEqual(run_queries(query_id=self.query.pk)[0]["imported"], 1)
        self.query.refresh_from_db()
        self.assertEqual(self.query.total_available, 26)
        DiscoveryQuery.objects.filter(pk=self.query.pk).update(
            next_run_at=timezone.now()
        )
        with patch(
            "jobboard.services.bundesagentur_collection.collect",
            side_effect=CatalogueImportError("upstream_rate_limited"),
        ):
            run_queries(query_id=self.query.pk)
        self.query.refresh_from_db()
        self.assertEqual(self.query.cursor, "2")
        self.assertIsNone(self.query.lease_token)

    def test_lost_lease_cannot_import(self):
        def steal(*args):
            DiscoveryQuery.objects.filter(pk=self.query.pk).update(
                lease_expires_at=timezone.now() - timedelta(seconds=1)
            )
            return BundesagenturPage([record()], "", 1)

        with patch(
            "jobboard.services.bundesagentur_collection.collect", side_effect=steal
        ):
            self.assertEqual(
                run_queries(query_id=self.query.pk)[0]["error"], "lease_lost"
            )
        self.assertFalse(OfferSource.objects.exists())
