from datetime import timedelta
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from jobboard.integrations.discovery_feeds import FeedPage, fetch_page
from jobboard.integrations.greenhouse_catalogue import CatalogueImportError
from jobboard.models import (
    DiscoveryQuery,
    DiscoveryResult,
    Offer,
    SourceBoard,
    SourceCandidate,
)
from jobboard.services.engine_search_discovery import (
    candidate_from_url,
    run_search_discovery,
    seed_queries,
)


class FeedTests(SimpleTestCase):
    def test_upstream_next_url_never_followed(self):
        query = DiscoveryQuery(provider="arbeitnow", cursor="1")
        with patch(
            "jobboard.integrations.discovery_feeds.read_json",
            return_value={
                "data": [
                    {
                        "slug": "x",
                        "url": "https://example.com",
                        "company_name": "Example",
                    }
                ],
                "links": {"next": "http://127.0.0.1/secret"},
            },
        ) as fetch:
            page = fetch_page(query, 123)
        self.assertEqual(page.next_cursor, "2")
        self.assertEqual(
            fetch.call_args.args[0],
            "https://www.arbeitnow.com/api/job-board-api?page=1",
        )

    def test_sweden_taxonomy_is_not_iso(self):
        query = DiscoveryQuery(provider="jobsearch_se", country="SE", term="praktik")
        payload = {
            "hits": [
                {
                    "id": "x",
                    "employer": {"name": "Company"},
                    "application_details": {"url": "https://example.com"},
                    "workplace_address": {"country_code": "199"},
                }
            ],
            "total": {"value": 2},
        }
        with patch(
            "jobboard.integrations.discovery_feeds.read_json", return_value=payload
        ):
            page = fetch_page(query, 123)
        self.assertEqual(page.next_cursor, "1")
        self.assertNotIn("country", page.records[0])

    def test_unknown_provider_rejected(self):
        with self.assertRaises(CatalogueImportError):
            fetch_page(DiscoveryQuery(provider="invented"), 123)

    def test_malformed_feed_metadata_is_bounded_failure(self):
        cases = [
            ("arbeitnow", {"data": [], "links": []}),
            ("arbeitnow", {"data": ["bad"], "links": {}}),
            ("jobsearch_se", {"hits": [], "total": {"value": -1}}),
            (
                "jobsearch_se",
                {"hits": [{"id": "x", "employer": "bad"}], "total": {"value": 1}},
            ),
        ]
        # A non-empty malformed links value must be rejected; an absent/empty
        # one is a legitimate terminal page.
        cases[0] = ("arbeitnow", {"data": [], "links": ["bad"]})
        for provider, payload in cases:
            with (
                self.subTest(provider=provider, payload=payload),
                patch(
                    "jobboard.integrations.discovery_feeds.read_json",
                    return_value=payload,
                ),
                self.assertRaises(CatalogueImportError),
            ):
                fetch_page(DiscoveryQuery(provider=provider), 123)


