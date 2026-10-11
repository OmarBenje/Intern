import json
import socket
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from jobboard.integrations.greenhouse_catalogue import CatalogueImportError
from jobboard.integrations.public_html import (
    MAX_BYTES,
    PinnedHTTPSConnection,
    fetch_html,
    parse_job_postings,
    resolve_public,
)
from jobboard.models import SourceBoard, SourceCandidate, SourceDiscoverySeed
from jobboard.services.engine_discovery import run_discovery


def addr(ip):
    return (socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443))


class PublicFetchTests(SimpleTestCase):
    def test_private_and_mixed_dns_rejected(self):
        for rows in ([addr("127.0.0.1")], [addr("1.1.1.1"), addr("10.0.0.1")]):
            with (
                patch("socket.getaddrinfo", return_value=rows),
                self.assertRaises(CatalogueImportError),
            ):
                resolve_public("example.com")

    def test_connection_uses_pinned_sockaddr_and_original_tls_host(self):
        connection = PinnedHTTPSConnection("example.com", addr("1.1.1.1"), 3)
        connection._context = MagicMock()
        with patch("socket.socket") as sock, patch("socket.getaddrinfo") as dns:
            connection.connect()
        dns.assert_not_called()
        sock.return_value.connect.assert_called_once_with(("1.1.1.1", 443))
        self.assertEqual(
            connection._context.wrap_socket.call_args.kwargs["server_hostname"],
            "example.com",
        )

    def test_redirect_to_private_host_rejected(self):
        response = MagicMock(status=302)
        response.getheader.return_value = "https://127.0.0.1/private"
        with (
            patch("socket.getaddrinfo", return_value=[addr("1.1.1.1")]),
            patch("jobboard.integrations.public_html.PinnedHTTPSConnection") as conn,
        ):
            conn.return_value.getresponse.return_value = response
            with self.assertRaises(CatalogueImportError):
                fetch_html("https://example.com", {"example.com"})
            self.assertEqual(conn.call_count, 1)

    def test_oversize_response_rejected(self):
        response = MagicMock(status=200)
        response.getheader.side_effect = lambda name, default=None: {
            "Content-Type": "text/html",
            "Content-Encoding": "identity",
        }.get(name, default)
        response.read1.return_value = b"x" * (MAX_BYTES + 1)
        with (
            patch("socket.getaddrinfo", return_value=[addr("1.1.1.1")]),
            patch("jobboard.integrations.public_html.PinnedHTTPSConnection") as conn,
        ):
            conn.return_value.getresponse.return_value = response
            with self.assertRaises(CatalogueImportError):
                fetch_html("https://example.com", {"example.com"})

    def test_jsonld_truncation_cannot_select_one_of_multiple_jobs(self):
        data = [{"@type": "JobPosting", "title": "Hidden second role"}]
        data.extend({"@type": "Thing"} for _ in range(1000))
        data.append({"@type": "JobPosting", "title": "First visible role"})
        with self.assertRaisesMessage(
            CatalogueImportError, "job_posting_graph_too_large"
        ):
            parse_job_postings(
                '<script type="application/ld+json">' + json.dumps(data) + "</script>"
            )

    def test_absolute_deadline_interrupts_slow_headers(self):
        import http.client

        with (
            patch("socket.getaddrinfo", return_value=[addr("1.1.1.1")]),
            patch("jobboard.integrations.public_html.PinnedHTTPSConnection") as conn,
            patch("jobboard.integrations.public_html.threading.Timer") as timer,
        ):

            def slow_headers():
                # Simulate watchdog firing while getresponse is still reading.
                timer.call_args.args[1]()
                raise http.client.RemoteDisconnected()

            conn.return_value.getresponse.side_effect = slow_headers
            with self.assertRaisesMessage(
                CatalogueImportError, "fetch_budget_exceeded"
            ):
                fetch_html("https://example.com", {"example.com"})
            conn.return_value.sock.shutdown.assert_called_once_with(socket.SHUT_RDWR)
            timer.return_value.cancel.assert_called_once()
            conn.return_value.close.assert_called_once()

    def test_jsonld_plain_text_and_graph(self):
        data = {
            "@graph": [
                {
                    "@type": "JobPosting",
                    "title": "<b>Stage</b>",
                    "description": "<p>Bonjour &amp; bienvenue</p><script>bad()</script>",
                    "hiringOrganization": {"name": "ACME"},
                }
            ]
        }
        rows = parse_job_postings(
            '<script type="application/ld+json">'
            + json.dumps(data).replace("</script>", "<\\/script>")
            + "</script>"
        )
        self.assertEqual(
            rows,
            [
                {
                    "title": "Stage",
                    "description": "Bonjour & bienvenue",
                    "company_name": "ACME",
                }
            ],
        )


