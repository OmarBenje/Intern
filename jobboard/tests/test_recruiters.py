import hashlib
import re
from datetime import timedelta
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from jobboard import models as m
from jobboard.tests.test_documents_api import pdf_bytes


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    MAILERS={"default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}},
)
class RecruiterTests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.user = get_user_model().objects.create_user(
            username="recruiter",
            email="alice@company.test",
            password="Long-secret-password-239!",
        )
        self.owner = m.RecruiterProfile.objects.create(
            user=self.user, full_name="Alice Martin"
        )
        self.other_user = get_user_model().objects.create_user(
            username="other", email="other@company.test"
        )
        self.other = m.RecruiterProfile.objects.create(
            user=self.other_user, full_name="Other"
        )
        self.client.force_login(self.user)

    def send(self, path, data=None, method="post"):
        token = self.client.get("/api/v1/auth/csrf/").json()["csrf_token"]
        return getattr(self.client, method)(
            "/api/v1/" + path,
            data or {},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )

    def verified(self):
        self.owner.email_verified = True
        self.owner.verification_status = "verified"
        self.owner.company_name = "Example"
        self.owner.website_url = "https://company.test"
        self.owner.save()

    def create_job(self, active=False):
        response = self.send(
            "recruiter/jobs/",
            {
                "title": "Stage développement Python",
                "description": "Stage conventionné de six mois en développement Python.",
                "location": "Paris",
                "country_code": "FR",
                "status": "active" if active else "draft",
            },
        )
        self.assertEqual(response.status_code, 201, response.content)
        return m.RecruiterJob.objects.get(pk=response.json()["id"])

    def test_registration_role_and_legacy_candidate_default(self):
        self.client.logout()
        for role in ("recruiter", "candidate"):
            response = self.send(
                "auth/register/",
                {
                    "full_name": "New Person",
                    "email": f"{role}@business.test",
                    "password": "Long-secret-password-239!",
                    "role": role,
                },
            )
            self.assertEqual(response.status_code, 200, response.content)
            self.assertEqual(response.json()["user"]["role"], role)
            user_id = response.json()["user"]["id"]
            self.assertEqual(
                m.CandidateProfile.objects.filter(user_id=user_id).exists(),
                role == "candidate",
            )
            self.assertEqual(
                response.json()["user"]["onboarding_step"],
                "verify" if role == "recruiter" else "resume",
            )
        bad = self.send(
            "auth/register/",
            {
                "full_name": "New",
                "email": "bad@business.test",
                "password": "Long-secret-password-239!",
                "role": "admin",
            },
        )
        self.assertEqual(bad.status_code, 400)

    def test_personal_email_rejected(self):
        for domain in ("gmail.com", "yahoo.fr", "hotmail.com", "outlook.fr"):
            response = self.send(
                "auth/register/",
                {
                    "full_name": "New",
                    "email": "new@" + domain,
                    "password": "Long-secret-password-239!",
                    "role": "recruiter",
                },
            )
            self.assertEqual(response.status_code, 400)
            self.assertEqual(
                response.json()["error"]["code"], "professional_email_required"
            )

    def test_authentication_csrf_and_role_boundaries(self):
        self.assertEqual(
            self.client.post(
                "/api/v1/recruiter/jobs/", {}, content_type="application/json"
            ).status_code,
            403,
        )
        self.assertEqual(
            self.send("profile/", {"full_name": "Candidate"}, "patch").status_code, 403
        )
        candidate = get_user_model().objects.create_user(username="candidate")
        self.client.force_login(candidate)
        self.assertEqual(
            self.client.get("/api/v1/recruiter/dashboard/").status_code, 403
        )
        self.client.logout()
        self.assertEqual(self.client.get("/api/v1/recruiter/jobs/").status_code, 401)

    def test_email_verification_then_manual_company_review(self):
        data = {
            "company_name": "Example",
            "siren": "732829320",
            "website_url": "https://company.test",
        }
        self.assertEqual(self.send("recruiter/verify/", data).status_code, 409)
        response = self.send("recruiter/verify/send-code/")
        self.assertEqual(response.status_code, 200, response.content)
        code = re.search(r"\b\d{6}\b", mail.outbox[-1].body)[0]
        self.owner.refresh_from_db()
        self.assertNotEqual(self.owner.email_code_hash, code)
        self.assertEqual(
            self.send("recruiter/verify/code/", {"code": "wrong"}).status_code, 400
        )
        self.assertEqual(
            self.send("recruiter/verify/code/", {"code": code}).status_code, 200
        )
        self.assertEqual(
            self.send("recruiter/verify/code/", {"code": code}).status_code, 400
        )
        self.assertEqual(
            self.send("recruiter/verify/", {**data, "siren": "000000000"}).status_code,
            400,
        )
        response = self.send("recruiter/verify/", data)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["verification_status"], "pending")
        self.assertEqual(
            self.client.get("/api/v1/auth/me/").json()["user"]["onboarding_step"],
            "complete",
        )
        self.assertEqual(
            self.send(
                "recruiter/verify/", {**data, "verification_status": "verified"}
            ).status_code,
            400,
        )

    def test_job_owner_isolation_and_no_company_claim_by_domain(self):
        job = self.create_job()
        self.client.force_login(self.other_user)
        for method, suffix, body in (
            ("get", "", {}),
            ("patch", "", {"title": "Stolen"}),
            ("post", "duplicate/", {}),
            ("get", "applicants/", {}),
        ):
            path = f"recruiter/jobs/{job.pk}/{suffix}"
            response = (
                self.client.get("/api/v1/" + path)
                if method == "get"
                else self.send(path, body, method)
            )
            self.assertEqual(response.status_code, 404, response.content)
        self.assertEqual(self.client.get("/api/v1/recruiter/jobs/").json()["count"], 0)
        self.assertEqual(
            self.send(
                "recruiter/jobs/", {"title": "Attack", "owner": self.owner.pk}
            ).status_code,
            400,
        )

    def test_publish_requires_verified_company_and_rolls_back(self):
        job = self.create_job()
        response = self.send(f"recruiter/jobs/{job.pk}/", {"status": "active"}, "patch")
        self.assertEqual(response.status_code, 409)
        job.refresh_from_db()
        self.assertEqual(job.status, "draft")
        self.assertIsNone(job.offer_id)

    def test_publish_visible_in_catalogue_suspend_and_duplicate(self):
        self.verified()
        job = self.create_job(active=True)
        self.assertIsNotNone(job.offer_id)
        response = self.client.get(f"/api/v1/offers/{job.offer_id}/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["recruiter_job_id"], job.pk)
        duplicate = self.send(f"recruiter/jobs/{job.pk}/duplicate/")
        self.assertEqual(duplicate.status_code, 201, duplicate.content)
        self.assertEqual(duplicate.json()["status"], "draft")
        self.assertIsNone(duplicate.json()["offer_id"])
        self.assertEqual(
            self.send(
                f"recruiter/jobs/{job.pk}/", {"status": "paused"}, "patch"
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(f"/api/v1/offers/{job.offer_id}/").status_code, 404
        )

    def test_dashboard_values_are_actual_data(self):
        self.create_job()
        counts = self.client.get("/api/v1/recruiter/dashboard/").json()["counts"]
        self.assertEqual(
            counts,
            {"active_jobs": 0, "applications": 0, "average_match": None, "views": 0},
        )

    def test_integration_is_pending_and_never_fetches_user_url(self):
        with patch("httpx.get") as fetch:
            response = self.send(
                "recruiter/integrations/",
                {"provider": "lever", "url": "https://jobs.lever.co/example"},
            )
        self.assertEqual(response.status_code, 200, response.content)
        fetch.assert_not_called()
        self.assertEqual(response.json()["results"][0]["status"], "pending")
        self.assertEqual(
            self.send(
                "recruiter/integrations/",
                {"provider": "lever", "url": "http://localhost"},
            ).status_code,
            400,
        )
        self.client.force_login(self.other_user)
        self.assertEqual(
            self.client.get("/api/v1/recruiter/integrations/").json()["results"], []
        )

    def test_direct_application_snapshot_resume_access_and_withdrawal(self):
        self.verified()
        job = self.create_job(active=True)
        candidate = get_user_model().objects.create_user(
            username="student", email="student@example.test"
        )
        profile = m.CandidateProfile.objects.create(
            user=candidate, full_name="Student", headline="Python"
        )
        self.client.force_login(candidate)
        self.assertEqual(self.send(f"recruiter/jobs/{job.pk}/apply/").status_code, 409)
        with (
            TemporaryDirectory() as directory,
            override_settings(
                PRIVATE_STORAGE_ROOT=directory, PRIVATE_STORAGE_BACKEND="local"
            ),
        ):
            token = self.client.get("/api/v1/auth/csrf/").json()["csrf_token"]
            response = self.client.post(
                "/api/v1/documents/",
                {
                    "kind": "resume",
                    "file": SimpleUploadedFile(
                        "cv.pdf", pdf_bytes(), content_type="application/pdf"
                    ),
                },
                HTTP_X_CSRFTOKEN=token,
            )
            self.assertEqual(response.status_code, 200, response.content)
            profile.current_resume_id = response.json()["id"]
            profile.save()
            response = self.send(f"recruiter/jobs/{job.pk}/apply/")
            self.assertEqual(response.status_code, 201, response.content)
            self.assertEqual(
                self.send(f"recruiter/jobs/{job.pk}/apply/").json(), response.json()
            )
            applicant = m.RecruiterApplicant.objects.get(job=job)
            profile.full_name = "Private edit"
            profile.save()
            self.client.force_login(self.other_user)
            self.assertEqual(
                self.client.get(
                    f"/api/v1/recruiter/candidates/{applicant.pk}/"
                ).status_code,
                404,
            )
            self.assertEqual(
                self.client.get(
                    f"/api/v1/recruiter/candidates/{applicant.pk}/resume/"
                ).status_code,
                404,
            )
            self.client.force_login(self.user)
            detail = self.client.get(
                f"/api/v1/recruiter/candidates/{applicant.pk}/"
            ).json()
            self.assertEqual(detail["profile"]["full_name"], "Student")
            self.assertIsNone(detail["match_score"])
            response = self.client.get(detail["resume_url"])
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                hashlib.sha256(b"".join(response.streaming_content)).hexdigest(),
                applicant.resume.sha256,
            )
            self.assertEqual(
                self.send(
                    f"recruiter/candidates/{applicant.pk}/",
                    {"stage": "rejected"},
                    "patch",
                ).status_code,
                400,
            )
            self.assertEqual(
                self.send(
                    f"recruiter/candidates/{applicant.pk}/",
                    {"stage": "interview", "interview_at": "2026-12-01T10:00:00Z"},
                    "patch",
                ).status_code,
                200,
            )
            m.Application.objects.filter(pk=applicant.application_id).update(
                status="withdrawn"
            )
            self.assertEqual(self.client.get(detail["resume_url"]).status_code, 404)
            self.assertEqual(
                self.client.get("/api/v1/recruiter/candidates/").json()["count"], 0
            )

    def test_inactive_candidate_is_removed_from_dashboard_and_documents(self):
        self.verified()
        job = self.create_job(active=True)
        candidate = get_user_model().objects.create_user(
            username="inactive", is_active=False
        )
        source = m.OfferSource.objects.get(offer_id=job.offer_id)
        application = m.Application.objects.create(
            user=candidate, offer_id=job.offer_id, source=source, status="submitted"
        )
        applicant = m.RecruiterApplicant.objects.create(
            job=job, application=application, profile_snapshot={"full_name": "Private"}
        )
        dashboard = self.client.get("/api/v1/recruiter/dashboard/").json()
        self.assertEqual(dashboard["counts"]["applications"], 0)
        self.assertEqual(dashboard["activity"], [])
        self.assertEqual(
            self.client.get(
                f"/api/v1/recruiter/candidates/{applicant.pk}/"
            ).status_code,
            404,
        )

    def test_professional_email_rules_are_shared_by_availability_and_registration(self):
        # Changing only the server policy must affect both registration steps.
        with patch(
            "jobboard.services.recruiters.PERSONAL_DOMAINS", {"personal.example"}
        ):
            email = " Person@PERSONAL.EXAMPLE "
            early = self.send(
                "auth/email-availability/", {"email": email, "role": "recruiter"}
            )
            final = self.send(
                "auth/register/",
                {
                    "email": email,
                    "role": "recruiter",
                    "full_name": "Person",
                    "password": "Long-secret-password-239!",
                },
            )
            for response in (early, final):
                self.assertEqual(response.status_code, 400, response.content)
                self.assertEqual(
                    response.json()["error"]["code"], "professional_email_required"
                )
                self.assertEqual(
                    response.json()["error"]["details"]["email"][0]["code"],
                    "professional_email_required",
                )
            candidate = self.send(
                "auth/email-availability/", {"email": email, "role": "candidate"}
            )
            self.assertEqual(candidate.status_code, 200, candidate.content)
            self.assertEqual(candidate.json(), {"available": True})
            self.assertEqual(
                self.send("auth/email-availability/", {"email": email}).status_code, 200
            )
            self.assertEqual(
                self.send(
                    "auth/email-availability/", {"email": email, "role": "admin"}
                ).status_code,
                400,
            )

    def test_shared_company_preserves_separate_workspaces(self):
        from django.contrib import admin

        self.verified()
        company = m.Company.objects.create(name="Shared Company", domain="company.test")
        for owner in (self.owner, self.other):
            owner.company = company
            owner.company_name = company.name
            owner.verification_status = "verified"
            owner.email_verified = True
            owner.website_url = "https://company.test"
            owner.save()
        self.assertEqual(company.recruiter_profiles.count(), 2)
        profile_admin = admin.site._registry[m.RecruiterProfile]
        self.assertNotIn("company", profile_admin.get_readonly_fields(None, self.owner))
        first = self.create_job(active=True)
        self.assertEqual(first.offer.company_id, company.pk)
        self.assertIn("company", profile_admin.get_readonly_fields(None, self.owner))
        self.client.force_login(self.other_user)
        self.assertEqual(self.client.get("/api/v1/recruiter/jobs/").json()["count"], 0)
        self.assertEqual(
            self.client.get(f"/api/v1/recruiter/jobs/{first.pk}/").status_code, 404
        )
        second = self.create_job(active=True)
        self.assertEqual(second.offer.company_id, company.pk)
        self.assertEqual(m.Company.objects.count(), 1)
        self.assertEqual(
            [
                job["id"]
                for job in self.client.get("/api/v1/recruiter/jobs/").json()["results"]
            ],
            [second.pk],
        )

    def test_revocation_removes_recent_and_old_direct_offers_immediately(self):
        from jobboard.api.catalogue import open_offers
        from jobboard.services.engine_filters import fresh_sources
        from jobboard.services.engine_quality import published_offers

        self.verified()
        job = self.create_job(active=True)
        source = m.OfferSource.objects.get(offer_id=job.offer_id)
        public = Client()
        for age in (timedelta(minutes=1), timedelta(days=7)):
            m.OfferSource.objects.filter(pk=source.pk).update(
                last_checked_at=timezone.now() - age
            )
            for field, value in (
                ("email_verified", False),
                ("verification_status", "pending"),
                ("is_active", False),
                ("status", "paused"),
            ):
                with self.subTest(age=age, field=field):
                    m.RecruiterProfile.objects.filter(pk=self.owner.pk).update(
                        email_verified=True, verification_status="verified"
                    )
                    get_user_model().objects.filter(pk=self.user.pk).update(
                        is_active=True
                    )
                    m.RecruiterJob.objects.filter(pk=job.pk).update(status="active")
                    self.assertTrue(fresh_sources().filter(pk=source.pk).exists())
                    self.assertTrue(open_offers().filter(pk=job.offer_id).exists())
                    if field == "is_active":
                        get_user_model().objects.filter(pk=self.user.pk).update(
                            is_active=value
                        )
                    elif field == "status":
                        m.RecruiterJob.objects.filter(pk=job.pk).update(status=value)
                    else:
                        m.RecruiterProfile.objects.filter(pk=self.owner.pk).update(
                            **{field: value}
                        )
                    self.assertFalse(fresh_sources().filter(pk=source.pk).exists())
                    self.assertFalse(
                        published_offers(m.Offer.objects.all())
                        .filter(pk=job.offer_id)
                        .exists()
                    )
                    self.assertFalse(open_offers().filter(pk=job.offer_id).exists())
                    self.assertEqual(
                        public.get(f"/api/v1/offers/{job.offer_id}/").status_code, 404
                    )
                    listing = public.get("/api/v1/offers/")
                    self.assertEqual(listing.status_code, 200, listing.content)
                    self.assertNotIn(
                        job.offer_id,
                        [offer["id"] for offer in listing.json()["results"]],
                    )
