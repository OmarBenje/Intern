import json
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from jobboard.integrations.greenhouse_catalogue import CatalogueImportError
from jobboard.models import DiscoveryResult
from jobboard.services.engine_merges import merge, reverse_merge
from jobboard.services.job_link_evidence import attributed_job, resolve
from jobboard.services.targeted_merges import propose_targeted
from jobboard.tests import test_targeted_merges


def html(job):
    return '<script type="application/ld+json">' + json.dumps(job) + "</script>"


class LinkEvidenceTests(TestCase):
    def setUp(self):
        test_targeted_merges.TargetedMergeTests.setUp(self)
        self.b.sources.update(
            origin_url="https://example.com/careers/stage-marketing",
            apply_url="https://example.com/careers/stage-marketing",
        )
        self.job = {
            "@type": "JobPosting",
            "title": "Stage marketing",
            "hiringOrganization": {"name": "Acme"},
            "url": "https://job-boards.greenhouse.io/acme/jobs/123",
            "identifier": {"name": "Acme", "value": "REQ123"},
        }

    def resolve(self):
        with patch(
            "jobboard.services.job_link_evidence.fetch_html",
            return_value=(
                "https://example.com/careers/stage-marketing",
                html(self.job),
            ),
        ):
            return resolve(self.b.sources.get(), set())

    def test_matching_evidence_enables_merge_and_reverse(self):
        self.assertEqual(propose_targeted([self.a.pk])["decision_ids"], [])
        result = self.resolve()
        self.assertEqual(result["status"], "resolved")
        self.assertEqual(result["references"][0]["value"], "REQ123")
        decision = propose_targeted([self.a.pk])["decision_ids"][0]
        # merge reloads offers without prefetch: evidence must still be present.
        merge(decision)
        self.assertEqual(self.a.sources.count(), 2)
        reverse_merge(decision)
        self.assertEqual(self.b.sources.count(), 1)

    def test_expired_evidence_blocks_previously_proposed_merge(self):
        self.resolve()
        decision = propose_targeted([self.a.pk])["decision_ids"][0]
        DiscoveryResult.objects.update(
            last_attempt_at=timezone.now() - timedelta(days=8)
        )
        with self.assertRaises(ValueError):
            merge(decision)

    def test_changed_source_invalidates_evidence(self):
        self.resolve()
        self.b.sources.update(content_hash="b" * 64)
        self.assertEqual(propose_targeted([self.a.pk])["decision_ids"], [])

    def test_replaced_evidence_invalidates_proposal(self):
        self.resolve()
        decision = propose_targeted([self.a.pk])["decision_ids"][0]
        self.job["url"] = "https://job-boards.greenhouse.io/acme/jobs/456"
        self.resolve()
        with self.assertRaises(ValueError):
            merge(decision)

    def test_ambiguous_or_different_posting_is_not_attributed(self):
        self.assertIsNone(
            attributed_job(html([self.job, self.job]), "Stage marketing", "Acme")
        )
        self.assertIsNone(attributed_job(html(self.job), "Other job", "Acme"))
        self.assertIsNone(attributed_job(html(self.job), "Stage marketing", "Other"))
        self.assertEqual(
            attributed_job(html({"@graph": [self.job]}), "Stage marketing", "Acme"),
            self.job,
        )

    def test_arbitrary_anchor_and_reference_alone_do_not_authorize_merge(self):
        self.job.pop("url")
        with patch(
            "jobboard.services.job_link_evidence.fetch_html",
            return_value=(
                "https://example.com",
                html(self.job)
                + '<a href="https://job-boards.greenhouse.io/acme/jobs/123">Other job</a>',
            ),
        ):
            result = resolve(self.b.sources.get(), set())
        self.assertEqual(result["status"], "unresolved")
        self.assertEqual(len(result["references"]), 1)
        self.assertEqual(propose_targeted([self.a.pk])["decision_ids"], [])

    def test_blocked_host_is_not_retried_in_batch(self):
        blocked = set()
        with patch(
            "jobboard.services.job_link_evidence.fetch_html",
            side_effect=CatalogueImportError("public_http_error"),
        ) as fetch:
            self.assertEqual(
                resolve(self.b.sources.get(), blocked)["error"], "public_http_error"
            )
            self.assertEqual(
                resolve(self.b.sources.get(), blocked)["error"], "host_blocked_this_run"
            )
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(DiscoveryResult.objects.get().status, "blocked")