class DiscoveryTests(TestCase):
    def setUp(self):
        self.seed = SourceDiscoverySeed.objects.create(
            url="https://example.com", allowed_host="example.com", company_name="ACME"
        )

    @patch("jobboard.services.engine_discovery.fetch_html")
    def test_daily_discovery_deduplicates_without_activation(self, fetch):
        fetch.return_value = (
            self.seed.url,
            '<a href="https://jobs.ashbyhq.com/acme/123">Stage</a>',
        )
        self.assertEqual(run_discovery(), 1)
        self.assertEqual(run_discovery(), 0)
        SourceDiscoverySeed.objects.update(next_run_at=timezone.now())
        run_discovery()
        self.assertEqual(SourceCandidate.objects.count(), 1)
        self.assertEqual(SourceBoard.objects.count(), 0)
        self.assertEqual(SourceCandidate.objects.get().status, "candidate")

    @patch("jobboard.services.engine_discovery.fetch_html")
    def test_failure_retains_candidate(self, fetch):
        SourceCandidate.objects.create(
            url="https://jobs.ashbyhq.com/acme",
            provider="ashby",
            board_key="acme",
            company_name="ACME",
        )
        fetch.side_effect = CatalogueImportError("public_http_error")
        run_discovery()
        self.seed.refresh_from_db()
        self.assertEqual(self.seed.failure_count, 1)
        self.assertEqual(SourceCandidate.objects.count(), 1)

    @patch("jobboard.services.engine_discovery.fetch_html")
    def test_three_page_limit(self, fetch):
        fetch.return_value = (
            self.seed.url,
            "".join(f'<a href="/careers/{i}">jobs</a>' for i in range(10)),
        )
        run_discovery()
        self.assertEqual(fetch.call_count, 3)


class PrivateHTMLImportTests(TestCase):
    def test_approved_host_extracts_private_job_and_unapproved_never_fetches(self):
        from django.contrib.auth import get_user_model

        from jobboard.models import ExternalOpportunity
        from jobboard.services.engine_external import process_external_opportunities

        user = get_user_model().objects.create_user(
            username="html-reader", password="test-pass"
        )
        SourceDiscoverySeed.objects.create(
            url="https://example.com", allowed_host="example.com", company_name="ACME"
        )
        approved = ExternalOpportunity.objects.create(
            user=user, url="https://example.com/job/1"
        )
        unapproved = ExternalOpportunity.objects.create(
            user=user, url="https://unapproved.example/job/1"
        )
        with patch(
            "jobboard.services.engine_external.fetch_html",
            return_value=(
                approved.url,
                '<script type="application/ld+json">{"@type":"JobPosting","title":"Stage finance","description":"<p>Paris</p>"}</script>',
            ),
        ) as fetch:
            self.assertEqual(process_external_opportunities(), 2)
        self.assertEqual(fetch.call_count, 1)
        approved.refresh_from_db()
        unapproved.refresh_from_db()
        self.assertEqual(
            (approved.status, approved.title, approved.description),
            ("ready", "Stage finance", "Paris"),
        )
        self.assertEqual(unapproved.status, "failed")
        self.assertIsNone(approved.offer_id)
