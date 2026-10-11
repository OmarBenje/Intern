import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import include, path

from jobboard.models import CandidateProfile, Experience
from jobboard.services.profiles import snapshot_profile

urlpatterns = [path("api/v1/", include("jobboard.api.profiles"))]


@override_settings(
    ROOT_URLCONF=__name__,
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class ProfileAPITests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="alice", password="password"
        )
        self.other = get_user_model().objects.create_user(
            username="bob", password="password"
        )
        self.client.force_login(self.user)

    def send(self, path, data, method="patch"):
        return getattr(self.client, method)(
            "/api/v1/" + path, json.dumps(data), content_type="application/json"
        )

    def test_read_does_not_create_and_profile_version_changes(self):
        self.assertEqual(self.client.get("/api/v1/profile/").json(), {"profile": None})
        self.assertEqual(CandidateProfile.objects.count(), 0)
        response = self.send(
            "profile/", {"full_name": "Alice", "available_from": "2027-06-01"}
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["profile_version"], 2)
        snap = snapshot_profile(self.user)
        self.send("profile/", {"full_name": "Alice Changed"})
        self.assertEqual(snap["full_name"], "Alice")
        self.assertEqual(snap["available_from"], "2027-06-01")
        self.assertEqual(
            CandidateProfile.objects.get(user=self.user).profile_version, 3
        )

    def test_child_ownership_and_transactional_validation(self):
        profile = CandidateProfile.objects.create(user=self.other, full_name="Bob")
        child = Experience.objects.create(
            profile=profile, company_name="Employer", title="Engineer"
        )
        self.assertEqual(
            self.send(
                f"profile/experiences/{child.pk}/", {"title": "Stolen"}
            ).status_code,
            404,
        )
        response = self.send(
            "profile/experiences/",
            {
                "company_name": "A",
                "title": "Intern",
                "is_current": True,
                "end_date": "2026-01-01",
            },
            "post",
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertFalse(CandidateProfile.objects.filter(user=self.user).exists())
        response = self.send(
            "profile/experiences/", {"company_name": "A", "title": "Intern"}, "post"
        )
        self.assertEqual(response.status_code, 200, response.content)
        pk = response.json()["id"]
        self.assertEqual(
            self.client.delete(f"/api/v1/profile/experiences/{pk}/").status_code, 204
        )
        self.assertEqual(
            CandidateProfile.objects.get(user=self.user).profile_version, 3
        )

    def test_preferences_complete_salary_and_choice_rollback(self):
        response = self.send("preferences/", {"minimum_salary": "1000"}, "put")
        self.assertEqual(response.status_code, 400, response.content)
        response = self.send(
            "preferences/",
            {
                "minimum_salary": "1000",
                "salary_currency": "EUR",
                "salary_period": "month",
                "contracts": ["internship"],
                "work_modes": ["remote"],
            },
            "put",
        )
        self.assertEqual(response.status_code, 200, response.content)
        version = CandidateProfile.objects.get(user=self.user).profile_version
        response = self.send("preferences/", {"contracts": ["unknown"]}, "put")
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(
            self.client.get("/api/v1/preferences/").json()["contracts"], ["internship"]
        )
        self.assertEqual(
            CandidateProfile.objects.get(user=self.user).profile_version, version
        )

    def test_server_owned_fields_rejected(self):
        for field in ("user_id", "profile_version", "current_resume_id", "resume_url"):
            self.assertEqual(self.send("profile/", {field: 123}).status_code, 400)
        self.assertEqual(self.send("profile/", {"skill_ids": None}).status_code, 400)
        self.assertEqual(
            self.send(
                "profile/work-authorizations/",
                {"country_code": "FR", "authorized": "yes"},
                "post",
            ).status_code,
            400,
        )
