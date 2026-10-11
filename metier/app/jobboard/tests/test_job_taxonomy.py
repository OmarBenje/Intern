from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import include, path
from django.utils import timezone

from jobboard.models import CandidateProfile, Company, JobSubdomain, Offer
from jobboard.services.job_taxonomy import assign_taxonomy, classify, seed_taxonomy
from jobboard.tests.engine_fixtures import publishable

urlpatterns = [
    path("api/v1/", include("jobboard.api.catalogue")),
    path("api/v1/", include("jobboard.api.taxonomy")),
    path("api/v1/", include("jobboard.api.engine")),
    path("api/v1/", include("jobboard.api.profiles")),
]


@override_settings(ROOT_URLCONF=__name__)
class JobTaxonomyTests(TestCase):
    def setUp(self):
        seed_taxonomy()
        self.company = Company.objects.create(name="Test bank")

    def offer(self, title, description=""):
        offer = publishable(
            Offer.objects.create(
                company=self.company,
                title=title,
                description=description,
                contract_type="internship",
                work_mode="onsite",
            )
        )
        assign_taxonomy(offer)
        offer.refresh_from_db()
        return offer

    def results(self, **params):
        response = self.client.get("/api/v1/offers/", params)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def test_classification_functions_not_industry_or_skills(self):
        for title, expected in [
            ("Backend Developer Intern at a bank", "backend"),
            ("Backend-Entwickler Praktikum", "backend"),
            ("Développeuse back-end", "backend"),
            ("Mechanical Design Intern", "mechanical"),
            ("Product Marketing Intern", "product-marketing"),
            ("Data Engineer Intern", "data-engineering"),
            (
                "SAP Full-Stack Developer Intern - AI & Data Transformation",
                "full-stack",
            ),
            (
                "Stage - Assistant Chef de Projet événementiel - PARIS H/F",
                "event-management",
            ),
            ("Juriste Stagiaire - Droit Commercial", "business-law"),
            ("Software Engineer Intern", "software-generalist"),
        ]:
            with self.subTest(title=title):
                self.assertEqual(classify(title)["primary"], expected)
        self.assertEqual(
            classify(
                "Marketing Intern",
                "SQL and Python are appreciated. We are a software company.",
            )["primary"],
            "marketing-generalist",
        )
        self.assertEqual(classify("Business Intern")["status"], "unclassified")
        self.assertEqual(classify("Backend Marketing Intern")["status"], "needs_review")

    def test_missions_can_specialize_but_skill_lists_cannot(self):
        result = classify(
            "Data Intern",
            "<h2>Responsibilities</h2><li>Build data engineering pipelines.</li><h2>Skills</h2><li>Machine learning and SQL.</li>",
        )
        self.assertEqual(result["primary"], "data-engineering")
        self.assertEqual(result["candidates"][0]["field"], "offer.description")
        self.assertEqual(
            classify("Marketing Intern", "Develop backend software for our team.")[
                "primary"
            ],
            "marketing-generalist",
        )

    def test_strict_union_filters_counts_no_secondary_duplicates(self):
        backend = self.offer("Backend Intern")
        frontend = self.offer("Frontend Intern")
        transverse = self.offer("Backend and Frontend Intern")
        unknown = self.offer("Business Intern")
        self.assertEqual(transverse.secondary_subdomains.count(), 1)
        data = self.results(subdomains="backend,frontend", include_unknown="true")
        self.assertEqual(data["count"], 3)
        self.assertEqual(
            {r["id"] for r in data["results"]}, {backend.pk, frontend.pk, transverse.pk}
        )
        self.assertNotIn(unknown.pk, {r["id"] for r in data["results"]})
        self.assertEqual(self.results(domains="software-it")["count"], 3)
        taxonomy = self.client.get(
            "/api/v1/taxonomy/", {"subdomains": "backend"}
        ).json()
        domain = next(d for d in taxonomy["domains"] if d["slug"] == "software-it")
        self.assertEqual(domain["count"], 3)
        self.assertEqual(
            next(s for s in domain["subdomains"] if s["slug"] == "frontend")["count"], 2
        )
        frontend.sources.update(last_checked_at=timezone.now() - timedelta(days=10))
        domain = next(
            d
            for d in self.client.get("/api/v1/taxonomy/").json()["domains"]
            if d["slug"] == "software-it"
        )
        self.assertEqual(domain["count"], 2)

    def test_validation_saved_search_and_preference_roundtrip(self):
        for params in [
            {"domains": "made-up"},
            {"subdomains": "made-up"},
            {"domains": "software-it", "domain": "it-data"},
        ]:
            self.assertEqual(
                self.client.get("/api/v1/offers/", params).status_code, 400
            )
        user = get_user_model().objects.create_user(username="taxonomy-reader")
        self.client.force_login(user)
        response = self.client.post(
            "/api/v1/saved-searches/",
            {
                "name": "Jobs",
                "criteria": {
                    "domains": ["software-it"],
                    "subdomains": ["backend", "analytics"],
                },
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["criteria"]["subdomains"], ["analytics"])
        response = self.client.put(
            "/api/v1/preferences/",
            {
                "domains": ["software-it"],
                "subdomains": ["analytics"],
                "excluded_subdomains": ["frontend"],
                "contracts": ["internship"],
                "work_modes": ["onsite"],
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["subdomains"], ["analytics"])
        response = self.client.put(
            "/api/v1/preferences/",
            {"domains": ["invalid"]},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            self.client.get("/api/v1/preferences/").json()["domains"], ["software-it"]
        )

    def test_recommendations_before_pagination_and_exclusions(self):
        user = get_user_model().objects.create_user(username="taxonomy-matches")
        CandidateProfile.objects.create(user=user, full_name="Candidate")
        self.client.force_login(user)
        self.client.put(
            "/api/v1/preferences/",
            {
                "domains": ["software-it"],
                "subdomains": ["analytics"],
                "excluded_subdomains": ["frontend"],
                "contracts": ["internship"],
                "work_modes": ["onsite"],
            },
            content_type="application/json",
        )
        precise = self.offer("Data Analyst Intern")
        self.offer("Backend Intern")
        blocked = self.offer("Frontend Intern")
        response = self.client.get("/api/v1/recommendations/", {"page_size": 1})
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertEqual(data["count"], 2)
        self.assertEqual(data["results"][0]["offer"]["id"], precise.pk)
        self.assertEqual(
            data["results"][0]["reasons"][0]["code"], "preferred_subdomain"
        )
        self.assertNotEqual(data["results"][0]["offer"]["id"], blocked.pk)

    def test_reclassification_idempotent_and_manual_corrections_preserved(self):
        offer = self.offer("Backend Intern")
        original = offer.taxonomy_input_hash
        assign_taxonomy(offer)
        offer.refresh_from_db()
        self.assertEqual(offer.taxonomy_input_hash, original)
        Offer.objects.filter(pk=offer.pk).update(
            taxonomy_manual=True,
            job_subdomain=JobSubdomain.objects.get(slug="analytics"),
        )
        assign_taxonomy(offer)
        offer.refresh_from_db()
        self.assertEqual(offer.job_subdomain.slug, "analytics")
        Offer.objects.filter(pk=offer.pk).update(title="Marketing Intern")
        assign_taxonomy(offer)
        offer.refresh_from_db()
        self.assertEqual(offer.taxonomy_status, "needs_review")
        self.assertEqual(offer.job_subdomain.slug, "analytics")
        self.assertEqual(self.results(subdomains="analytics")["count"], 0)
