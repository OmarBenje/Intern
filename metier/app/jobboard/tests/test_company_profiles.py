import json
from datetime import timedelta
from io import StringIO
from tempfile import NamedTemporaryFile

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import include, path
from django.utils import timezone

from jobboard.models import (
    CandidateProfile,
    Company,
    CompanyProfile,
    Location,
    Offer,
    PreferenceContract,
    PreferenceWorkMode,
    SearchPreference,
)
from jobboard.services.company_profiles import (
    enrich_company_from_offer,
    extract_presentation,
)
from jobboard.services.company_profiles_schema import validate_sections
from jobboard.tests.engine_fixtures import publishable

urlpatterns = [
    path("api/v1/", include("jobboard.api.catalogue")),
    path("api/v1/", include("jobboard.api.companies")),
]


def entry(**kwargs):
    return {
        "key": "presentation",
        "value": "A company presentation.",
        "source_url": "https://employer.example/about",
        "source_kind": "employer",
        "observed_at": "2026-10-01T08:00:00+00:00",
        **kwargs,
    }


class PresentationExtractionTests(SimpleTestCase):
    def test_company_heading_excludes_team_and_role(self):
        text = "Nebula builds software products for organisations throughout Europe and provides reliable data tools."
        self.assertEqual(
            extract_presentation(
                f"About Nebula\n\n{text}\n\nAbout the team\n\nBuild tools.", "Nebula"
            ),
            text,
        )
        self.assertIsNone(extract_presentation(f"About the role\n\n{text}", "Nebula"))
        self.assertIsNone(extract_presentation(f"À propos de vous\n\n{text}", "Nebula"))
        self.assertIsNone(
            extract_presentation(f"À propos de notre équipe\n\n{text}", "Nebula")
        )

    def test_structured_company_description_needs_matching_revision(self):
        text = "Nebula builds software products for organisations throughout Europe and provides reliable data tools."
        payload = {
            "jobAd": {"sections": {"companyDescription": {"text": f"<p>{text}</p>"}}}
        }
        self.assertEqual(extract_presentation(text, "Nebula", payload), text)
        self.assertIsNone(
            extract_presentation("Build tools in this internship.", "Nebula", payload)
        )

    def test_source_validation_rejects_unsafe_unsourced_and_unbounded_information(self):
        for invalid in [
            entry(source_url="javascript:alert(1)"),
            entry(source_url="https://secret:pass@example.com"),
            entry(observed_at="2026-10-01"),
            entry(key="private_contact"),
            entry(value="x" * 12001),
            entry(source_kind="inferred"),
        ]:
            with self.subTest(invalid=invalid), self.assertRaises(ValidationError):
                validate_sections([invalid])


