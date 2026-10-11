from types import SimpleNamespace

from django.test import SimpleTestCase, TestCase

from jobboard.models import Company, Offer, OfferEnrichment
from jobboard.services.engine_matching import evaluate_match, preselect_offers


def offer_with(**facts):
    return SimpleNamespace(
        status="open",
        enrichment=SimpleNamespace(
            facts=facts,
            classification="confirmed",
            europe_status="in_scope",
            country_codes=["FR"],
            content_version=2,
            extractor_version="rules-1",
        ),
    )


def proven(value, required=True):
    return {
        "value": value,
        "required": required,
        "source_revision_id": 1,
        "evidence_text": "Source excerpt",
    }


class MatchingTests(SimpleTestCase):
    def test_missing_duration_is_unknown_not_rejection(self):
        result = evaluate_match(offer_with(), {}, {"duration_max_months": 4})
        self.assertEqual(result["compatibility"], "needs_verification")
        self.assertIn("duration", result["unknown_fields"])

    def test_minimum_duration_conflict_requires_source_evidence(self):
        duration = proven({"minimum": 6, "maximum": 6, "unit": "months"})
        result = evaluate_match(
            offer_with(duration=duration), {}, {"duration_max_months": 4}
        )
        self.assertEqual(result["compatibility"], "incompatible_explicit")
        duration["source_revision_id"] = None
        self.assertEqual(
            evaluate_match(
                offer_with(duration=duration), {}, {"duration_max_months": 4}
            )["compatibility"],
            "needs_verification",
        )

    def test_preferred_duration_never_blocks(self):
        duration = proven(
            {"minimum": 6, "maximum": 6, "unit": "months"}, required=False
        )
        self.assertNotEqual(
            evaluate_match(
                offer_with(duration=duration), {}, {"duration_max_months": 4}
            )["compatibility"],
            "incompatible_explicit",
        )

    def test_calendar_month_comparison(self):
        offer = offer_with(
            start_date=proven("2027-01-31"),
            duration=proven({"minimum": 1, "maximum": 1, "unit": "months"}),
        )
        result = evaluate_match(
            offer, {}, {"available_from": "2027-01-01", "available_until": "2027-02-28"}
        )
        self.assertEqual(result["compatibility"], "compatible_known")

    def test_no_approximate_week_conversion_without_date(self):
        offer = offer_with(
            duration=proven({"minimum": 17, "maximum": 17, "unit": "weeks"})
        )
        self.assertEqual(
            evaluate_match(offer, {}, {"duration_max_months": 4})["compatibility"],
            "needs_verification",
        )

    def test_sponsorship_absent_and_explicitly_refused(self):
        self.assertEqual(
            evaluate_match(offer_with(), {}, {"needs_sponsorship": True})[
                "compatibility"
            ],
            "needs_verification",
        )
        self.assertEqual(
            evaluate_match(
                offer_with(sponsorship_available=proven(False)),
                {},
                {"needs_sponsorship": True},
            )["compatibility"],
            "incompatible_explicit",
        )

    def test_missing_language_not_assumed_unable(self):
        offer = offer_with(required_languages=proven([{"code": "de"}]))
        self.assertEqual(
            evaluate_match(offer, {}, {"languages": ["fr"]})["compatibility"],
            "needs_verification",
        )

    def test_versions_change_with_profile(self):
        result = evaluate_match(offer_with(), {"profile_version": 7})
        self.assertEqual(result["versions"]["profile"], 7)
        self.assertEqual(result["versions"]["offer"], 2)


class SqlPreselectionTests(TestCase):
    def test_unknowns_and_scope_enum(self):
        company = Company.objects.create(name="Selection")
        unknown = Offer.objects.create(company=company, title="Unknown", description="")
        europe = Offer.objects.create(
            company=company, title="Internship", description=""
        )
        outside = Offer.objects.create(
            company=company, title="Internship", description=""
        )
        OfferEnrichment.objects.create(
            offer=europe,
            classification="confirmed",
            europe_status="in_scope",
            country_codes=["FR"],
        )
        OfferEnrichment.objects.create(
            offer=outside,
            classification="confirmed",
            europe_status="out_of_scope",
            country_codes=["US"],
        )
        qs = preselect_offers(Offer.objects.all(), {"country_codes": ["FR"]})
        self.assertSetEqual(
            set(qs.values_list("pk", flat=True)), {unknown.pk, europe.pk}
        )
        qs = preselect_offers(
            Offer.objects.all(),
            {"europe_scope": "out_of_scope", "unknown_policy": "exclude"},
        )
        self.assertEqual(list(qs.values_list("pk", flat=True)), [outside.pk])
