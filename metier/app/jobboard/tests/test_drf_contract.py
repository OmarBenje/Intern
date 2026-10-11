"""Regression cases for differences between Django and DRF defaults."""

from datetime import UTC, datetime
from decimal import Decimal
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import URLResolver, get_resolver
from rest_framework.test import APIClient
from rest_framework.views import APIView

from jobboard.api import read_serializers as read
from jobboard.api import serializers as inputs
from jobboard.api.core import APIError
from jobboard.api.drf import ContractJSONRenderer
from jobboard.models import CandidateProfile, Company, Document, Offer, SearchPreference
from jobboard.services.profiles import preference_data, profile_data
from jobboard.tests.engine_fixtures import publishable
from jobboard.tests.test_documents_api import pdf_bytes


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class DRFContractTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="drf", password="example-password"
        )
        self.client = APIClient()
        self.client.force_login(self.user)

    def test_every_v1_route_uses_drf(self):
        callbacks = []

        def walk(patterns, prefix=""):
            for pattern in patterns:
                route = prefix + str(pattern.pattern)
                if isinstance(pattern, URLResolver):
                    walk(pattern.url_patterns, route)
                elif route.startswith("api/v1/"):
                    callbacks.append(pattern.callback)

        walk(get_resolver().url_patterns)
        self.assertGreater(len(callbacks), 30)
        for callback in callbacks:
            self.assertTrue(issubclass(callback.cls, APIView))

    def test_anonymous_csrf_and_origin_are_enforced(self):
        client = APIClient(enforce_csrf_checks=True)
        for route in ("register", "login", "password-reset", "password-reset-confirm"):
            response = client.post(f"/api/v1/auth/{route}/", {}, format="json")
            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.json()["error"]["code"], "csrf_failed")
            self.assertEqual(response["Cache-Control"], "no-store")
        token = client.get("/api/v1/auth/csrf/").json()["csrf_token"]
        response = client.post(
            "/api/v1/auth/login/",
            {"username": "drf", "password": "example-password"},
            format="json",
            HTTP_X_CSRFTOKEN=token,
            HTTP_ORIGIN="https://untrusted.example",
        )
        self.assertEqual(response.status_code, 403)
        client.force_login(self.user)
        self.assertEqual(
            client.patch("/api/v1/profile/", {}, format="json").status_code, 403
        )

    def test_anonymous_private_access_has_401_challenge(self):
        self.client.logout()
        self.assertEqual(self.client.get("/api/v1/offers/").status_code, 200)
        for route in (
            "auth/me/",
            "saved-offers/",
            "profile/",
            "documents/",
            "applications/",
            "account/export/",
        ):
            response = self.client.get("/api/v1/" + route)
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response["WWW-Authenticate"], "Session")
            self.assertEqual(
                response.json()["error"]["code"], "authentication_required"
            )
            self.assertEqual(response["Cache-Control"], "no-store")

    def test_json_parsing_and_mass_assignment(self):
        for raw in (
            b"",
            b"{",
            b"null",
            b"[]",
            b'{"full_name":NaN}',
            b'{"full_name":"\xff"}',
        ):
            response = self.client.generic(
                "PATCH", "/api/v1/profile/", raw, content_type="application/json"
            )
            self.assertEqual(response.status_code, 400, response.content)
            self.assertEqual(response.json()["error"]["code"], "invalid_json")
        response = self.client.patch(
            "/api/v1/profile/",
            {"user_id": self.user.pk, "profile_version": 99},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["error"]["details"]["unknown"],
            ["profile_version", "user_id"],
        )
        response = self.client.generic(
            "PATCH", "/api/v1/profile/", b"{}", content_type="text/plain"
        )
        self.assertEqual(response.status_code, 415)
        self.assertFalse(CandidateProfile.objects.exists())

    def test_serializers_do_not_coerce_untrusted_types(self):
        for cls, payload in (
            (inputs.LoginSerializer, {"username": 42, "password": "secret"}),
            (inputs.ProfileSerializer, {"full_name": 42}),
            (inputs.PreferenceSerializer, {"willing_to_relocate": "false"}),
            (inputs.CreateApplicationSerializer, {"offer_id": True, "source_id": 1}),
            (inputs.CreateApplicationSerializer, {"offer_id": "01", "source_id": 1}),
            (inputs.ResumeSerializer, {"document_id": True}),
        ):
            with (
                self.subTest(serializer=cls.__name__, payload=payload),
                self.assertRaises(APIError),
            ):
                cls(data=payload).is_valid(raise_exception=True)
        serializer = inputs.LoginSerializer(
            data={"username": "drf", "password": " with spaces "}
        )
        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data["password"], " with spaces ")
        self.assertNotIn("password", serializer.data)

    def test_strict_pagination(self):
        response = self.client.get("/api/v1/offers/")
        self.assertEqual(
            response.json(), {"count": 0, "page": 1, "page_size": 20, "results": []}
        )
        for query in (
            "page_size=101",
            "page_size=0",
            "page=01",
            "page=last",
            "page=-1",
        ):
            response = self.client.get("/api/v1/offers/?" + query)
            self.assertEqual(response.status_code, 400, query)
        self.assertEqual(self.client.get("/api/v1/offers/?page=2").status_code, 404)
        company = Company.objects.create(name="DRF")
        Offer.objects.bulk_create(
            [Offer(company=company, title=str(i)) for i in range(3)]
        )
        for offer in Offer.objects.all():
            publishable(offer)
        first = self.client.get("/api/v1/offers/?page_size=2").json()
        second = self.client.get("/api/v1/offers/?page_size=2&page=2").json()
        self.assertEqual(first["count"], 3)
        self.assertEqual(len(first["results"]), 2)
        self.assertEqual(len(second["results"]), 1)
        self.assertFalse(
            {row["id"] for row in first["results"]}
            & {row["id"] for row in second["results"]}
        )

    def test_negotiation_options_methods_and_cache(self):
        for method, kwargs, expected in (
            ("get", {"HTTP_ACCEPT": "text/html"}, 406),
            ("post", {"data": {}, "format": "json"}, 405),
            ("options", {}, 200),
        ):
            response = getattr(self.client, method)("/api/v1/offers/", **kwargs)
            self.assertEqual(response.status_code, expected)
            self.assertEqual(response["Cache-Control"], "no-store")
            if expected == 405:
                self.assertIn("GET", response["Allow"])
                self.assertEqual(response.json()["error"]["code"], "method_not_allowed")
        with override_settings(DEBUG=False):
            response = self.client.get("/api/v1/does-not-exist/")
            self.assertEqual(response.status_code, 404)
            self.assertEqual(response["Cache-Control"], "no-store")

    def test_response_serializers_preserve_types_and_private_field_allowlists(self):
        profile = CandidateProfile.objects.create(user=self.user, full_name="DRF")
        preference = SearchPreference(
            profile=profile,
            minimum_salary=Decimal(10),
            salary_currency="EUR",
            salary_period="year",
        )
        renderer = ContractJSONRenderer()
        self.assertEqual(
            renderer.render(read.ProfileSerializer(profile).data),
            renderer.render(profile_data(profile)),
        )
        preference.save()
        self.assertEqual(
            renderer.render(read.PreferenceSerializer(preference).data),
            renderer.render(preference_data(preference)),
        )
        rendered = renderer.render(
            {
                "at": datetime(2026, 1, 1, 0, 0, 0, 123456, tzinfo=UTC),
                "amount": Decimal("10.00"),
            }
        )
        self.assertEqual(
            rendered, b'{"at":"2026-01-01T00:00:00.123Z","amount":"10.00"}'
        )
        fields = read.DocumentSerializer(Document(owner=self.user)).data
        self.assertEqual(
            set(fields),
            {
                "id",
                "kind",
                "original_name",
                "mime_type",
                "byte_size",
                "sha256",
                "status",
                "created_at",
            },
        )
        self.assertNotIn("lease_token", read.RunSerializer().fields)
        self.assertNotIn("raw_payload", read.SourceSerializer().fields)

    def test_multipart_duplicate_and_unknown_fields_are_rejected(self):
        for payload in (
            {
                "kind": ["resume", "resume"],
                "file": SimpleUploadedFile("cv.pdf", b"pdf"),
            },
            {
                "kind": "resume",
                "file": [
                    SimpleUploadedFile("a.pdf", b"a"),
                    SimpleUploadedFile("b.pdf", b"b"),
                ],
            },
            {
                "kind": "resume",
                "file": SimpleUploadedFile("a.pdf", b"a"),
                "owner_id": str(self.user.pk),
            },
        ):
            response = self.client.post(
                "/api/v1/documents/", payload, format="multipart"
            )
            self.assertEqual(response.status_code, 400, response.content)
            self.assertEqual(response.json()["error"]["code"], "invalid_upload")
        self.assertFalse(Document.objects.exists())

    def test_downloads_accept_their_binary_media_type(self):
        with (
            TemporaryDirectory() as directory,
            override_settings(
                PRIVATE_STORAGE_BACKEND="local", PRIVATE_STORAGE_ROOT=directory
            ),
        ):
            pdf = pdf_bytes()
            response = self.client.post(
                "/api/v1/documents/",
                {
                    "kind": "resume",
                    "file": SimpleUploadedFile(
                        "cv.pdf", pdf, content_type="application/pdf"
                    ),
                },
                format="multipart",
            )
            self.assertEqual(response.status_code, 200, response.content)
            pk = response.json()["id"]
            response = self.client.get(
                f"/api/v1/documents/{pk}/download/", HTTP_ACCEPT="application/pdf"
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response["Content-Type"], "application/pdf")
            self.assertEqual(b"".join(response.streaming_content), pdf)
            response = self.client.get(
                "/api/v1/account/export/", HTTP_ACCEPT="application/zip"
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response["Content-Type"], "application/zip")
            self.assertTrue(b"".join(response.streaming_content).startswith(b"PK"))
            self.client.logout()
            response = self.client.get(
                f"/api/v1/documents/{pk}/download/", HTTP_ACCEPT="application/pdf"
            )
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response["Content-Type"], "application/json")
