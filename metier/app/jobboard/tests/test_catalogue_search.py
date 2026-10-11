from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import include, path
from django.utils import timezone

from jobboard.models import Company, Offer
from jobboard.services.engine_filters import filter_catalogue
from jobboard.services.engine_matching import preselect_offers
from jobboard.tests.engine_fixtures import publishable

urlpatterns = [
    path("api/v1/", include("jobboard.api.catalogue")),
    path("api/v1/", include("jobboard.api.engine")),
]


@override_settings(ROOT_URLCONF=__name__)
class CatalogueSearchTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Nebula Robotics")

    def offer(self, title, **kwargs):
        return publishable(
            Offer.objects.create(company=self.company, title=title, **kwargs)
        )

    def results(self, **params):
        response = self.client.get("/api/v1/offers/", params)
        self.assertEqual(response.status_code, 200, response.content)
        return [row["id"] for row in response.json()["results"]]

    def test_multilingual_aliases_keep_other_terms_required(self):
        wanted = self.offer("Software Engineer Intern Python")
        self.offer("Software Engineer Intern Java")
        self.offer("Marketing Intern Python")
        self.assertEqual(self.results(q="stage développeur Python"), [wanted.pk])
        self.assertEqual(
            list(
                preselect_offers(
                    Offer.objects.all(), {"q": "stage développeur Python"}
                ).values_list("id", flat=True)
            ),
            [wanted.pk],
        )

    def test_company_and_mixed_query_and_live_company_rename(self):
        wanted = self.offer("Python Internship")
        self.offer("Marketing Internship")
        self.assertEqual(self.results(q="Nebula Python"), [wanted.pk])
        self.company.name = "Renamed Labs"
        self.company.save()
        self.assertEqual(self.results(q="Nebula"), [])
        self.assertEqual(len(self.results(q="Renamed")), 2)

    def test_relevance_prefers_title_but_newest_is_available(self):
        title = self.offer(
            "Python Intern", published_at=timezone.now() - timedelta(days=10)
        )
        description = self.offer(
            "Marketing Intern", description="Python", published_at=timezone.now()
        )
        self.assertEqual(self.results(q="Python"), [title.pk, description.pk])
        self.assertEqual(
            self.results(q="Python", sort="newest"), [description.pk, title.pk]
        )

    def test_explicit_quotes_or_and_exclusions_preserved(self):
        python = self.offer("Python Internship")
        marketing = self.offer("Marketing Internship")
        self.assertEqual(
            set(self.results(q="Python OR Marketing")), {python.pk, marketing.pk}
        )
        self.assertEqual(self.results(q="Internship -Marketing"), [python.pk])
        self.assertEqual(self.results(q='"stage développeur"'), [])

    def test_recency_uses_known_publication_not_import_date(self):
        recent = self.offer("Recent", published_at=timezone.now() - timedelta(days=2))
        self.offer("Old", published_at=timezone.now() - timedelta(days=10))
        self.offer("Unknown")
        self.offer("Future", published_at=timezone.now() + timedelta(days=1))
        self.assertEqual(self.results(published_within="7"), [recent.pk])
        self.assertEqual(
            list(
                filter_catalogue(
                    Offer.objects.all(), {"published_within": "7"}
                ).values_list("id", flat=True)
            ),
            [recent.pk],
        )

    def test_invalid_filters_and_publication_boundary(self):
        hidden = self.offer("Python")
        hidden.enrichment.classification = "not_internship"
        hidden.enrichment.save()
        self.assertEqual(self.results(q="Python", unknown_policy="include"), [])
        for params in (
            {"sort": "random"},
            {"published_within": "0"},
            {"duration_min": 6, "duration_max": 3, "duration_unit": "months"},
        ):
            self.assertEqual(
                self.client.get("/api/v1/offers/", params).status_code, 400
            )

    def test_duration_overlap_unknown_policy_and_work_mode(self):
        offer = self.offer("Intern", work_mode="remote")
        offer.enrichment.facts = {
            "duration": {"value": {"minimum": 3, "maximum": 6, "unit": "months"}}
        }
        offer.enrichment.save()
        self.offer("Unknown duration", work_mode="onsite")
        self.assertEqual(
            self.results(
                duration_min=4,
                duration_max=5,
                duration_unit="months",
                include_unknown="false",
            ),
            [offer.pk],
        )
        self.assertEqual(self.results(work_mode="remote"), [offer.pk])
        self.assertEqual(
            self.results(
                duration_min=7, duration_unit="months", include_unknown="false"
            ),
            [],
        )

    def test_saved_search_round_trip_preserves_new_criteria(self):
        user = get_user_model().objects.create_user(username="search-reader")
        self.client.force_login(user)
        criteria = {
            "q": "développeur",
            "country_codes": ["FR", "DE"],
            "work_mode": "remote",
            "published_within": "7",
            "sort": "newest",
            "duration_min": 3,
            "duration_max": 6,
            "duration_unit": "months",
            "include_unknown": "false",
        }
        response = self.client.post(
            "/api/v1/saved-searches/",
            {"name": "Europe", "criteria": criteria},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        saved = self.client.get("/api/v1/saved-searches/").json()["results"][0][
            "criteria"
        ]
        for key, value in criteria.items():
            self.assertEqual(saved[key], value)
        self.assertEqual(saved["unknown_policy"], "exclude")