class DiscoveryTests(TestCase):
    def setUp(self):
        self.query = DiscoveryQuery.objects.create(provider="arbeitnow", language="de")
        self.page = FeedPage(
            [
                {
                    "id": "job1",
                    "url": "https://jobs.ashbyhq.com/example/job",
                    "company": "Example",
                    "raw": {"title": "Not necessarily an internship"},
                }
            ],
            "2",
            12,
        )

    def test_pagination_cadence_idempotence_no_publication(self):
        with patch(
            "jobboard.services.engine_search_discovery.fetch_page",
            return_value=self.page,
        ) as fetch:
            self.assertEqual(run_search_discovery(), 1)
            self.assertEqual(run_search_discovery(), 0)
            self.query.refresh_from_db()
            self.assertEqual(self.query.cursor, "2")
            self.assertTrue(self.query.truncated)
            self.assertEqual(self.query.result_count, 1)
            self.assertEqual(Offer.objects.count(), 0)
            self.assertEqual(SourceBoard.objects.count(), 0)
            DiscoveryQuery.objects.update(next_run_at=timezone.now())
            run_search_discovery()
        self.assertEqual(DiscoveryResult.objects.count(), 1)
        self.assertEqual(SourceCandidate.objects.count(), 1)
        self.assertEqual(fetch.call_count, 2)

    def test_live_lease_skips_query(self):
        self.query.lease_expires_at = timezone.now() + timedelta(minutes=5)
        self.query.save()
        with patch("jobboard.services.engine_search_discovery.fetch_page") as fetch:
            self.assertEqual(run_search_discovery(), 0)
        fetch.assert_not_called()

    def test_failure_preserves_cursor_and_backs_off(self):
        self.query.cursor = "3"
        self.query.save()
        with patch(
            "jobboard.services.engine_search_discovery.fetch_page",
            side_effect=CatalogueImportError("upstream_rate_limited"),
        ):
            run_search_discovery()
        self.query.refresh_from_db()
        self.assertEqual(self.query.cursor, "3")
        self.assertEqual(self.query.last_error_code, "upstream_rate_limited")
        self.assertIsNone(self.query.lease_token)
        self.assertGreater(self.query.next_run_at, timezone.now())

    def test_unsupported_provider_is_durable(self):
        candidate = candidate_from_url(
            "https://company.taleo.net/careersection/jobdetail.ftl", "Company"
        )
        self.assertEqual(candidate.status, "unsupported_provider")
        self.assertEqual(candidate.provider, "taleo")
        self.assertEqual(SourceBoard.objects.count(), 0)

    def test_feed_page_only_fetches_exact_public_host(self):
        self.page.records[0]["url"] = "https://www.arbeitnow.com/view/internship"
        with (
            patch(
                "jobboard.services.engine_search_discovery.fetch_page",
                return_value=self.page,
            ),
            patch(
                "jobboard.services.engine_search_discovery.fetch_html",
                return_value=(
                    self.page.records[0]["url"],
                    '<a href="https://jobs.lever.co/example/123">Apply</a>',
                ),
            ) as html,
        ):
            run_search_discovery()
        self.assertEqual(html.call_args.args[1], {"www.arbeitnow.com"})
        self.assertEqual(
            SourceCandidate.objects.get().url, "https://jobs.lever.co/example"
        )

    def test_matrix_is_idempotent_and_sweden_scope_explicit(self):
        seed_queries()
        seed_queries()
        self.assertEqual(DiscoveryQuery.objects.count(), 16)
        self.assertEqual(
            set(
                DiscoveryQuery.objects.filter(provider="jobsearch_se").values_list(
                    "country", flat=True
                )
            ),
            {"SE"},
        )

    def test_auto_activation_is_persisted_and_bounded(self):
        seed_queries(auto_activate=True)
        self.query.refresh_from_db()
        self.assertTrue(self.query.auto_activate)
        extra = {
            **self.page.records[0],
            "id": "job2",
            "url": "https://jobs.ashbyhq.com/other/job",
        }
        self.page.records.append(extra)
        original_register = __import__(
            "jobboard.services.engine_search_discovery", fromlist=["register_source"]
        ).register_source
        calls = []

        def register(url, company, enable=False):
            candidate = original_register(url, company)
            if enable:
                calls.append(url)
                candidate.status = "validated"
                candidate.save(update_fields=["status"])
            return candidate

        # Keep this test to one provider query; default matrix has other due rows.
        with (
            patch(
                "jobboard.services.engine_search_discovery.fetch_page",
                return_value=self.page,
            ),
            patch(
                "jobboard.services.engine_search_discovery.register_source",
                side_effect=register,
            ),
        ):
            run_search_discovery(limit=1, activation_limit=1)
        self.assertEqual(len(calls), 1)
        self.query.refresh_from_db()
        self.assertLess(self.query.next_run_at, timezone.now() + timedelta(minutes=6))
        self.assertEqual(DiscoveryResult.objects.filter(status="validated").count(), 1)
        self.assertEqual(DiscoveryResult.objects.filter(status="candidate").count(), 1)

    def test_lost_lease_does_not_write_feed_results(self):
        def page(*args):
            DiscoveryQuery.objects.filter(pk=self.query.pk).update(lease_token=None)
            return self.page

        with patch(
            "jobboard.services.engine_search_discovery.fetch_page", side_effect=page
        ):
            run_search_discovery(limit=1)
        self.assertFalse(DiscoveryResult.objects.exists())

    def test_complete_feed_resets_cursor_for_next_daily_crawl(self):
        self.page.next_cursor = ""
        with patch(
            "jobboard.services.engine_search_discovery.fetch_page",
            return_value=self.page,
        ):
            run_search_discovery(limit=1)
        self.query.refresh_from_db()
        self.assertFalse(self.query.truncated)
        self.assertEqual(self.query.cursor, "")
        self.assertGreater(self.query.next_run_at, timezone.now() + timedelta(hours=23))

    def test_failed_activation_retries_after_other_candidates(self):
        self.query.auto_activate = True
        self.query.save()
        self.page.records.append(
            {
                **self.page.records[0],
                "id": "job2",
                "url": "https://jobs.ashbyhq.com/other/job",
            }
        )
        from jobboard.services.engine_collection import (
            register_source as original_register,
        )

        attempts = []

        def register(url, company, enable=False):
            candidate = original_register(url, company)
            if enable:
                attempts.append(url)
                lease = DiscoveryQuery.objects.get(pk=self.query.pk).lease_expires_at
                self.assertGreater(lease, timezone.now() + timedelta(minutes=14))
                if len(attempts) == 1:
                    raise CatalogueImportError("upstream_rate_limited")
                candidate.status = "validated"
                candidate.save()
            return candidate

        with (
            patch(
                "jobboard.services.engine_search_discovery.fetch_page",
                return_value=self.page,
            ),
            patch(
                "jobboard.services.engine_search_discovery.register_source",
                side_effect=register,
            ),
        ):
            for _ in range(3):
                DiscoveryQuery.objects.filter(pk=self.query.pk).update(
                    next_run_at=timezone.now()
                )
                run_search_discovery(limit=1, activation_limit=1)
        self.assertEqual(
            attempts,
            [
                "https://jobs.ashbyhq.com/example",
                "https://jobs.ashbyhq.com/other",
                "https://jobs.ashbyhq.com/example",
            ],
        )
        self.assertEqual(DiscoveryResult.objects.filter(status="validated").count(), 2)

    def test_failed_activation_respects_board_backoff(self):
        from jobboard.models import BoardSchedule, Company

        candidate = candidate_from_url("https://jobs.ashbyhq.com/example", "Example")
        board = SourceBoard.objects.create(
            provider="ashby",
            board_key="example",
            base_url=candidate.url,
            company=Company.objects.create(name="Example"),
        )
        BoardSchedule.objects.create(
            board=board, paused=True, next_run_at=timezone.now() + timedelta(hours=1)
        )
        candidate.board = board
        candidate.save()
        DiscoveryResult.objects.create(
            query=self.query,
            external_id="job1",
            source_url=candidate.url,
            company_name="Example",
            status="validation_failed",
            candidate=candidate,
            last_attempt_at=timezone.now(),
        )
        with (
            patch(
                "jobboard.services.engine_search_discovery.fetch_page",
                return_value=FeedPage([], "", 0),
            ),
            patch(
                "jobboard.services.engine_search_discovery.register_source"
            ) as register,
        ):
            run_search_discovery(limit=1, activate=True)
        register.assert_not_called()

    def test_vendor_and_private_links_are_not_employer_candidates(self):
        for url in [
            "https://www.teamtailor.com/",
            "https://teamtailor.com/",
            "https://app.teamtailor.com/companies/12/dashboard",
            "https://api.teamtailor.com/jobs",
            "https://company.teamtailor.com/dashboard",
        ]:
            with (
                self.subTest(url=url),
                self.assertRaisesMessage(CatalogueImportError, "not_employer_careers"),
            ):
                candidate_from_url(url, "Company")
        first = candidate_from_url(
            "https://homecall.teamtailor.com/jobs/123-intern", "Homecall"
        )
        second = candidate_from_url(
            "https://homecall.teamtailor.com/jobs/456-intern", "Homecall"
        )
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(first.url, "https://homecall.teamtailor.com")
        self.assertEqual(SourceCandidate.objects.count(), 1)


