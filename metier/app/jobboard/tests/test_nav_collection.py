from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from jobboard.integrations.greenhouse_catalogue import CatalogueImportError
from jobboard.integrations.nav_catalogue import (
    NavPage,
    collect,
    normalize_record,
    profile_record,
    public_url,
    request,
)
from jobboard.models import DiscoveryQuery, OfferSource
from jobboard.services.jobspy_collection import ingest
from jobboard.services.nav_collection import run_queries, seed_queries

AD = "066dd2e6-7695-43fd-bd84-6e4482c72e32"
PAGE = "ebb16d90-120b-45d9-812a-0b562678f4d6"


def record(**changes):
    return dict(
        {
            "id": AD,
            "url": public_url(AD),
            "company": "Example NAV",
            "title": "Software internship",
            "description": "A six month internship building tools and working with our team in Norway.",
            "locations": [{"city": "Oslo", "country": "NORGE"}],
            "expires": (timezone.now() + timedelta(days=30)).isoformat(),
            "application_url": "https://employer.example/jobs/123",
        },
        **changes,
    )


def detail(**changes):
    r = record()
    return dict(
        {
            "uuid": AD,
            "status": "ACTIVE",
            "ad_content": {
                "uuid": AD,
                "employer": {"name": r["company"]},
                "title": r["title"],
                "description": r["description"],
                "expires": r["expires"],
                "workLocations": r["locations"],
                "applicationUrl": r["application_url"],
                "contactList": [{"email": "private@example.org"}],
            },
        },
        **changes,
    )


class NavTests(SimpleTestCase):
    def test_country_stage_expiry_and_apply_url(self):
        row, _ = normalize_record(record())
        self.assertEqual(row["location_details"][0]["country"], "NO")
        self.assertEqual(row["apply_url"], "https://employer.example/jobs/123")
        self.assertIsNone(normalize_record(record(locations=[{"city": "Oslo"}]))[0])
        self.assertIsNone(normalize_record(record(title="Graduate Trainee"))[0])
        self.assertIsNone(
            normalize_record(
                record(
                    title="Intern utlysning",
                    description="This is an internal vacancy for existing employees only.",
                )
            )[0]
        )
        with self.assertRaises(CatalogueImportError):
            normalize_record(record(expires="2020-01-01T00:00:00+01:00"))

    def test_minimal_inactive_and_identity(self):
        self.assertEqual(
            profile_record(AD, {"uuid": AD, "status": "INACTIVE"})["error"],
            "nav_inactive",
        )
        self.assertNotIn("contactList", profile_record(AD, detail()))
        with self.assertRaises(CatalogueImportError):
            profile_record(str(uuid4()), detail())

    def test_untrusted_paths_cannot_receive_token(self):
        for path in [
            "https://evil.example/api/v1/feed",
            "/api/v1/feed/../private",
            "//evil.example",
        ]:
            with self.assertRaises(CatalogueImportError):
                request(path, token="secret")

    @patch("jobboard.integrations.nav_catalogue.get_token", return_value="test")
    def test_event_following_uses_ids_and_tail_cursor(self, _):
        payload = {
            "id": PAGE,
            "next_id": None,
            "next_url": "https://evil.example",
            "items": [
                {
                    "_feed_entry": {
                        "uuid": AD,
                        "title": "Software internship",
                        "status": "ACTIVE",
                    }
                },
                {
                    "_feed_entry": {
                        "uuid": AD,
                        "title": "Software internship",
                        "status": "ACTIVE",
                    }
                },
            ],
        }
        with patch(
            "jobboard.integrations.nav_catalogue.read_json",
            side_effect=[payload, detail()],
        ):
            page = collect("2026-09-01")
        self.assertEqual(len(page.records), 1)
        self.assertEqual(page.scanned, 2)
        self.assertEqual(page.next_cursor, "tail:" + PAGE + ":2")
        with patch(
            "jobboard.integrations.nav_catalogue.read_json", return_value=payload
        ):
            self.assertEqual(collect("2026-09-01", page.next_cursor).scanned, 0)

    @patch("jobboard.integrations.nav_catalogue.get_token", return_value="test")
    def test_known_offer_is_checked_after_title_removed(self, _):
        payload = {
            "id": PAGE,
            "next_id": None,
            "items": [
                {"_feed_entry": {"uuid": AD, "title": "...", "status": "INACTIVE"}}
            ],
        }
        with patch(
            "jobboard.integrations.nav_catalogue.read_json",
            side_effect=[payload, {"uuid": AD, "status": "INACTIVE"}],
        ):
            page = collect("2026-09-01", known_ids={AD})
        self.assertEqual(page.records[0]["error"], "nav_inactive")


class NavCollectionTests(TestCase):
    def setUp(self):
        seed_queries(["NO"])
        self.query = DiscoveryQuery.objects.get(provider="nav")

    def test_idempotence_and_removal(self):
        ingest(self.query, [record()])
        ingest(self.query, [record()])
        source = OfferSource.objects.get(board__provider="nav")
        self.assertEqual(source.offer.enrichment.classification, "confirmed")
        ingest(self.query, [{"id": AD, "url": public_url(AD), "error": "nav_inactive"}])
        source.refresh_from_db()
        self.assertEqual(source.source_status, "unknown")

    def test_tail_refresh_and_failure_preserves_cursor(self):
        ingest(self.query, [record()])
        with patch(
            "jobboard.services.nav_collection.collect",
            return_value=NavPage([], "tail:" + PAGE + ":2", scanned=2, at_tail=True),
        ):
            run_queries(query_id=self.query.pk)
        self.query.refresh_from_db()
        cursor = self.query.cursor
        DiscoveryQuery.objects.filter(pk=self.query.pk).update(
            next_run_at=timezone.now()
        )
        with patch(
            "jobboard.services.nav_collection.collect",
            side_effect=CatalogueImportError("nav_network_error"),
        ):
            run_queries(query_id=self.query.pk)
        self.query.refresh_from_db()
        self.assertEqual(self.query.cursor, cursor)
        self.assertEqual(self.query.last_error_code, "nav_network_error")
