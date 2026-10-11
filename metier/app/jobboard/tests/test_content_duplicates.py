from django.test import TestCase

from jobboard.models import Location
from jobboard.services.content_duplicates import (
    decision_for,
    matches,
    reconcile_duplicates,
)
from jobboard.services.engine_merges import merge, reverse_merge
from jobboard.tests.test_targeted_merges import TargetedMergeTests


class ContentDuplicateTests(TestCase):
    def setUp(self):
        TargetedMergeTests.setUp(self)
        self.b.company = self.a.company
        self.a.description = self.b.description = (
            "Plan campaigns and coordinate marketing communications with the brand team. "
            "Analyze performance and improve the customer experience across channels. "
        ) * 8
        self.a.save()
        self.b.save()
        self.b.sources.update(
            origin_url="https://example.com/jobs/456",
            apply_url="https://example.com/jobs/456",
        )

    def test_different_publication_ids_merge_and_reverse(self):
        result = reconcile_duplicates()
        self.assertEqual(result["merged"], [self.b.pk])
        self.assertEqual(self.a.sources.count(), 2)
        self.assertEqual(reconcile_duplicates()["merged"], [])
        decision = decision_for(self.a, self.b)
        reverse_merge(decision.pk)
        self.assertEqual(self.b.sources.count(), 1)
        self.assertEqual(reconcile_duplicates()["merged"], [])

    def test_location_country_suffix(self):
        self.a.locations.set(
            [
                Location.objects.create(
                    name="Paris", country_code="FR", canonical_key="p1"
                )
            ]
        )
        self.b.locations.set(
            [
                Location.objects.create(
                    name="Paris, FR", country_code="FR", canonical_key="p2"
                )
            ]
        )
        self.assertTrue(matches(self.a, self.b))
        self.b.locations.set(
            [
                Location.objects.create(
                    name="Paris", country_code="US", canonical_key="p3"
                )
            ]
        )
        self.assertFalse(matches(self.a, self.b))

    def test_dates_and_requisitions_block(self):
        self.b.description += " Starts 2027"
        self.assertFalse(matches(self.a, self.b))
        self.b.description = self.a.description
        self.a.sources.update(external_requisition_id="A")
        self.b.sources.update(external_requisition_id="B")
        self.assertFalse(matches(self.a, self.b))

    def test_summary_and_other_role_not_auto_merged(self):
        self.b.description = "A brief marketing summary"
        self.assertFalse(matches(self.a, self.b))
        self.b.description = self.a.description
        self.b.title = "Ads Creative Intern"
        self.assertFalse(matches(self.a, self.b))

    def test_stale_fingerprint_blocks(self):
        decision = decision_for(self.a, self.b)
        self.b.description += " updated"
        self.b.save()
        with self.assertRaisesMessage(ValueError, "merge_identity_conflict"):
            merge(decision.pk)

    def test_workday_requisition_ids_are_not_publication_copies(self):
        source = self.a.sources.get()
        source.board.provider = "workday"
        source.board.save()
        self.b.sources.update(board=source.board, external_id="R222")
        self.a.sources.update(external_id="R111")
        self.assertFalse(matches(self.a, self.b))