class LinkedInDiscoveryTests(SimpleTestCase):
    def test_public_cards_and_bounded_cursor(self):
        from jobboard.integrations.linkedin_discovery import fetch_linkedin

        markup = '<div data-entity-urn="urn:li:jobPosting:123"><a class="base-card__full-link" href="https://fr.linkedin.com/jobs/view/intern-123?tracking=abc"></a><h3 class="base-search-card__title">Stage Finance</h3><h4 class="base-search-card__subtitle"><a>Acme</a></h4><span class="job-search-card__location">Paris</span></div>'
        with patch(
            "jobboard.integrations.linkedin_discovery.read_search", return_value=markup
        ) as fetch:
            result = fetch_linkedin(
                DiscoveryQuery(
                    provider="linkedin_public", country="FR", term="stage", cursor="149"
                ),
                123,
            )
        self.assertEqual(result.next_cursor, "150")
        self.assertEqual(result.records[0]["company"], "Acme")
        self.assertEqual(
            result.records[0]["url"], "https://fr.linkedin.com/jobs/view/intern-123"
        )
        self.assertIn("f_JT=I", fetch.call_args.args[0])
        self.assertIn("location=France", fetch.call_args.args[0])

    def test_login_gate_stops_and_hidden_apply_is_ignored(self):
        from jobboard.integrations.linkedin_discovery import (
            VisibleLinks,
            fetch_linkedin,
        )

        with (
            patch(
                "jobboard.integrations.linkedin_discovery.read_search",
                return_value='<form class="sign-in-form"></form>',
            ),
            self.assertRaises(CatalogueImportError) as error,
        ):
            fetch_linkedin(DiscoveryQuery(country="FR"), 123)
        self.assertEqual(error.exception.code, "linkedin_needs_access")
        parser = VisibleLinks()
        parser.feed(
            '<div class="modal"><a href="https://jobs.lever.co/secret">Apply</a></div><a href="https://jobs.lever.co/public">Employer site</a><code style="display:none"><a href="https://jobs.lever.co/hidden">Hidden</a></code>'
        )
        self.assertEqual(parser.links, ["https://jobs.lever.co/public"])

    def test_unsupported_country_no_request(self):
        from jobboard.integrations.linkedin_discovery import fetch_linkedin

        with (
            patch("jobboard.integrations.linkedin_discovery.read_search") as fetch,
            self.assertRaises(CatalogueImportError),
        ):
            fetch_linkedin(DiscoveryQuery(country="US"), 123)
        fetch.assert_not_called()


