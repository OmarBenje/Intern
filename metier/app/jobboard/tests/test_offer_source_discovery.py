from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from jobboard.integrations.greenhouse_catalogue import CatalogueImportError
from jobboard.models import (
    AtsProbe,
    Company,
    DiscoveryResult,
    Location,
    Offer,
    OfferSource,
    SourceBoard,
)
from jobboard.services.engine_quality import enrich_offer
from jobboard.services.offer_source_discovery import (
    canonical_board,
    discover_from_offers,
)

MODULE = "jobboard.services.offer_source_discovery"


class CanonicalTests(SimpleTestCase):
    def test_posting_paths_and_tracking_collapse(self):
        self.assertEqual(
            canonical_board(
                "https://job-boards.greenhouse.io/acme/jobs/42?utm_source=feed"
            )["board_key"],
            "acme",
        )
        self.assertEqual(
            canonical_board("https://acme.teamtailor.com/jobs/42-stage")["canonical"],
            "https://acme.teamtailor.com",
        )

    def test_unsafe_input_not_laundered(self):
        for url in [
            "http://jobs.lever.co/acme/1",
            "https://user:secret@jobs.lever.co/acme/1",
            "https://jobs.lever.co:444/acme/1",
            "https://127.0.0.1/jobs/1",
        ]:
            with (
                self.subTest(url=url),
                self.assertRaises((ValueError, CatalogueImportError)),
            ):
                canonical_board(url)


class DiscoveryTests(TestCase):
    def setUp(self):
        company = Company.objects.create(name="Acme Europe")
        self.board = SourceBoard.objects.create(
            provider="wttj",
            board_key="acme",
            company=company,
            base_url="https://www.welcometothejungle.com/fr/companies/acme",
        )
        self.offer = Offer.objects.create(
            company=company,
            title="Marketing Internship",
            description="Internship in marketing",
            status="open",
        )
        self.offer.locations.add(
            Location.objects.create(name="Paris, France", canonical_key="paris-france")
        )
        self.source = OfferSource.objects.create(
            offer=self.offer,
            board=self.board,
            external_id="1",
            origin_url="https://www.welcometothejungle.com/fr/companies/acme/jobs/1",
            apply_url="https://jobs.lever.co/acme/42",
            content_hash="a" * 64,
            last_checked_at=timezone.now(),
        )
        enrich_offer(self.offer)

    def test_direct_link_enrolls_with_provenance_and_is_idempotent(self):
        result = discover_from_offers(1)
        self.assertEqual(len(result["enrolled"]), 1)
        self.assertEqual(result["enrolled"][0]["source_id"], self.source.pk)
        self.assertEqual(
            DiscoveryResult.objects.get().payload["method"], "posting_link"
        )
        self.assertEqual(discover_from_offers(1)["already_queued"], 1)
        self.assertEqual(AtsProbe.objects.count(), 1)

    def test_known_board_case_alias_skipped(self):
        SourceBoard.objects.create(
            provider="lever",
            board_key="ACME",
            company=self.board.company,
            base_url="https://jobs.lever.co/ACME",
        )
        self.assertEqual(discover_from_offers(1)["known_boards"], 1)
        self.assertFalse(AtsProbe.objects.exists())

    def test_registry_names_are_exact_and_labelled_as_leads(self):
        self.source.apply_url = self.source.origin_url
        self.source.save()
        rows = [
            {"name": "Acme", "url": "https://jobs.lever.co/wrong"},
            {"name": "acme europe", "url": "https://jobs.lever.co/right"},
        ]
        with patch(
            f"{MODULE}.read_inventory",
            return_value=("https://example.com/inventory", "sha", rows),
        ):
            result = discover_from_offers(1, True)
        self.assertEqual(result["enrolled"][0]["url"], "https://jobs.lever.co/right")
        self.assertEqual(result["enrolled"][0]["method"], "exact_registry_name")

    def test_non_published_offer_never_seeds_discovery(self):
        self.offer.status = "closed"
        self.offer.save()
        self.assertEqual(discover_from_offers(1)["scanned_sources"], 0)
        self.assertFalse(AtsProbe.objects.exists())

    def test_priority_ranks_across_providers_and_deduplicates_employers(self):
        from jobboard.tests.engine_fixtures import publishable

        self.source.apply_url = self.source.origin_url
        self.source.save()
        rare = publishable(
            Offer.objects.create(
                company=Company.objects.create(name="Rare Employer"),
                title="Marketing Internship",
                description="Internship in Sofia, Bulgaria",
            )
        )
        rare.enrichment.country_codes = ["BG"]
        rare.enrichment.save()
        # Make FR more represented than BG, independent of source/inventory order.
        other = publishable(
            Offer.objects.create(
                company=self.offer.company,
                title="Another internship",
                description="Internship in France",
            )
        )
        other.enrichment.country_codes = ["FR"]
        other.enrichment.save()

        def inventory(provider):
            rows = (
                [{"name": "Acme Europe", "url": "https://jobs.lever.co/acme-new"}]
                if provider == "lever"
                else [
                    {"name": "Rare Employer", "url": "https://jobs.ashbyhq.com/rare"},
                    {"name": "Rare Employer", "url": "https://jobs.ashbyhq.com/rare2"},
                ]
                if provider == "ashby"
                else []
            )
            return "https://example.com/inventory", "sha", rows

        with patch(f"{MODULE}.read_inventory", side_effect=inventory):
            result = discover_from_offers(2, True, True)
        self.assertEqual(
            [r["company"] for r in result["enrolled"]], ["Rare Employer", "Acme Europe"]
        )
        self.assertEqual(result["enrolled"][0]["seed_countries"], ["BG"])
        self.assertLess(
            result["enrolled"][0]["priority_country_count"],
            result["enrolled"][1]["priority_country_count"],
        )
        self.assertEqual(result["shortfall"], 0)

    def test_priority_preserves_existing_probe_schedule(self):
        from datetime import timedelta

        first = discover_from_offers(1, prioritize=True)["enrolled"][0]
        future = timezone.now() + timedelta(days=7)
        AtsProbe.objects.filter(pk=first["probe_id"]).update(
            state="waiting", next_attempt_at=future
        )
        result = discover_from_offers(100, prioritize=True)
        self.assertEqual(result["enrolled"], [])
        self.assertEqual(result["shortfall"], 100)
        self.assertEqual(AtsProbe.objects.get().next_attempt_at, future)
        with self.assertRaises(ValueError):
            discover_from_offers(101, prioritize=True)
