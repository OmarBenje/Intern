import json
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from jobboard.integrations.greenhouse_catalogue import CatalogueImportError
from jobboard.integrations.jobspy_catalogue import collect as collect_jobspy
from jobboard.integrations.jobspy_runner import UpstreamError, observe_indeed_response
from jobboard.integrations.public_catalogue import fetch_smartrecruiters
from jobboard.integrations.wttj_catalogue import source_record
from jobboard.models import DiscoveryQuery
from jobboard.services.engine_search_discovery import run_search_discovery
from jobboard.tests.test_smartrecruiters import listing, posting
from jobboard.tests.test_wttj_collection import hit


class RecoveryTests(SimpleTestCase):
    def test_wttj_dotted_slug_and_unsafe_path(self):
        self.assertIn(
            "/backbone.consulting/",
            source_record(
                hit(organization={"name": "Backbone", "slug": "backbone.consulting"})
            )["url"],
        )
        for slug in ["../escape", "company/path", "company?redirect=x", "%2Fescape"]:
            with self.assertRaises(CatalogueImportError):
                source_record(hit(organization={"name": "Example", "slug": slug}))

    def test_changed_total_retains_verified_rows_as_partial(self):
        a, b = posting(), posting("456")
        with patch(
            "jobboard.integrations.public_catalogue.read_json",
            side_effect=[listing(a, total=3), listing(b, total=2, offset=1), a, b],
        ):
            snapshot = fetch_smartrecruiters("Example")
        self.assertEqual(len(snapshot), 2)
        self.assertFalse(snapshot.complete)
        self.assertIn({"code": "snapshot_changed"}, snapshot.errors)

    def test_overfull_page_cannot_be_authoritative(self):
        a, b = posting(), posting("456")
        with patch(
            "jobboard.integrations.public_catalogue.read_json",
            side_effect=[listing(a, b, total=1), a, b],
        ):
            snapshot = fetch_smartrecruiters("Example")
        self.assertFalse(snapshot.complete)
        self.assertEqual(len(snapshot), 2)

    def test_repeated_listing_is_partial_without_repeated_details(self):
        a = posting()
        with patch(
            "jobboard.integrations.public_catalogue.read_json",
            side_effect=[listing(a, total=2), listing(a, total=2, offset=1), a],
        ):
            snapshot = fetch_smartrecruiters("Example")
        self.assertEqual(len(snapshot), 1)
        self.assertFalse(snapshot.complete)

    def test_indeed_empty_requires_valid_successful_response(self):
        response = SimpleNamespace(
            status_code=200,
            headers={},
            json=lambda: {
                "data": {"jobSearch": {"results": [], "pageInfo": {"nextCursor": None}}}
            },
        )
        self.assertTrue(observe_indeed_response(response))
        response.status_code = 429
        response.headers = {"Retry-After": "7200"}
        with self.assertRaises(UpstreamError) as caught:
            observe_indeed_response(response)
        self.assertEqual(caught.exception.retry_after, 7200)
        response.status_code = 200
        response.json = lambda: {"errors": [{"message": "unavailable"}]}
        with self.assertRaises(UpstreamError):
            observe_indeed_response(response)

    def test_subprocess_empty_and_upstream_error_are_distinct(self):
        with patch(
            "jobboard.integrations.jobspy_catalogue.subprocess.run",
            return_value=SimpleNamespace(
                returncode=0, stdout=json.dumps({"rows": [], "empty_confirmed": True})
            ),
        ):
            self.assertEqual(collect_jobspy("indeed", "FR", "stage"), [])
        with (
            patch(
                "jobboard.integrations.jobspy_catalogue.subprocess.run",
                return_value=SimpleNamespace(
                    returncode=0,
                    stdout=json.dumps(
                        {"error": "jobspy_rate_limited", "retry_after": 7200}
                    ),
                ),
            ),
            self.assertRaises(CatalogueImportError) as caught,
        ):
            collect_jobspy("indeed", "FR", "stage")
        self.assertEqual(caught.exception.retry_after, 7200)


class LinkedinCooldownTests(TestCase):
    def test_rate_limit_defers_all_linkedin_queries_only(self):
        first = DiscoveryQuery.objects.create(
            provider="linkedin_public", country="FR", language="fr", term="stage"
        )
        second = DiscoveryQuery.objects.create(
            provider="linkedin_public", country="DE", language="de", term="Praktikum"
        )
        unrelated = DiscoveryQuery.objects.create(
            provider="arbeitnow", country="DE", language="de"
        )
        error = CatalogueImportError("linkedin_rate_limited")
        error.retry_after = 7200
        with patch(
            "jobboard.services.engine_search_discovery.fetch_page", side_effect=error
        ):
            run_search_discovery(limit=1, provider="linkedin_public")
        for query in [first, second]:
            query.refresh_from_db()
            self.assertGreater(
                query.next_run_at, timezone.now() + timedelta(minutes=119)
            )
        unrelated.refresh_from_db()
        self.assertLess(unrelated.next_run_at, timezone.now())
