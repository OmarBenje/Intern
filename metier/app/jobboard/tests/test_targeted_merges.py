from django.test import TestCase

from jobboard.models import Company, Location, Offer, OfferMergeDecision, SourceBoard
from jobboard.services.engine_merges import (
    merge,
    preferred_content_board,
    reverse_merge,
)
from jobboard.services.targeted_merges import job_link, propose_targeted
from jobboard.tests.test_engine_coverage import publishable


class TargetedMergeTests(TestCase):
    def setUp(self):
        self.a = publishable(
            Offer.objects.create(
                company=Company.objects.create(name="Acme"),
                title="Stage marketing",
                description="Full employer description. " * 10,
            )
        )
        self.b = publishable(
            Offer.objects.create(
                company=Company.objects.create(name="Acme"),
                title="Stage marketing",
                description="Short aggregator summary",
            )
        )
        location = Location.objects.create(
            name="Paris, France", canonical_key="merge-paris"
        )
        self.a.locations.add(location)
        self.b.locations.add(location)
        for offer in [self.a, self.b]:
            offer.sources.update(
                origin_url="https://job-boards.greenhouse.io/acme/jobs/123",
                apply_url="https://job-boards.greenhouse.io/acme/jobs/123",
            )
        source = self.b.sources.get()
        source.board = SourceBoard.objects.create(
            provider="wttj", board_key="summary", company=self.b.company
        )
        source.save()

    def test_summary_merge_preserves_employer_and_reverses(self):
        report = propose_targeted([self.a.pk])
        decision = OfferMergeDecision.objects.get(pk=report["decision_ids"][0])
        self.assertEqual(decision.canonical_offer_id, self.a.pk)
        merge(decision.pk)
        self.b.refresh_from_db()
        self.assertEqual(self.b.status, "hidden")
        self.assertEqual(self.a.sources.count(), 2)
        self.assertTrue(
            preferred_content_board(
                self.a, self.a.sources.get(board__provider="greenhouse").board
            )
        )
        reverse_merge(decision.pk)
        self.assertEqual(self.b.sources.count(), 1)
        self.assertFalse(preferred_content_board(self.a, self.a.sources.get().board))

    def test_changed_evidence_blocks_merge(self):
        decision = propose_targeted([self.a.pk])["decision_ids"][0]
        self.b.description = "Changed after review"
        self.b.save()
        with self.assertRaises(ValueError):
            merge(decision)

    def test_reference_conflict_and_different_employer_stay_separate(self):
        self.a.sources.update(external_requisition_id="A")
        self.b.sources.update(external_requisition_id="B")
        self.assertEqual(propose_targeted([self.a.pk])["decision_ids"], [])
        self.b.sources.update(external_requisition_id="A")
        self.b.company.name = "Other employer"
        self.b.company.save()
        self.assertEqual(propose_targeted([self.a.pk])["decision_ids"], [])

    def test_generic_or_different_job_ids_are_not_identity(self):
        self.assertIsNone(job_link("https://example.com/careers"))
        self.assertNotEqual(
            job_link("https://example.com/careers?gh_jid=1"),
            job_link("https://example.com/careers?gh_jid=2"),
        )
        self.b.sources.update(
            origin_url="https://example.com/jobs/456",
            apply_url="https://example.com/jobs/456",
        )
        report = propose_targeted([self.a.pk])
        self.assertEqual(report["decision_ids"], [])
        self.assertEqual(len(report["title_only_groups"]), 1)

    def test_employer_refresh_survives_merge(self):
        from unittest.mock import patch

        from jobboard.api.catalogue import offer_queryset
        from jobboard.services.catalogue import import_board
        from jobboard.tests.test_imports import snapshot

        decision = propose_targeted([self.a.pk])["decision_ids"][0]
        source = self.a.sources.get()
        merge(decision)
        payload = snapshot(int(source.external_id))
        payload["jobs"][0]["content"] = "Updated employer internship description"
        with patch("jobboard.services.catalogue.fetch_snapshot", return_value=payload):
            import_board(source.board_id)
        self.a.refresh_from_db()
        self.assertEqual(self.a.description, "Updated employer internship description")
        self.assertEqual(
            offer_queryset().get(pk=self.a.pk).sources.all()[0].board.provider,
            "greenhouse",
        )

    def test_stale_link_cannot_authorize_merge(self):
        from datetime import timedelta

        from django.utils import timezone

        decision = propose_targeted([self.a.pk])["decision_ids"][0]
        self.b.sources.update(last_checked_at=timezone.now() - timedelta(days=20))
        with self.assertRaises(ValueError):
            merge(decision)