@override_settings(ROOT_URLCONF=__name__)
class CompanyPageTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            name="Nebula", website_url="https://nebula.example"
        )
        self.other = Company.objects.create(name="Another employer")
        self.first = publishable(
            Offer.objects.create(
                company=self.company,
                title="Software internship",
                description="Internship in software.",
            )
        )
        self.second = publishable(
            Offer.objects.create(company=self.company, title="Design internship")
        )
        publishable(Offer.objects.create(company=self.other, title="Other internship"))
        self.location = Location.objects.create(
            name="Paris", city="Paris", country_code="FR", canonical_key="company-paris"
        )
        self.first.locations.add(self.location)

    def get(self, suffix="", query=None):
        return self.client.get(
            f"/api/v1/companies/{self.company.pk}/{suffix}", query or {}
        )

    def test_all_offers_and_count_preserve_company_publication_boundary(self):
        # Adversarial stale, expired, closed and unconfirmed offers remain unpublished.
        stale = publishable(
            Offer.objects.create(company=self.company, title="Stale internship")
        )
        stale.sources.update(last_checked_at=timezone.now() - timedelta(days=10))
        publishable(
            Offer.objects.create(
                company=self.company, title="Closed internship", status="closed"
            )
        )
        publishable(
            Offer.objects.create(
                company=self.company,
                title="Expired internship",
                expires_at=timezone.now() - timedelta(days=1),
            )
        )
        Offer.objects.create(company=self.company, title="Director")
        response = self.get()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["offers_count"], 2)
        self.assertEqual(
            response.json()["hiring_locations"][0]["locations__country_code"], "FR"
        )
        first = self.get("offers/", {"page_size": 1}).json()
        second = self.get("offers/", {"page_size": 1, "page": 2}).json()
        self.assertEqual(first["count"], 2)
        self.assertEqual(
            {first["results"][0]["id"], second["results"][0]["id"]},
            {self.first.pk, self.second.pk},
        )
        self.assertEqual(self.get("offers/", {"q": "software"}).json()["count"], 1)

    def test_empty_company_page_and_absent_company(self):
        empty = Company.objects.create(name="No current internships")
        response = self.client.get(f"/api/v1/companies/{empty.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["offers_count"], 0)
        self.assertEqual(len(response.json()["profile"]["missing_sections"]), 9)
        self.assertEqual(self.client.get("/api/v1/companies/999999/").status_code, 404)

    def test_invalid_admin_bypass_data_is_not_published_and_text_is_literal(self):
        CompanyProfile.objects.create(
            company=self.company,
            sections=[
                entry(value='<img src=x onerror="unsafe()">'),
                entry(key="benefits", source_url="javascript:alert(1)"),
            ],
        )
        self.company.website_url = "javascript:alert(1)"
        self.company.save()
        data = self.get().json()
        self.assertIsNone(data["website_url"])
        self.assertEqual(len(data["profile"]["sections"]), 1)
        self.assertIn("<img", data["profile"]["sections"][0]["value"])
        self.assertNotIn("logo_last_error", data)

    def test_personalized_feed_filters_company_without_changing_all_offers(self):
        user = get_user_model().objects.create_user(
            username="candidate", password="test-password"
        )
        profile, _ = CandidateProfile.objects.get_or_create(user=user)
        preference = SearchPreference.objects.create(profile=profile)
        PreferenceContract.objects.create(preference=preference, value="internship")
        PreferenceWorkMode.objects.create(preference=preference, value="remote")
        self.client.force_login(user)
        response = self.client.get(
            "/api/v1/recommendations/", {"company": self.company.pk}
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            {row["offer"]["company"]["id"] for row in response.json()["results"]},
            {self.company.pk},
        )
        self.assertEqual(self.get("offers/").json()["count"], 2)
        self.assertEqual(
            self.client.get("/api/v1/recommendations/", {"company": "bad"}).status_code,
            400,
        )

    def test_enrichment_is_idempotent_and_preserves_reviewed_content(self):
        self.first.description = "About Nebula\n\nNebula builds software products for organisations throughout Europe and provides reliable data tools.\n\nResponsibilities\n\nBuild features."
        self.first.save()
        source = self.first.sources.first()
        self.assertTrue(enrich_company_from_offer(self.first, source))
        self.assertFalse(enrich_company_from_offer(self.first, source))
        profile = CompanyProfile.objects.get(company=self.company)
        self.assertEqual(profile.sections[0]["offer_id"], self.first.pk)
        self.assertEqual(profile.sections[0]["source_url"], source.apply_url)
        profile.sections = [entry(value="Reviewed official presentation.")]
        profile.save()
        call_command(
            "enrich_company_profiles", company_id=self.company.pk, stdout=StringIO()
        )
        profile.refresh_from_db()
        self.assertEqual(
            profile.sections[0]["value"], "Reviewed official presentation."
        )

    def test_reviewed_import_preserves_other_sections_and_checks_company_identity(self):
        CompanyProfile.objects.create(
            company=self.company,
            sections=[entry(key="culture", value="Existing culture.")],
        )
        with NamedTemporaryFile(mode="w+", suffix=".json") as stream:
            json.dump(
                [
                    {
                        "company_id": self.company.pk,
                        "company_name": self.company.name,
                        "sections": [entry()],
                    }
                ],
                stream,
            )
            stream.flush()
            call_command(
                "enrich_company_profiles", import_file=stream.name, stdout=StringIO()
            )
            call_command(
                "enrich_company_profiles", import_file=stream.name, stdout=StringIO()
            )
        profile = CompanyProfile.objects.get(company=self.company)
        self.assertEqual(
            [item["key"] for item in profile.sections], ["culture", "presentation"]
        )
        with NamedTemporaryFile(mode="w+", suffix=".json") as stream:
            json.dump(
                [
                    {
                        "company_id": self.company.pk,
                        "company_name": "Wrong employer",
                        "sections": [entry()],
                    }
                ],
                stream,
            )
            stream.flush()
            with self.assertRaises(CommandError):
                call_command("enrich_company_profiles", import_file=stream.name)

    def test_reviewed_import_rolls_back_every_company_when_a_later_entry_is_invalid(
        self,
    ):
        with NamedTemporaryFile(mode="w+", suffix=".json") as stream:
            json.dump(
                [
                    {"company_id": self.company.pk, "sections": [entry()]},
                    {
                        "company_id": self.other.pk,
                        "sections": [entry(source_url="javascript:alert(1)")],
                    },
                ],
                stream,
            )
            stream.flush()
            with self.assertRaises(ValidationError):
                call_command("enrich_company_profiles", import_file=stream.name)
        self.assertFalse(CompanyProfile.objects.exists())
