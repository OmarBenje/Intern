from datetime import timedelta
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from jobboard.integrations.eures_catalogue import (
    EuresPage,
    collect,
    normalize_record,
    profile_record,
)
from jobboard.integrations.greenhouse_catalogue import CatalogueImportError
from jobboard.models import DiscoveryQuery, OfferSource, SourceBoard
from jobboard.services.eures_collection import run_queries, seed_queries
from jobboard.services.jobspy_collection import ingest


def record(**changes):
    return dict(
        {
            "id": "ABC123",
            "url": "https://europa.eu/eures/portal/jv-se/jv-details/ABC123?lang=en",
            "company": "Example EURES",
            "title": "Marketing internship",
            "description": "A six month internship supporting research and marketing campaigns.",
            "positionOfferingCode": "internship",
            "locations": [{"cityName": "Berlin", "countryCode": "de"}],
        },
        **changes,
    )


class EuresNormalizationTests(SimpleTestCase):
    def test_country_and_contract_are_source_evidence(self):
        row, facts = normalize_record(record())
        self.assertEqual(facts["europe_status"], "in_scope")
        self.assertEqual(row["location_details"][0]["country"], "DE")
        for offering in [
            "apprenticeship",
            "trainee",
            "traineeship",
            "directhire",
            None,
        ]:
            self.assertIsNone(
                normalize_record(record(positionOfferingCode=offering))[0]
            )
        self.assertIsNone(
            normalize_record(
                record(locations=[{"countryCode": "US", "cityName": "Boston"}])
            )[0]
        )
        self.assertIsNone(
            normalize_record(record(locations=[{"cityName": "Berlin"}]))[0]
        )

    def test_noisy_eures_internship_label_is_not_sufficient(self):
        for title in [
            "Sales Trainee",
            "Seconded National Expert",
            "Werksstudent Government Relations",
            "Liikenneopettajaksi oppisopimuksella",
        ]:
            row, _ = normalize_record(
                record(
                    title=title,
                    description="A position in our European office. Please apply today.",
                )
            )
            self.assertIsNone(row)

    def test_anonymous_and_incomplete_rejected(self):
        for changes in [
            {"company": "non renseigné"},
            {"description": ""},
            {"id": "../secret"},
            {"locations": "DE"},
        ]:
            with self.assertRaises(CatalogueImportError):
                normalize_record(record(**changes))

    def test_detail_identity_and_no_contacts(self):
        profile = {
            "title": "Internship",
            "employer": {"name": "Example"},
            "personContacts": [{"email": "private@example.org"}],
            "description": "Job",
        }
        raw = profile_record(
            {"id": "ABC"},
            {"id": "ABC", "preferredLanguage": "de", "jvProfiles": {"de": profile}},
        )
        self.assertNotIn("personContacts", raw)
        with self.assertRaises(CatalogueImportError):
            profile_record({"id": "ABC"}, {"id": "DEF"})

    def test_search_filter_and_confirmed_empty(self):
        with patch(
            "jobboard.integrations.eures_catalogue.request_json",
            return_value={"numberRecords": 0, "jvs": []},
        ) as read:
            page = collect("GR")
        self.assertEqual(page.records, [])
        self.assertEqual(read.call_args.kwargs["body"]["locationCodes"], ["el"])
        self.assertEqual(
            read.call_args.kwargs["body"]["positionOfferingCodes"], ["internship"]
        )
        self.assertEqual(page.next_cursor, "")

    def test_detail_failure_is_not_empty_success(self):
        with (
            patch(
                "jobboard.integrations.eures_catalogue.request_json",
                side_effect=[
                    {"numberRecords": 1, "jvs": [{"id": "ABC"}]},
                    CatalogueImportError("eures_rate_limited"),
                ],
            ),
            self.assertRaisesMessage(CatalogueImportError, "eures_rate_limited"),
        ):
            collect("DE")
        with (
            patch(
                "jobboard.integrations.eures_catalogue.request_json",
                return_value={"numberRecords": 10, "jvs": []},
            ),
            self.assertRaisesMessage(CatalogueImportError, "eures_incomplete_page"),
        ):
            collect("DE")


class EuresCollectionTests(TestCase):
    def setUp(self):
        seed_queries(["DE"])
        self.query = DiscoveryQuery.objects.get(provider="eures")

    def test_import_is_idempotent_across_pages_and_partial(self):
        self.assertEqual(ingest(self.query, [record()]), 1)
        self.assertEqual(ingest(self.query, [record()]), 1)
        self.assertEqual(OfferSource.objects.filter(board__provider="eures").count(), 1)
        ingest(self.query, [])
        source = OfferSource.objects.get(board__provider="eures")
        self.assertEqual(source.source_status, "active")
        self.assertEqual(source.offer.enrichment.europe_status, "in_scope")
        self.assertEqual(self.query.results.get().status, "imported")

    def test_cursor_success_and_failure_retry(self):
        with patch(
            "jobboard.services.eures_collection.collect",
            return_value=EuresPage([record()], "2", 30),
        ):
            result = run_queries()
        self.assertEqual(result[0]["imported"], 1)
        self.query.refresh_from_db()
        self.assertEqual(self.query.cursor, "2")
        success = self.query.last_success_at
        DiscoveryQuery.objects.filter(pk=self.query.pk).update(
            next_run_at=timezone.now()
        )
        with patch(
            "jobboard.services.eures_collection.collect",
            side_effect=CatalogueImportError("eures_http_error"),
        ):
            run_queries()
        self.query.refresh_from_db()
        self.assertEqual(self.query.cursor, "2")
        self.assertEqual(self.query.last_success_at, success)
        self.assertEqual(self.query.last_error_code, "eures_http_error")
        self.assertIsNone(self.query.lease_token)

    def test_unqualified_update_hides_previous_copy(self):
        ingest(self.query, [record()])
        ingest(self.query, [record(positionOfferingCode="apprenticeship")])
        self.assertEqual(
            OfferSource.objects.get(board__provider="eures").source_status, "unknown"
        )

    def test_stale_lease_cannot_import(self):
        def steal(*args):
            DiscoveryQuery.objects.filter(pk=self.query.pk).update(
                lease_expires_at=timezone.now() - timedelta(seconds=1)
            )
            return EuresPage([record()], "", 1)

        with patch("jobboard.services.eures_collection.collect", side_effect=steal):
            result = run_queries()
        self.assertEqual(result[0]["error"], "lease_lost")
        self.assertEqual(OfferSource.objects.count(), 0)

    def test_disabled_board_and_other_workers(self):
        ingest(self.query, [record()])
        board = SourceBoard.objects.get(provider="eures")
        board.enabled = False
        board.save()
        ingest(self.query, [record()])
        self.assertEqual(self.query.results.get().status, "source_disabled")
