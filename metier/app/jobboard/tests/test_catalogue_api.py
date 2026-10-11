from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import include, path
from django.utils import timezone

from jobboard.models import (
    CandidateProfile,
    Company,
    CompensationBand,
    Offer,
    OfferSource,
    PreferenceContract,
    PreferenceWorkMode,
    SavedOffer,
    SearchPreference,
    Skill,
    SourceBoard,
)
from jobboard.tests.engine_fixtures import publishable

urlpatterns = [path("api/v1/", include("jobboard.api.catalogue"))]


@override_settings(ROOT_URLCONF=__name__)
class CatalogueAPITests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="reader", password="reader-password-42"
        )
        self.other = get_user_model().objects.create_user(username="other")
        self.company = Company.objects.create(name="Acme")
        self.offer = Offer.objects.create(
            title="Python Engineer",
            description="Django backend development",
            company=self.company,
            contract_type="internship",
        )
        publishable(self.offer)
        self.client.force_login(self.user)

    def test_feed_excludes_closed_expired_hidden_and_filters_search(self):
        for status in ["closed", "hidden"]:
            Offer.objects.create(title=status, company=self.company, status=status)
        Offer.objects.create(
            title="expired",
            company=self.company,
            expires_at=timezone.now() - timedelta(seconds=1),
        )
        response = self.client.get("/api/v1/offers/?q=Python&contract_type=internship")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)
        self.assertEqual(response.json()["results"][0]["id"], self.offer.pk)
        self.assertEqual(
            self.client.get("/api/v1/offers/?role=invalid").status_code, 400
        )
        self.assertEqual(
            self.client.get("/api/v1/offers/?work_mode=invalid").status_code, 400
        )

    def test_saved_offers_isolation_and_idempotency(self):
        url = f"/api/v1/saved-offers/{self.offer.pk}/"
        for _ in range(2):
            self.assertEqual(
                self.client.put(
                    url, data="{}", content_type="application/json"
                ).status_code,
                200,
            )
        self.assertEqual(SavedOffer.objects.count(), 1)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get("/api/v1/saved-offers/").json()["count"], 0)
        self.client.delete(url)
        self.assertEqual(SavedOffer.objects.count(), 1)
        self.client.force_login(self.user)
        for _ in range(2):
            self.assertEqual(self.client.delete(url).status_code, 200)
        self.assertEqual(SavedOffer.objects.count(), 0)

    def test_pagination_is_deterministic_and_query_count_bounded(self):
        Offer.objects.bulk_create(
            [
                Offer(title=f"Engineer {i}", description="", company=self.company)
                for i in range(25)
            ]
        )
        for offer in Offer.objects.all():
            publishable(offer)
        with CaptureQueriesContext(connection) as small:
            self.client.get("/api/v1/offers/?page_size=1")
        with CaptureQueriesContext(connection) as large:
            first = self.client.get("/api/v1/offers/?page_size=20").json()
        second = self.client.get("/api/v1/offers/?page_size=20&page=2").json()
        self.assertEqual(first["count"], 26)
        self.assertEqual(len(first["results"]), 20)
        self.assertEqual(len(second["results"]), 6)
        self.assertFalse(
            {o["id"] for o in first["results"]} & {o["id"] for o in second["results"]}
        )
        self.assertEqual(len(small), len(large))

    def test_recommendations_explain_structured_preferences(self):
        profile, _ = CandidateProfile.objects.get_or_create(
            user=self.user, defaults={"full_name": "Reader"}
        )
        preference = SearchPreference.objects.create(profile=profile)
        PreferenceContract.objects.create(preference=preference, value="internship")
        PreferenceWorkMode.objects.create(preference=preference, value="remote")
        response = self.client.get("/api/v1/recommendations/").json()
        self.assertEqual(response["count"], 1)
        self.assertEqual(
            response["results"][0]["reasons"],
            [{"code": "preferred_contract", "value": "internship"}],
        )
        self.client.force_login(self.other)
        self.assertEqual(self.client.get("/api/v1/recommendations/").json()["count"], 0)

    def test_authentication_required(self):
        self.client.logout()
        self.assertEqual(self.client.get("/api/v1/offers/").status_code, 200)
        self.assertEqual(self.client.get("/api/v1/saved-offers/").status_code, 401)

    def preference(self, **kwargs):
        profile, _ = CandidateProfile.objects.get_or_create(
            user=self.user, defaults={"full_name": "Reader"}
        )
        preference = SearchPreference.objects.create(profile=profile, **kwargs)
        PreferenceContract.objects.create(preference=preference, value="internship")
        PreferenceWorkMode.objects.create(preference=preference, value="remote")
        return preference

    def recommendations(self, include_unknown="true"):
        response = self.client.get(
            "/api/v1/recommendations/", {"include_unknown": include_unknown}
        )
        self.assertEqual(response.status_code, 200)
        return response.json()["results"]

    def test_explicit_contract_and_mode_exclude_even_matching_skills(self):
        preference = self.preference()
        skill = Skill.objects.create(name="Python", slug="python")
        preference.profile.skills.add(skill)
        self.offer.skills.add(skill)
        self.offer.work_mode = "remote"
        self.offer.save()
        wrong_contract = Offer.objects.create(
            title="Employment",
            company=self.company,
            contract_type="employment",
            work_mode="remote",
        )
        wrong_mode = Offer.objects.create(
            title="Onsite",
            company=self.company,
            contract_type="internship",
            work_mode="onsite",
        )
        wrong_contract.skills.add(skill)
        wrong_mode.skills.add(skill)
        results = self.recommendations()
        self.assertEqual([item["offer"]["id"] for item in results], [self.offer.pk])
        self.assertIn(
            {"code": "profile_skills", "skill_ids": [skill.pk]}, results[0]["reasons"]
        )

    def test_unknown_constraints_are_visible_and_can_be_excluded(self):
        preference = self.preference()
        results = self.recommendations()
        self.assertEqual(results[0]["unknown_fields"], ["work_mode"])
        self.assertEqual(self.recommendations("false"), [])
        preference.work_modes.all().delete()
        self.assertEqual(self.recommendations(), [])
        self.assertEqual(
            self.client.get(
                "/api/v1/recommendations/?include_unknown=maybe"
            ).status_code,
            400,
        )

    def test_salary_comparison_uses_compatible_currency_period_basis_only(self):
        self.preference(
            minimum_salary="50000",
            salary_currency="EUR",
            salary_period="year",
            salary_gross_net="gross",
        )
        board = SourceBoard.objects.create(
            provider="greenhouse",
            board_key="acme",
            company=self.company,
            base_url="https://boards.greenhouse.io/acme",
        )
        self.offer.work_mode = "remote"
        self.offer.save()

        def offer_with_salary(name, minimum, maximum, **kwargs):
            offer = Offer.objects.create(
                title=name,
                company=self.company,
                contract_type="internship",
                work_mode="remote",
            )
            source = OfferSource.objects.create(
                offer=offer,
                board=board,
                external_id=name,
                origin_url="https://example.com/job",
                apply_url="https://example.com/job",
                content_hash="a" * 64,
            )
            CompensationBand.objects.create(
                offer=offer,
                source=source,
                minimum=minimum,
                maximum=maximum,
                **{"currency": "EUR", "period": "year", "gross_net": "gross", **kwargs},
            )
            return publishable(offer)

        sufficient = offer_with_salary("enough", "45000", "55000")
        insufficient = offer_with_salary("too-low", "35000", "45000")
        usd = offer_with_salary("currency-unknown", "80000", "90000", currency="USD")
        monthly = offer_with_salary("period-unknown", "80000", "90000", period="month")
        net = offer_with_salary("basis-unknown", "80000", "90000", gross_net="net")
        unknown_basis = offer_with_salary(
            "basis-unreported", "80000", "90000", gross_net="unknown"
        )
        results = self.recommendations()
        by_id = {item["offer"]["id"]: item for item in results}
        self.assertNotIn(insufficient.pk, by_id)
        self.assertEqual(by_id[sufficient.pk]["salary_comparison"], "comparable")
        for offer in [self.offer, usd, monthly, net, unknown_basis]:
            self.assertEqual(by_id[offer.pk]["salary_comparison"], "not_comparable")
            self.assertIn("salary", by_id[offer.pk]["unknown_fields"])
        self.assertEqual(
            [item["offer"]["id"] for item in self.recommendations("false")],
            [sufficient.pk],
        )
