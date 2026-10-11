from datetime import timedelta
from types import SimpleNamespace

from django.test import TestCase
from django.utils import timezone

from jobboard.models import (
    Company,
    DiscoveryQuery,
    Offer,
    OfferMergeDecision,
    SourceBoard,
)
from jobboard.services.engine_coverage import query_state
from jobboard.services.engine_merges import (
    canonical_job_url,
    merge,
    propose_link_merges,
    reverse_merge,
)
from jobboard.tests.engine_fixtures import publishable


class CoverageTests(TestCase):
    def test_query_states_are_not_exhaustiveness(self):
        now = timezone.now()
        q = SimpleNamespace(
            enabled=True,
            lease_expires_at=None,
            last_error_code="",
            truncated=False,
            next_run_at=now,
            cursor="2",
            last_success_at=now,
        )
        self.assertEqual(query_state(q, now), "remaining")
        q.last_error_code = "rate_limited"
        self.assertEqual(query_state(q, now), "error")
        q.enabled = False
        self.assertEqual(query_state(q, now), "disabled")
        q.enabled, q.last_error_code, q.truncated = True, "", True
        self.assertEqual(query_state(q, now), "truncated")
        q.truncated, q.cursor = False, ""
        self.assertEqual(query_state(q, now), "cycle_finished")
        q.next_run_at = now - timedelta(hours=2)
        self.assertEqual(query_state(q, now), "overdue")

    def test_publication_and_provider_counts_exclude_stale_sources(self):
        company = Company.objects.create(name="Coverage")
        publishable(
            Offer.objects.create(
                company=company, title="Internship", description="Example"
            )
        )
        publishable(
            Offer.objects.create(
                company=company,
                title="Expired",
                description="Example",
                expires_at=timezone.now() - timedelta(days=1),
            )
        )
        stale = publishable(
            Offer.objects.create(company=company, title="Stale", description="Example")
        )
        stale.sources.update(last_checked_at=timezone.now() - timedelta(days=10))
        DiscoveryQuery.objects.create(
            provider="bundesagentur",
            country="DE",
            language="de",
            term="Praktikum",
            cursor="3",
        )
        data = self.client.get("/api/v1/coverage/").json()
        self.assertEqual(data["published_offers"], 1)
        self.assertEqual(
            next(p for p in data["providers"] if p["provider"] == "greenhouse")[
                "offers"
            ],
            1,
        )
        self.assertEqual(
            next(p for p in data["providers"] if p["provider"] == "bundesagentur")[
                "queries"
            ],
            {"remaining": 1},
        )
        self.assertNotIn("query_details", data)


class LinkMergeTests(TestCase):
    def setUp(self):
        company = Company.objects.create(name="Exact Employer")
        self.offers = [
            publishable(
                Offer.objects.create(
                    company=company,
                    title="Stage marketing",
                    description="Full internship description. " * 10,
                )
            )
            for _ in range(2)
        ]
        board = SourceBoard.objects.create(
            company=company, provider="lever", board_key="exact"
        )
        a, b = [o.sources.get() for o in self.offers]
        a.origin_url, a.apply_url = (
            "https://employer.example/jobs/123?utm_source=board",
            "https://employer.example/jobs/123",
        )
        a.save()
        b.board, b.origin_url, b.apply_url = (
            board,
            "https://aggregator.example/job/42",
            "https://employer.example/jobs/123?utm_campaign=feed",
        )
        b.save()

    def test_tracking_merge_is_reversible(self):
        self.assertEqual(propose_link_merges(), 1)
        decision = OfferMergeDecision.objects.get()
        merge(decision.pk)
        self.assertEqual(self.offers[0].sources.count(), 2)
        self.assertEqual(
            self.client.get("/api/v1/coverage/").json()["published_offers"], 1
        )
        reverse_merge(decision.pk)
        self.assertEqual(self.offers[1].sources.count(), 1)

    def test_identity_parameters_and_generic_urls_are_preserved(self):
        self.assertNotEqual(
            canonical_job_url("https://example.org/job?id=1"),
            canonical_job_url("https://example.org/job?id=2"),
        )
        self.assertIsNone(canonical_job_url("https://example.org/careers?utm_source=x"))
        self.assertIsNone(canonical_job_url("https://user:password@example.org/job"))

    def test_different_dates_or_changed_content_prevent_merge(self):
        self.offers[1].expires_at = timezone.now() + timedelta(days=1)
        self.offers[1].save()
        self.assertEqual(propose_link_merges(), 0)
        self.offers[1].expires_at = None
        self.offers[1].save()
        propose_link_merges()
        self.offers[1].description = "Changed after proposal"
        self.offers[1].save()
        with self.assertRaises(ValueError):
            merge(OfferMergeDecision.objects.get().pk)

    def test_reference_conflict_and_title_only_do_not_merge(self):
        for offer, ref in zip(self.offers, ["a", "b"]):
            offer.sources.update(external_requisition_id=ref)
        self.assertEqual(propose_link_merges(), 0)

    def test_bundesagentur_reference_with_dot(self):
        from jobboard.integrations.bundesagentur_catalogue import public_url

        self.assertTrue(public_url("14551-k28417.429-S").endswith("14551-k28417.429-S"))
