from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase, override_settings

from jobboard.api.auth import rate


class LoginRateLimitTests(SimpleTestCase):
    def setUp(self):
        self.request = RequestFactory().post("/", REMOTE_ADDR="192.0.2.1")

    @override_settings(AUTH_LOGIN_RATE_LIMIT_ENABLED=True)
    @patch("jobboard.api.auth.throttle")
    def test_normal_login_checks_ip_and_identity(self, throttle):
        rate(self.request, "login", "Alice")
        self.assertEqual(throttle.call_count, 2)
        throttle.assert_any_call("login:ip", "192.0.2.1", limit=30)
        throttle.assert_any_call("login:identity", "alice")

    @override_settings(AUTH_LOGIN_RATE_LIMIT_ENABLED=False)
    @patch("jobboard.api.auth.throttle")
    def test_measurement_logins_do_not_consume_either_counter(self, throttle):
        for _ in range(36):
            rate(self.request, "login", "Alice")
        throttle.assert_not_called()

    @override_settings(AUTH_LOGIN_RATE_LIMIT_ENABLED=False)
    @patch("jobboard.api.auth.throttle")
    def test_other_authentication_actions_keep_their_protection(self, throttle):
        rate(self.request, "password-reset", "Alice")
        self.assertEqual(throttle.call_count, 2)

    @patch("jobboard.api.auth.throttle")
    def test_protection_resumes_after_measurement_override(self, throttle):
        with override_settings(AUTH_LOGIN_RATE_LIMIT_ENABLED=False):
            rate(self.request, "login", "Alice")
        with override_settings(AUTH_LOGIN_RATE_LIMIT_ENABLED=True):
            rate(self.request, "login", "Alice")
        self.assertEqual(throttle.call_count, 2)
