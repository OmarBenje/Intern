import re
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import include, path

from jobboard.models import CandidateProfile

urlpatterns = [path("api/v1/", include("jobboard.api.auth"))]
PASSWORD = "Valid-Original-Password-2026!"
NEW_PASSWORD = "A-Different-Long-Password-2027!"


@override_settings(
    ROOT_URLCONF=__name__,
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    MAILERS={"default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}},
    PUBLIC_BASE_URL="https://intern.example",
    AUTH_RATE_LIMIT=10,
)
class AuthAPITests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.user = get_user_model().objects.create_user(
            username="alice", email="alice@example.com", password=PASSWORD
        )

    def csrf(self, client=None):
        client = client or self.client
        response = client.get("/api/v1/auth/csrf/")
        self.assertEqual(response.status_code, 200)
        return response.json()["csrf_token"]

    def post(self, route, data, client=None, **extra):
        client = client or self.client
        return client.post(
            "/api/v1/auth/" + route + "/",
            data,
            content_type="application/json",
            HTTP_X_CSRFTOKEN=self.csrf(client),
            **extra,
        )

    def test_register_and_login_require_real_csrf(self):
        registration = {
            "username": "newuser",
            "email": "new@example.com",
            "password": PASSWORD,
            "full_name": "New User",
        }
        for route, data in [
            ("register", registration),
            ("login", {"username": "alice", "password": PASSWORD}),
        ]:
            response = self.client.post(
                "/api/v1/auth/" + route + "/", data, content_type="application/json"
            )
            self.assertEqual(response.status_code, 403, response.content)
        self.assertFalse(get_user_model().objects.filter(username="newuser").exists())
        response = self.post("register", registration)
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["status"], "pending")
        user = get_user_model().objects.get(username="newuser")
        self.assertFalse(user.is_active)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertEqual(CandidateProfile.objects.get(user=user).full_name, "New User")
        self.assertEqual(self.client.get("/api/v1/auth/me/").status_code, 401)

    def test_email_onboarding_creates_profile_and_allows_email_login(self):
        data = {
            "email": "New.Person@example.com",
            "full_name": "New Person",
            "password": PASSWORD,
        }
        response = self.post("register", data)
        self.assertEqual(response.status_code, 201, response.content)
        user = get_user_model().objects.get(email="new.person@example.com")
        self.assertFalse(user.is_active)
        self.assertTrue(user.username.startswith("candidate_"))
        self.assertEqual(user.email, "new.person@example.com")
        self.assertEqual(
            CandidateProfile.objects.get(user=user).full_name, "New Person"
        )
        response = self.post(
            "login", {"username": "NEW.PERSON@example.com", "password": PASSWORD}
        )
        self.assertEqual(response.status_code, 403, response.content)
        self.assertEqual(response.json()["error"]["code"], "account_inactive")
        user.is_active = True
        user.save(update_fields=["is_active"])
        response = self.post(
            "login", {"username": "NEW.PERSON@example.com", "password": PASSWORD}
        )
        self.assertEqual(response.status_code, 200, response.content)
        response = self.post("register", data)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["error"]["details"]["email"][0]["code"], "unavailable"
        )

    def test_email_availability_requires_csrf_and_normalizes_email(self):
        response = self.client.post(
            "/api/v1/auth/email-availability/",
            {"email": self.user.email},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            self.post("email-availability", {"email": " ALICE@EXAMPLE.COM "}).json(),
            {"available": False},
        )
        self.assertEqual(
            self.post("email-availability", {"email": "new@example.com"}).json(),
            {"available": True},
        )
        self.assertEqual(
            self.post("email-availability", {"email": "bad"}).status_code, 400
        )
        self.assertEqual(get_user_model().objects.count(), 1)
        self.assertEqual(self.client.get("/api/v1/auth/me/").status_code, 401)

    @override_settings(AUTH_RATE_LIMIT=1)
    def test_email_availability_is_rate_limited(self):
        self.assertEqual(
            self.post("email-availability", {"email": "alice@example.com"}).status_code,
            200,
        )
        self.assertEqual(
            self.post("email-availability", {"email": "ALICE@example.com"}).status_code,
            429,
        )

    def test_ambiguous_legacy_email_cannot_select_another_account(self):
        get_user_model().objects.create_user(
            username="other", email="alice@example.com", password=PASSWORD
        )
        response = self.post(
            "login", {"username": "alice@example.com", "password": PASSWORD}
        )
        self.assertEqual(response.status_code, 401)

    def test_registration_rejects_weak_password_and_privilege_fields(self):
        data = {
            "username": "newuser",
            "email": "new@example.com",
            "password": "password",
            "full_name": "New User",
        }
        self.assertEqual(self.post("register", data).status_code, 400)
        data["password"] = PASSWORD
        for field in ("is_staff", "is_superuser", "groups", "user_permissions"):
            response = self.post("register", {**data, field: True})
            self.assertEqual(response.status_code, 400, response.content)
            self.assertEqual(response.json()["error"]["code"], "invalid_fields")
        self.assertFalse(get_user_model().objects.filter(username="newuser").exists())

    def test_login_rotates_session_logout_removes_access(self):
        self.assertEqual(self.client.get("/api/v1/auth/me/").status_code, 401)
        session = self.client.session
        session["pre_login"] = True
        session.save()
        old_key = session.session_key
        self.assertEqual(
            self.post(
                "login", {"username": "alice", "password": "wrong-password"}
            ).status_code,
            401,
        )
        response = self.post("login", {"username": "alice", "password": PASSWORD})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertNotEqual(self.client.session.session_key, old_key)
        self.assertEqual(self.client.get("/api/v1/auth/me/").status_code, 200)
        self.assertEqual(self.post("logout", {}).status_code, 200)
        self.assertEqual(self.client.get("/api/v1/auth/me/").status_code, 401)

    def test_password_change_checks_old_password_and_invalidates_other_sessions(self):
        other = Client(enforce_csrf_checks=True)
        for client in (self.client, other):
            self.assertEqual(
                self.post(
                    "login", {"username": "alice", "password": PASSWORD}, client=client
                ).status_code,
                200,
            )
        self.assertEqual(
            self.post(
                "password",
                {"old_password": "wrong-password", "new_password": NEW_PASSWORD},
            ).status_code,
            400,
        )
        self.assertEqual(
            self.post(
                "password", {"old_password": PASSWORD, "new_password": "password"}
            ).status_code,
            400,
        )
        response = self.post(
            "password", {"old_password": PASSWORD, "new_password": NEW_PASSWORD}
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.client.get("/api/v1/auth/me/").status_code, 200)
        self.assertEqual(other.get("/api/v1/auth/me/").status_code, 401)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW_PASSWORD))

    def test_password_reset_has_uniform_response_and_single_use_token(self):
        unknown = self.post("password-reset", {"email": "unknown@example.com"})
        self.assertEqual(unknown.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)
        response = self.post(
            "password-reset", {"email": self.user.email}, HTTP_HOST="testserver"
        )
        self.assertEqual(response.json(), unknown.json())
        self.assertEqual(len(mail.outbox), 1)
        reset_url = re.search(r"https://\S+", mail.outbox[0].body).group(0)
        parsed = urlsplit(reset_url)
        self.assertEqual(parsed.netloc, "intern.example")
        params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        self.assertEqual(
            self.post(
                "password-reset-confirm", {**params, "new_password": "password"}
            ).status_code,
            400,
        )
        payload = {**params, "new_password": NEW_PASSWORD}
        self.assertEqual(self.post("password-reset-confirm", payload).status_code, 200)
        self.assertEqual(self.post("password-reset-confirm", payload).status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW_PASSWORD))

    @override_settings(AUTH_RATE_LIMIT=2)
    def test_login_throttle_shared_across_clients_ips_and_case(self):
        for username, ip in [("alice", "192.0.2.1"), ("ALICE", "192.0.2.2")]:
            client = Client(enforce_csrf_checks=True)
            response = self.post(
                "login",
                {"username": username, "password": "wrong-password"},
                client=client,
                REMOTE_ADDR=ip,
            )
            self.assertEqual(response.status_code, 401)
        third = Client(enforce_csrf_checks=True)
        response = self.post(
            "login",
            {"username": "alice", "password": PASSWORD},
            client=third,
            REMOTE_ADDR="192.0.2.3",
        )
        self.assertEqual(response.status_code, 429, response.content)
        self.assertEqual(third.get("/api/v1/auth/me/").status_code, 401)

    def test_inactive_user_cannot_login(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        response = self.post("login", {"username": "alice", "password": PASSWORD})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "account_inactive")
