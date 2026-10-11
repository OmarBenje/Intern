from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from jobboard.models import Company, Location, Offer, OfferSource, SourceBoard
from jobboard.services.engine_quality import enrich_offer
from jobboard.services.source_funnel import audit_sources


class SourceFunnelTests(TestCase):
    def test_exclusive_buckets_preserve_hidden_and_source_counts(self):
        board = SourceBoard.objects.create(
            provider="lever",
            board_key="audit",
            company=Company.objects.create(name="Audit"),
        )
        for i, title, status, age in [
            (1, "Marketing Internship", "open", 0),
            (2, "Marketing Internship", "hidden", 0),
            (3, "Senior Engineer", "open", 0),
            (4, "Marketing Internship", "open", 90),
        ]:
            offer = Offer.objects.create(
                company=board.company,
                title=title,
                description="Internship",
                status=status,
            )
            offer.locations.add(
                Location.objects.create(
                    name="Paris, France", canonical_key=f"audit-{i}"
                )
            )
            OfferSource.objects.create(
                board=board,
                offer=offer,
                external_id=str(i),
                content_hash=str(i) * 64,
                last_checked_at=timezone.now() - timedelta(days=age),
            )
            enrich_offer(offer)
        report = audit_sources()
        row = next(r for r in report["boards"] if r["board_id"] == board.pk)
        self.assertEqual(row["imported_source_rows"], 4)
        self.assertEqual(
            row["buckets"],
            {
                "published": 1,
                "offer_not_open": 1,
                "not_internship": 1,
                "source_not_fresh": 1,
            },
        )
        self.assertIsNone(row["last_run"])
        self.assertEqual(Offer.objects.filter(status="hidden").count(), 1)

    def test_disabled_boards_excluded_empty_boards_visible(self):
        SourceBoard.objects.create(
            provider="lever", board_key="disabled", enabled=False
        )
        board = SourceBoard.objects.create(provider="lever", board_key="empty")
        report = audit_sources()
        self.assertEqual(len(report["boards"]), 1)
        self.assertEqual(report["boards"][0]["board_id"], board.pk)
        self.assertEqual(report["boards"][0]["imported_source_rows"], 0)