class LinkedInGridTests(TestCase):
    def test_opt_in_grid_matches_europe_scope_without_mutating_existing_queries(self):
        from jobboard.services.engine_quality import EUROPE_COUNTRIES

        seed_queries()
        self.assertFalse(
            DiscoveryQuery.objects.filter(provider="linkedin_public").exists()
        )
        seed_queries(linkedin=True)
        seed_queries(linkedin=True)
        self.assertEqual(
            set(
                DiscoveryQuery.objects.filter(provider="linkedin_public").values_list(
                    "country", flat=True
                )
            ),
            EUROPE_COUNTRIES,
        )
        self.assertEqual(
            DiscoveryQuery.objects.exclude(provider="linkedin_public").count(), 16
        )

    def test_configure_command_passes_linkedin_flag(self):
        from io import StringIO

        from django.core.management import call_command

        output = StringIO()
        call_command(
            "configure_discovery", linkedin=True, auto_activate=True, stdout=output
        )
        self.assertEqual(
            DiscoveryQuery.objects.filter(
                provider="linkedin_public", auto_activate=True
            ).count(),
            47,
        )
        self.assertIn("Configured 63 queries", output.getvalue())


class LinkedInPartitionTests(TestCase):
    def setUp(self):
        self.query = DiscoveryQuery.objects.create(
            provider="linkedin_public",
            country="FR",
            language="fr",
            domain="all",
            term="stage",
            auto_activate=True,
        )

    def test_actual_cap_schedules_children_once_without_immediate_requests(self):
        page = FeedPage([], "150", None)
        with patch(
            "jobboard.services.engine_search_discovery.fetch_page", return_value=page
        ) as fetch:
            run_search_discovery(limit=16, provider="linkedin_public")
        fetch.assert_called_once()
        children = DiscoveryQuery.objects.exclude(pk=self.query.pk)
        self.assertEqual(children.count(), 13)
        self.assertTrue(all(child.auto_activate for child in children))
        self.assertTrue(all(child.next_run_at > timezone.now() for child in children))
        self.query.refresh_from_db()
        self.assertTrue(self.query.truncated)
        self.assertEqual(self.query.cursor, "150")
        self.assertGreater(self.query.next_run_at, timezone.now() + timedelta(hours=23))
        from jobboard.services.engine_search_discovery import (
            partition_capped_linkedin_query,
        )

        self.assertEqual(partition_capped_linkedin_query(self.query, "150"), 0)
        self.assertEqual(children.count(), 13)

    def test_pending_pagination_does_not_partition(self):
        with patch(
            "jobboard.services.engine_search_discovery.fetch_page",
            return_value=FeedPage([], "10", None),
        ):
            run_search_discovery(limit=1, provider="linkedin_public")
        self.assertEqual(DiscoveryQuery.objects.count(), 1)
        self.query.refresh_from_db()
        self.assertTrue(self.query.truncated)

    def test_children_do_not_split_recursively_and_fallback_is_english(self):
        from jobboard.services.engine_search_discovery import (
            partition_capped_linkedin_query,
        )

        self.query.language = "es"
        self.query.country = "ES"
        self.query.save()
        partition_capped_linkedin_query(self.query, "150")
        child = DiscoveryQuery.objects.exclude(pk=self.query.pk).first()
        self.assertEqual(child.language, "en")
        self.assertTrue(child.term.startswith("internship "))
        self.assertEqual(partition_capped_linkedin_query(child, "150"), 0)
        self.assertEqual(DiscoveryQuery.objects.count(), 14)
