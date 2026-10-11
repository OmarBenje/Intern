from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from jobboard.models import CandidateProfile
from jobboard.tests.test_documents_api import pdf_bytes


@override_settings(
    PRIVATE_STORAGE_BACKEND="local",
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class OnboardingTests(TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.override = override_settings(PRIVATE_STORAGE_ROOT=self.directory.name)
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.user = get_user_model().objects.create_user(
            username="onboarding", password="test"
        )
        self.client.force_login(self.user)
        self.address = {
            "street_address": "11 rue Exemple",
            "city": "Marseille",
            "postal_code": "13001",
            "district": "",
            "region": "",
            "country_code": "FR",
        }
        self.eligibility = {
            "citizenships": ["MA"],
            "work_authorizations": [
                {
                    "country_code": "FR",
                    "authorized": True,
                    "needs_sponsorship": False,
                    "authorization_basis": "student",
                }
            ],
        }

    def step(self):
        return self.client.get("/api/v1/auth/me/").json()["user"]["onboarding_step"]

    def put(self, step, data):
        return self.client.put(
            "/api/v1/onboarding/" + step + "/", data, content_type="application/json"
        )

    def resume(self):
        document = self.client.post(
            "/api/v1/documents/",
            {
                "kind": "resume",
                "file": SimpleUploadedFile(
                    "cv.pdf", pdf_bytes(), content_type="application/pdf"
                ),
            },
        ).json()
        response = self.client.put(
            "/api/v1/profile/resume/",
            {"document_id": document["id"]},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)

    def test_resume_address_eligibility_persist_across_sessions(self):
        self.assertEqual(self.step(), "resume")
        self.assertEqual(self.put("address", self.address).status_code, 409)
        self.assertEqual(
            self.put("work-eligibility", self.eligibility).status_code, 409
        )
        self.resume()
        self.assertEqual(self.step(), "address")
        self.assertEqual(self.put("address", self.address).status_code, 200)
        self.client.logout()
        self.client.force_login(self.user)
        self.assertEqual(self.step(), "work-eligibility")
        self.assertEqual(
            self.client.get("/api/v1/onboarding/").json()["address"], self.address
        )
        self.assertEqual(
            self.put("work-eligibility", self.eligibility).status_code, 200
        )
        self.assertEqual(self.step(), "complete")
        profile = CandidateProfile.objects.get(user=self.user)
        self.assertEqual(profile.citizenships, ["MA"])
        self.assertEqual(
            profile.work_authorizations.get().authorization_basis, "student"
        )
        self.assertIsNotNone(profile.onboarding_completed_at)
        self.client.logout()
        self.client.force_login(self.user)
        self.assertEqual(self.step(), "complete")

    def test_invalid_or_incomplete_answers_cannot_complete_onboarding(self):
        self.resume()
        self.assertEqual(
            self.put("address", {**self.address, "city": "  "}).status_code, 400
        )
        self.assertEqual(
            self.put("address", {**self.address, "country_code": "XX"}).status_code, 400
        )
        self.put("address", self.address)
        for rows in (
            [],
            [{**self.eligibility["work_authorizations"][0], "authorized": None}],
            self.eligibility["work_authorizations"] * 2,
        ):
            self.assertEqual(
                self.put(
                    "work-eligibility",
                    {**self.eligibility, "work_authorizations": rows},
                ).status_code,
                400,
            )
        self.assertEqual(self.step(), "work-eligibility")

    def test_other_user_cannot_read_answers_or_write_completion_flag(self):
        self.resume()
        self.put("address", self.address)
        self.assertEqual(
            self.put(
                "work-eligibility",
                {**self.eligibility, "onboarding_completed_at": "2026-09-30"},
            ).status_code,
            400,
        )
        other = get_user_model().objects.create_user(username="other")
        self.client.force_login(other)
        self.assertEqual(
            self.client.get("/api/v1/onboarding/").json()["address"]["street_address"],
            "",
        )
        self.assertEqual(self.step(), "resume")
        self.client.logout()
        self.assertEqual(self.client.get("/api/v1/onboarding/").status_code, 401)
