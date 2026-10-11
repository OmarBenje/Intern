from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import include, path
from django.utils import timezone

from jobboard.models import (
    CandidateProfile,
    Company,
    CompanyPreference,
    Location,
    Offer,
    OfferFeedback,
    PreferenceContract,
    PreferenceWorkMode,
    Role,
    SearchPreference,
    Skill,
    WorkAuthorization,
)
from jobboard.services.catalogue_search import search_offers
from jobboard.tests.engine_fixtures import publishable

urlpatterns = [path("api/v1/", include("jobboard.api.catalogue"))]


@override_settings(ROOT_URLCONF=__name__)
class SearchDocumentTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Nébula Labs")

    def offer(self, title, **kwargs):
        return publishable(
            Offer.objects.create(company=self.company, title=title, **kwargs)
        )

    def results(self, query):
        response = self.client.get("/api/v1/offers/", {"q": query})
        self.assertEqual(response.status_code, 200, response.content)
        return [row["id"] for row in response.json()["results"]]

    def test_accents_ligatures_and_mixed_company_query(self):
        offer = self.offer("Stage création logiciel", description="Œuvre pédagogique")
        self.assertEqual(self.results("nebula creation"), [offer.pk])
        self.assertEqual(self.results("œuvre"), [offer.pk])
        self.assertEqual(self.results("oeuvre pedagogique"), [offer.pk])

    def test_technical_tokens_do_not_collapse_to_c_or_net(self):
        cpp = self.offer("C++ Internship")
        csharp = self.offer("C# Internship")
        dotnet = self.offer(".NET Internship")
        self.offer("C Internship", description="net income")
        for query, offer in [
            ("C++", cpp),
            ("cpp", cpp),
            ("C#", csharp),
            (".NET", dotnet),
        ]:
            self.assertEqual(self.results(query), [offer.pk])

    def test_swe_and_developer_aliases_preserve_other_required_terms(self):
        offer = self.offer("Software Development Internship Python")
        self.offer("Software Engineer Intern Java")
        for query in [
            "SWE Python",
            "développeur logiciel Python",
            "développeuse Python",
        ]:
            self.assertEqual(self.results(query), [offer.pk])

    def test_dotnet_preserves_a_separate_token_in_aspnet(self):
        offer = self.offer("ASP.NET Internship")
        self.assertEqual(self.results(".NET"), [offer.pk])
        self.assertEqual(self.results("ASP.NET"), [offer.pk])

    def test_bulk_and_direct_sql_updates_keep_document_current(self):
        offer = Offer.objects.bulk_create(
            [Offer(company=self.company, title="Python Intern", description="Django")]
        )[0]
        publishable(offer)
        self.assertEqual(self.results("nebula Python"), [offer.pk])
        Offer.objects.filter(pk=offer.pk).update(
            title="Rust Intern", description="Tokio"
        )
        self.assertEqual(self.results("Python"), [])
        self.assertEqual(self.results("Tokio"), [offer.pk])
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE jobboard_company SET name=%s WHERE id=%s",
                ["Renommée Labs", self.company.pk],
            )
        self.assertEqual(self.results("nebula"), [])
        self.assertEqual(self.results("renommee Rust"), [offer.pk])
        second = Company.objects.create(name="Other Employer")
        Offer.objects.filter(pk=offer.pk).update(company=second)
        self.assertEqual(self.results("renommee"), [])
        self.assertEqual(self.results("Other Rust"), [offer.pk])

    def test_rollback_does_not_leave_a_renamed_document(self):
        offer = self.offer("Python Intern")
        try:
            with transaction.atomic():
                Company.objects.filter(pk=self.company.pk).update(name="Rolled back")
                self.assertEqual(self.results("Rolled"), [offer.pk])
                raise ValueError("rollback")
        except ValueError:
            pass
        self.assertEqual(self.results("Rolled"), [])
        self.assertEqual(self.results("nebula"), [offer.pk])

    def test_operator_semantics_and_punctuation(self):
        cpp = self.offer("C++ Intern")
        python = self.offer("Python Intern")
        self.assertEqual(set(self.results("C++ OR Python")), {cpp.pk, python.pk})
        self.assertEqual(self.results('"C++" -Python'), [cpp.pk])
        self.assertEqual(self.results("Intern -C++"), [python.pk])
        for query in ["...", "!!!", '"', "---"]:
            self.assertEqual(self.results(query), [])

    def test_query_can_use_document_index(self):
        # A tiny fixture may legitimately choose a sequential scan. Disable it
        # inside this transaction to prove the filter supports the GIN index.
        self.offer("UniquePython Intern")
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL enable_seqscan = off")
        plan = search_offers(Offer.objects.all(), "UniquePython").explain()
        self.assertIn("offer_document_idx", plan)

    def test_suggestion_operator_can_use_the_trigram_index(self):
        from jobboard.services.catalogue_search import search_text

        self.offer("Python Internship")
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL enable_seqscan = off")
        plan = Offer.objects.filter(
            search_title__trigram_word_similar=search_text("pythonn")
        ).explain()
        self.assertIn("offer_title_trgm_idx", plan)

    def test_listing_never_fetches_description_or_document_or_match_facts(self):
        self.offer("Python Intern", description="sensitive large body")
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get("/api/v1/offers/", {"q": "Python"})
        self.assertEqual(response.status_code, 200)
        select = next(
            item["sql"]
            for item in queries
            if 'FROM "jobboard_offer"' in item["sql"] and "COUNT(" not in item["sql"]
        )
        projection = select.split(" FROM ")[0]
        for field in [
            '."description"',
            '."search_vector"',
            '."search_title"',
            '."facts"',
            '."content"',
        ]:
            self.assertNotIn(field, projection)
        self.assertNotIn('"search_document" AS', projection)

    def test_suggestions_use_same_filters_and_publication_boundary(self):
        visible = self.offer("Python Internship", work_mode="remote")
        self.offer("Python Onsite Internship", work_mode="onsite")
        hidden = self.offer(
            "Python Hidden Internship", status="hidden", work_mode="remote"
        )
        outside = self.offer("Python Outside Internship", work_mode="remote")
        outside.enrichment.europe_status = "out_of_scope"
        outside.enrichment.save()
        stale = self.offer("Python Stale Internship", work_mode="remote")
        stale.sources.update(last_checked_at=timezone.now() - timedelta(days=4))
        expired = self.offer(
            "Python Expired Internship",
            work_mode="remote",
            expires_at=timezone.now() - timedelta(days=1),
        )
        response = self.client.get(
            "/api/v1/offers/suggestions/",
            {
                "q": "pythonn",
                "work_mode": "remote",
                "include_unknown": "false",
                "country_codes": "FR",
            },
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["suggestions"], [{"query": visible.title}])
        self.assertEqual(self.results("pythonn"), [])
        self.assertTrue(hidden.pk and expired.pk)

    def test_suggestions_are_unique_bounded_and_skip_operators(self):
        for index in range(7):
            self.offer(f"Python Internship {index}")
        self.offer("Python Internship 0")
        response = self.client.get("/api/v1/offers/suggestions/", {"q": "pythonn"})
        suggestions = response.json()["suggestions"]
        self.assertEqual(len(suggestions), 3)
        self.assertEqual(len({item["query"] for item in suggestions}), 3)
        for query in [
            "",
            "py",
            "---",
            "Python OR Rust",
            "Python -Java",
            '"Python"',
            "x" * 101,
        ]:
            self.assertEqual(
                self.client.get("/api/v1/offers/suggestions/", {"q": query}).json()[
                    "suggestions"
                ],
                [],
            )
        self.assertEqual(
            self.client.get(
                "/api/v1/offers/suggestions/", {"q": "pythonn", "sort": "invalid"}
            ).status_code,
            400,
        )


