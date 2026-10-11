import copy
import json
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase

from jobboard.api.catalogue import open_offers
from jobboard.integrations.lever_locations import explicit_role_locations
from jobboard.integrations.public_catalogue import normalize_ashby, normalize_lever
from jobboard.integrations.workable_catalogue import normalize_workable
from jobboard.models import Company, OfferSource, SourceBoard
from jobboard.services.ats_probing import qualifies
from jobboard.services.catalogue import import_board

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures/civitta_location.json").read_text()
)


class LeverLocationTests(SimpleTestCase):
    def test_real_civitta_country_list_keeps_non_europe_and_one_posting(self):
        rows = normalize_lever([copy.deepcopy(FIXTURE)])
        self.assertEqual(len(rows), 1)
        countries = {p["country"] for p in rows[0]["location_details"]}
        self.assertTrue({"FI", "BG", "CZ", "US", "UZ", "AM"} <= countries)
        self.assertEqual(len(countries), 23)
        self.assertTrue(qualifies(rows[0]))
        self.assertIn(
            "This position is open across",
            rows[0]["raw"]["location_resolution"]["evidence"],
        )

    def test_no_inference_from_company_offices_or_negation(self):
        for text in [
            "Our offices are in France, Finland and United States.",
            "This position is not open across All Civitta locations: France.",
            "Previously, this position is open across All Civitta locations: France.",
            "This position is open across All Civitta locations: France, Atlantis.",
        ]:
            with self.subTest(text=text):
                self.assertIsNone(
                    explicit_role_locations(text, ["All Civitta locations"])
                )

    def test_specific_locations_and_multiple_claims_not_overridden(self):
        text = "This position is open across All Civitta locations: France."
        for places in [["Boston, United States"], ["All Civitta locations", "London"]]:
            self.assertIsNone(explicit_role_locations(text, places))
        self.assertIsNone(
            explicit_role_locations(text + "\n" + text, ["All Civitta locations"])
        )

    def test_non_europe_only_and_remote_not_published(self):
        job = copy.deepcopy(FIXTURE)
        job["descriptionPlain"] = (
            "This position is open across All Civitta locations: United States."
        )
        self.assertFalse(qualifies(normalize_lever([job])[0]))
        job = copy.deepcopy(FIXTURE)
        job["workplaceType"] = "remote"
        job["categories"]["allLocations"] = ["Paris, France"]
        row = normalize_lever([job])[0]
        self.assertEqual(row["work_mode"], "remote")
        self.assertFalse(qualifies(row))

    def test_structured_country_blocks_text_fallback(self):
        job = copy.deepcopy(FIXTURE)
        job["country"] = "US"
        row = normalize_lever([job])[0]
        self.assertNotIn("location_resolution", row["raw"])
        self.assertFalse(qualifies(row))

    def test_gen_malaysia_intern_not_published(self):
        # Reduced public Gen API record, 2026-10-01.
        row = normalize_ashby(
            {
                "jobs": [
                    {
                        "title": "Data Scientist, Intern - MoneyLion",
                        "jobUrl": "https://jobs.ashbyhq.com/gen-digital/020a42a9-7c79-4e6c-958f-726069ff86f0",
                        "descriptionPlain": "This internship will be 6 months long.",
                        "employmentType": "Intern",
                        "isListed": True,
                        "location": "MYS - Kuala Lumpur",
                        "address": {"postalAddress": {"addressCountry": "Malaysia"}},
                    }
                ]
            }
        )[0]
        self.assertFalse(qualifies(row))

    def test_plum_non_intern_listing_does_not_request_details(self):
        def unexpected(_):
            self.fail("Should not fetch non-intern detail")

        rows = normalize_workable(
            {"jobs": [{"title": "Backend Engineer", "shortcode": "6671EA9508"}]},
            "withplum",
            unexpected,
        )
        self.assertFalse(rows)


class LeverLocationImportTests(TestCase):
    def test_country_evidence_survives_idempotent_import(self):
        board = SourceBoard.objects.create(
            provider="lever",
            instance="global",
            board_key="Civitta",
            company=Company.objects.create(name="Civitta"),
            enabled=True,
        )
        rows = normalize_lever([copy.deepcopy(FIXTURE)])
        with patch("jobboard.services.catalogue.fetch_normalized", return_value=rows):
            import_board(board.pk)
            import_board(board.pk)
        self.assertEqual(OfferSource.objects.filter(board=board).count(), 1)
        offer = open_offers().get(company=board.company)
        self.assertIn("FI", offer.enrichment.country_codes)
        self.assertIn("US", offer.enrichment.country_codes)
        self.assertIn("location_resolution", offer.sources.get().raw_payload)
