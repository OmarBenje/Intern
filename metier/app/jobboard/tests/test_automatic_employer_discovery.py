from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from jobboard.models import (
    AtsProbe,
    Company,
    DiscoveryQuery,
    DiscoveryResult,
    SourceBoard,
    SourceCandidate,
)
from jobboard.services.automatic_employer_discovery import run_automatic_discovery


class AutomaticDiscoveryTests(TestCase):
    def test_legacy_feed_activation_does_not_bypass_probe_validation(self):
        from jobboard.services.engine_search_discovery import run_search_discovery

        lead = self.lead()
        run_automatic_discovery()
        lead.candidate = AtsProbe.objects.get().candidate
        lead.status = "candidate"
        lead.save()
        self.feed.auto_activate = True
        self.feed.save()
        with (
            patch(
                "jobboard.services.engine_search_discovery.fetch_page",
                return_value=SimpleNamespace(records=[], next_cursor="", total=0),
            ),
            patch(
                "jobboard.services.engine_search_discovery.register_source"
            ) as activate,
        ):
            run_search_discovery(limit=1, resolve_limit=0, provider="arbeitnow")
        activate.assert_not_called()

    def test_existing_employer_is_not_registered_on_another_portal(self):
        Company.objects.create(name="Acme")
        self.lead()
        report = run_automatic_discovery()
        self.assertEqual(report["counts"]["known_employer"], 1)
        self.assertFalse(AtsProbe.objects.exists())

    def test_pinned_registry_is_only_a_lead_and_unknown_revision_is_rejected(self):
        from jobboard.services.ats_registry import REVISION

        registry = DiscoveryQuery.objects.create(
            provider="ats_registry", language="en", enabled=False
        )
        payload = {
            "revision": REVISION,
            "registry": f"https://raw.githubusercontent.com/kalil0321/ats-scrapers/{REVISION}/ats-companies/ashby.csv",
        }
        self.lead(query=registry, payload=payload)
        self.lead(
            company="Other",
            url="https://jobs.ashbyhq.com/other",
            query=registry,
            payload=dict(payload, revision="untrusted"),
        )
        result = run_automatic_discovery()
        self.assertEqual(len(result["enrolled"]), 1)
        self.assertEqual(result["counts"]["unverified_registry_revision"], 1)
        self.assertFalse(SourceBoard.objects.exists())

    def setUp(self):
        self.feed = DiscoveryQuery.objects.create(provider="arbeitnow", language="en")

    def lead(self, company="Acme", url="https://jobs.ashbyhq.com/acme/abc", **changes):
        values = {
            "query": self.feed,
            "external_id": str(DiscoveryResult.objects.count()),
            "company_name": company,
            "source_url": url,
            "payload": {"title": "Software Engineer Intern"},
            "attribution": "https://www.arbeitnow.com",
        }
        values.update(changes)
        return DiscoveryResult.objects.create(**values)

    def due(self):
        DiscoveryQuery.objects.filter(provider="auto_employer_discovery").update(
            next_run_at=timezone.now()
        )

    def test_admission_is_provenanced_idempotent_and_never_publishes_directly(self):
        lead = self.lead()
        report = run_automatic_discovery()
        self.assertEqual(len(report["enrolled"]), 1)
        self.assertFalse(SourceBoard.objects.exists())
        probe = AtsProbe.objects.get()
        evidence = DiscoveryResult.objects.get(
            query__provider="auto_employer_discovery"
        )
        self.assertEqual(evidence.payload["evidence_result_id"], lead.pk)
        self.assertEqual(evidence.attribution, lead.source_url)
        self.assertEqual(probe.candidate.company_name, "Acme")
        self.assertEqual(run_automatic_discovery()["state"], "not_due")
        self.lead(url="https://jobs.ashbyhq.com/acme/other")
        self.due()
        report = run_automatic_discovery()
        self.assertEqual(report["counts"]["already_queued"], 1)
        self.assertEqual(AtsProbe.objects.count(), 1)

    def test_unknown_identity_unsafe_links_nonintern_and_stale_evidence_rejected(self):
        self.lead(company="Different Employer")
        self.lead(
            company="Credentials",
            url="https://user:pass@jobs.ashbyhq.com/credentials/job",
        )
        self.lead(company="Unsafe", url="https://jobs.ashbyhq.com.evil.test/unsafe")
        self.lead(
            company="Senior",
            url="https://jobs.ashbyhq.com/senior/job",
            payload={"title": "Senior Engineer"},
        )
        self.lead(
            company="Old",
            url="https://jobs.ashbyhq.com/old/job",
            last_seen_at=timezone.now() - timedelta(days=8),
        )
        self.lead(
            company="Ambiguous",
            url="https://jobs.ashbyhq.com/ambiguous/job",
            payload={
                "title": "Intern",
                "apply_url": "https://jobs.lever.co/ambiguous/abc",
            },
        )
        report = run_automatic_discovery()
        self.assertEqual(report["enrolled"], [])
        self.assertEqual(report["counts"]["ambiguous_portals"], 1)
        self.assertFalse(AtsProbe.objects.exists())

    def test_known_disabled_board_and_existing_probe_backoff_preserved(self):
        SourceBoard.objects.create(provider="ashby", board_key="acme", enabled=False)
        self.lead()
        candidate = SourceCandidate.objects.create(
            provider="ashby",
            board_key="other",
            url="https://jobs.ashbyhq.com/other",
            company_name="Other",
        )
        retry = timezone.now() + timedelta(days=5)
        probe = AtsProbe.objects.create(
            candidate=candidate, enabled=False, state="stopped", next_attempt_at=retry
        )
        self.lead(company="Other", url=candidate.url + "/job")
        report = run_automatic_discovery()
        self.assertEqual(report["enrolled"], [])
        probe.refresh_from_db()
        self.assertFalse(probe.enabled)
        self.assertEqual(probe.next_attempt_at, retry)

    def test_shared_daily_quota_and_cursor(self):
        for i in range(3):
            self.lead(company=f"Acme{i}", url=f"https://jobs.ashbyhq.com/acme{i}/job")
        with patch("jobboard.services.automatic_employer_discovery.DAILY_LIMIT", 2):
            self.assertEqual(len(run_automatic_discovery()["enrolled"]), 2)
            self.due()
            self.assertEqual(run_automatic_discovery()["state"], "daily_limit")
        self.assertEqual(AtsProbe.objects.count(), 2)

    def test_disabled_admission_remains_disabled(self):
        self.lead()
        DiscoveryQuery.objects.create(
            provider="auto_employer_discovery",
            country="",
            language="en",
            domain="all",
            term="public-feed-portals",
            enabled=False,
        )
        self.assertEqual(run_automatic_discovery()["state"], "not_due")
        self.assertFalse(AtsProbe.objects.exists())