@override_settings(ROOT_URLCONF=__name__)
class RecommendationRankingTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="rank-reader")
        self.client.force_login(self.user)
        self.company = Company.objects.create(name="Preference Labs")
        self.role = Role.objects.create(name="Software Engineer", slug="software")
        self.location = Location.objects.create(
            name="Paris", canonical_key="fr-paris", country_code="FR"
        )
        self.profile, _ = CandidateProfile.objects.get_or_create(user=self.user)
        self.preference = SearchPreference.objects.create(profile=self.profile)
        self.preference.roles.add(self.role)
        self.preference.locations.add(self.location)
        PreferenceContract.objects.create(
            preference=self.preference, value="internship"
        )
        PreferenceWorkMode.objects.create(preference=self.preference, value="remote")
        WorkAuthorization.objects.create(
            profile=self.profile,
            country_code="FR",
            confirmed_at=timezone.now(),
            needs_sponsorship=False,
        )
        self.skills = [
            Skill.objects.create(name=f"Skill {i}", slug=f"rank-skill-{i}")
            for i in range(4)
        ]
        self.profile.skills.add(*self.skills)

    def offer(self, title, **kwargs):
        return publishable(
            Offer.objects.create(
                company=self.company,
                title=title,
                contract_type="internship",
                work_mode="remote",
                **kwargs,
            )
        )

    def results(self, **params):
        response = self.client.get("/api/v1/recommendations/", params)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()["results"]

    def test_preferences_rank_before_pagination_and_newest_override(self):
        older = self.offer(
            "Python Intern",
            role=self.role,
            published_at=timezone.now() - timedelta(days=12),
        )
        older.locations.add(self.location)
        older.skills.add(*self.skills)
        newest = self.offer("Python Intern", published_at=timezone.now())
        page = self.results(page_size=1)
        self.assertEqual(page[0]["offer"]["id"], older.pk)
        self.assertEqual(page[0]["ranking"], {"score": 36, "version": "preferences-taxonomy-2"})
        self.assertEqual(self.results(page_size=1, page=2)[0]["offer"]["id"], newest.pk)
        self.assertEqual(
            self.results(page_size=1, sort="newest")[0]["offer"]["id"], newest.pk
        )
        self.assertEqual(
            self.results(page_size=1, q="Python")[0]["offer"]["id"], older.pk
        )
        self.assertEqual(
            {item["code"] for item in page[0]["reasons"]},
            {
                "preferred_role",
                "preferred_location",
                "profile_skills",
                "preferred_contract",
                "preferred_work_mode",
            },
        )

    def test_unknown_modes_do_not_receive_preference_bonus(self):
        known = self.offer("Known")
        unknown = self.offer("Unknown")
        Offer.objects.filter(pk=unknown.pk).update(work_mode="unknown")
        results = {item["offer"]["id"]: item for item in self.results()}
        self.assertEqual(results[known.pk]["ranking"]["score"], 4)
        self.assertEqual(results[unknown.pk]["ranking"]["score"], 2)
        self.assertIn("work_mode", results[unknown.pk]["unknown_fields"])

    def test_exclusions_and_other_users_preferences_never_change_catalogue(self):
        dismissed = self.offer("Dismissed", role=self.role)
        OfferFeedback.objects.create(
            user=self.user, offer=dismissed, reason="not_interested"
        )
        excluded_company = Company.objects.create(name="Excluded")
        excluded = self.offer("Excluded", role=self.role)
        Offer.objects.filter(pk=excluded.pk).update(company=excluded_company)
        CompanyPreference.objects.create(
            user=self.user, company=excluded_company, excluded=True
        )
        self.assertEqual(self.results(), [])
        catalogue = self.client.get("/api/v1/offers/").json()
        self.assertEqual(catalogue["count"], 2)
        other = get_user_model().objects.create_user(username="other-ranking-reader")
        self.client.force_login(other)
        data = self.client.get("/api/v1/recommendations/").json()
        self.assertEqual(data["count"], 0)
        self.assertTrue(data["onboarding_required"])

    def test_authorization_and_rank_queries_are_bounded_per_page(self):
        for index in range(21):
            offer = self.offer(f"Intern {index}", role=self.role)
            offer.locations.add(self.location)
            offer.skills.add(*self.skills)
        with CaptureQueriesContext(connection) as small:
            self.results(page_size=1)
        with CaptureQueriesContext(connection) as large:
            self.results(page_size=20)
        self.assertEqual(len(small), len(large))
        # The workspace permission performs one constant-time recruiter role check.
        self.assertEqual(
            sum('FROM "jobboard_recruiterprofile"' in query["sql"] for query in large),
            1,
        )
        self.assertLessEqual(len(large), 17)
