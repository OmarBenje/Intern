import io
import json
import socket
import tempfile
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from PIL import Image

from jobboard.api.read_serializers import CompanySerializer
from jobboard.integrations.greenhouse_catalogue import CatalogueImportError
from jobboard.integrations.public_html import fetch_public
from jobboard.models import Company
from jobboard.services.company_logos import (
    REJECTED_LOGO_DIGESTS,
    LogoParser,
    cache_logo,
    employer_domain,
    extract_logo,
    normalize_logo,
)


def png():
    output = io.BytesIO()
    Image.new("RGB", (64, 32), "red").save(output, format="PNG")
    return output.getvalue()


class LogoExtractionTests(SimpleTestCase):
    def test_employer_image_on_linkedin_is_distinct_from_platform_icon(self):
        parser = LogoParser("https://www.linkedin.com/jobs/view/123", "Example")
        parser.feed(
            '<link rel="icon" href="/favicon.png"><img class="artdeco-entity-image" alt="Example" src="data:image/gif;base64,placeholder" data-delayed-url="https://media.licdn.com/company-logo.png">'
        )
        self.assertEqual(parser.urls(), ["https://media.licdn.com/company-logo.png"])

    def test_platform_favicons_and_social_images_are_excluded(self):
        for host in (
            "www.linkedin.com",
            "fr.linkedin.com",
            "www.welcometothejungle.com",
            "example.recruitee.com",
            "ag.wd3.myworkdayjobs.com",
            "www.indeed.com",
            "jobs.personio.de",
        ):
            with self.subTest(host=host):
                parser = LogoParser(f"https://{host}/example", "Example")
                parser.feed(
                    '<link rel="icon" href="/favicon.png"><link rel="apple-touch-icon" href="/apple.png"><img alt="LinkedIn logo" src="/linkedin.png"><img alt="logo" src="/platform.png">'
                )
                self.assertEqual(parser.urls(), [])

    def test_structured_employer_logo_and_homepage(self):
        parser = LogoParser("https://www.welcometothejungle.com/fr/jobs/123", "Example")
        parser.feed(
            '<script type="application/ld+json">'
            + json.dumps(
                {
                    "@graph": [
                        {
                            "@type": "Organization",
                            "name": "Other",
                            "logo": "https://other.com/logo.png",
                        },
                        {
                            "@type": "JobPosting",
                            "hiringOrganization": {
                                "@type": "Organization",
                                "name": "Example",
                                "url": "https://example.com/",
                                "logo": {
                                    "@type": "ImageObject",
                                    "contentUrl": "https://cdn.example.com/logo.png",
                                },
                            },
                        },
                    ]
                }
            )
            + "</script>"
        )
        self.assertEqual(parser.urls(), ["https://cdn.example.com/logo.png"])
        self.assertEqual(parser.structured_homepages, ["https://example.com/"])
        self.assertEqual(parser.kinds[parser.urls()[0]], "structured_logo")

    def test_invalid_json_and_urls_do_not_break_extraction(self):
        parser = LogoParser("https://example.com", "Example")
        parser.feed(
            '<script type="application/ld+json">not json</script><img alt="Example logo" src="https://[bad/logo.png"><link rel="icon" href="/favicon.png">'
        )
        self.assertEqual(parser.urls(), ["https://example.com/favicon.png"])

    def test_explicit_brand_logo_precedes_icon(self):
        parser = LogoParser("https://example.com", "Example")
        parser.feed(
            '<link rel="apple-touch-icon" href="/icon.png"><img alt="Example logo" data-src="/brand.png">'
        )
        self.assertEqual(parser.urls()[0], "https://example.com/brand.png")

    def test_official_domain_validation(self):
        self.assertEqual(employer_domain("https://www.example.com/"), "www.example.com")
        for value in (
            "linkedin.com",
            "www.linkedin.com",
            "example.recruitee.com",
            "localhost",
            "127.0.0.1",
            "https://user@example.com",
            "https://example.com:444",
            "https://example.com/?redirect=evil.com",
            "https://[bad",
            "example.com/evil",
        ):
            self.assertIsNone(employer_domain(value), value)

    def test_platform_icon_is_not_an_employer_logo(self):
        parser = LogoParser("https://jobs.ashbyhq.com/example", "Example")
        parser.feed(
            '<link rel="icon" href="/ashby.png"><meta property="og:image" content="https://app.ashbyhq.com/api/images/org-theme-logo/company/image">'
        )
        self.assertEqual(
            parser.urls(),
            ["https://app.ashbyhq.com/api/images/org-theme-logo/company/image"],
        )

    def test_logo_has_priority_and_vendor_footer_is_excluded(self):
        parser = LogoParser("https://jobs.lever.co/example", "Example")
        parser.feed(
            '<img alt="Lever logo" src="/lever.png"><img alt="Example logo" src="https://cdn.example.com/logo.png">'
        )
        self.assertEqual(parser.urls(), ["https://cdn.example.com/logo.png"])

    def test_employer_icon_is_preferred_to_customer_marketing_images(self):
        parser = LogoParser("https://example.com", "Example")
        parser.feed(
            '<img alt="Customer using Example logo" src="/customer.png"><link rel="apple-touch-icon" href="/brand.png">'
        )
        self.assertEqual(parser.urls()[0], "https://example.com/brand.png")

    def test_text_only_ats_brand_link_can_lead_to_the_official_site(self):
        parser = LogoParser("https://example.recruitee.com", "Example")
        parser.feed('<a class="navigation-logo" href="https://example.com">Example</a>')
        self.assertEqual(parser.homepages, ["https://example.com"])

    def test_raster_validation_rejects_html_svg_and_oversized_dimensions(self):
        for data in (
            b"<html>not a logo</html>",
            b'<svg xmlns="http://www.w3.org/2000/svg"/>',
        ):
            with self.assertRaises(CatalogueImportError):
                normalize_logo(data)
        output = io.BytesIO()
        Image.new("RGB", (2001, 2000)).save(output, format="PNG")
        with self.assertRaises(CatalogueImportError):
            normalize_logo(output.getvalue())
        self.assertTrue(normalize_logo(png()).startswith(b"\x89PNG"))

    def test_cross_host_redirect_still_rejects_private_dns(self):
        response = MagicMock(status=302)
        response.getheader.return_value = "https://internal.example/logo.png"

        def addresses(host, *args, **kwargs):
            ip = "1.1.1.1" if host == "public.example" else "127.0.0.1"
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443))]

        with (
            patch("socket.getaddrinfo", side_effect=addresses),
            patch("jobboard.integrations.public_html.PinnedHTTPSConnection") as conn,
        ):
            conn.return_value.getresponse.return_value = response
            with self.assertRaises(CatalogueImportError):
                fetch_public("https://public.example/logo.png", image=True)
            self.assertEqual(conn.call_count, 1)


class CachedLogoTests(TestCase):
    def test_malformed_provider_logo_is_reported_as_an_extraction_failure(self):
        company = Company.objects.create(name="Example")
        with self.assertRaisesMessage(CatalogueImportError, "unsafe_public_url"):
            cache_logo(company, "https://[bad/image.png")

    def test_rejected_legacy_logo_is_not_serialized_or_served(self):
        company = Company.objects.create(name="Bad")
        company.logo_object_key = (
            f"company-logos/{company.pk}/{next(iter(REJECTED_LOGO_DIGESTS))}.png"
        )
        company.save()
        self.assertIsNone(CompanySerializer(company).data["logo_url"])
        user = get_user_model().objects.create_user(username="bad-logo-test")
        self.client.force_login(user)
        with patch("jobboard.api.company_logos.read_object") as read:
            self.assertEqual(
                self.client.get(f"/api/v1/companies/{company.pk}/logo/").status_code,
                404,
            )
            read.assert_not_called()

    def test_platform_domain_is_not_exposed_as_employer_identity(self):
        company = Company(name="Example", domain="fr.linkedin.com")
        self.assertIsNone(CompanySerializer(company).data["domain"])

    def test_provider_company_logo_is_cached_without_reading_generic_site(self):
        from jobboard.models import Offer, OfferSource, SourceBoard

        company = Company.objects.create(name="Example")
        board = SourceBoard.objects.create(
            company=company,
            provider="jobspy",
            instance="global",
            board_key="example",
            base_url="https://www.linkedin.com",
        )
        offer = Offer.objects.create(
            company=company, title="Stage", description="Stage"
        )
        OfferSource.objects.create(
            offer=offer,
            board=board,
            external_id="123",
            origin_url="https://www.linkedin.com/jobs/view/123",
            apply_url="https://www.linkedin.com/jobs/view/123",
            content_hash="a" * 64,
            raw_payload={
                "company": "Example",
                "company_logo": "https://media.licdn.com/company-logo.png",
            },
        )
        with (
            tempfile.TemporaryDirectory() as root,
            override_settings(
                PRIVATE_STORAGE_BACKEND="local", PRIVATE_STORAGE_ROOT=root
            ),
            patch(
                "jobboard.services.company_logos.fetch_public",
                return_value=("https://media.licdn.com/company-logo.png", png()),
            ) as fetch,
        ):
            extract_logo(company)
        fetch.assert_called_once()
        self.assertTrue(fetch.call_args.kwargs["image"])
        company.refresh_from_db()
        self.assertEqual(company.logo_source_kind, "source_metadata")
        self.assertIsNone(company.domain)

    def test_cached_logo_serialization_and_authenticated_delivery(self):
        company = Company.objects.create(name="Example")
        self.assertIsNone(CompanySerializer(company).data["logo_url"])
        with (
            tempfile.TemporaryDirectory() as root,
            override_settings(
                PRIVATE_STORAGE_BACKEND="local", PRIVATE_STORAGE_ROOT=root
            ),
            patch(
                "jobboard.services.company_logos.fetch_public",
                return_value=("https://example.com/logo.png", png()),
            ) as fetch,
        ):
            cache_logo(company, "https://example.com/logo.png")
            cache_logo(company, "https://example.com/logo.png")
            company.refresh_from_db()
            self.assertEqual(company.logo_source_url, "https://example.com/logo.png")
            self.assertEqual(company.logo_source_kind, "manual")
            self.assertIsNotNone(company.logo_fetched_at)
            self.assertEqual(fetch.call_count, 2)
            url = CompanySerializer(company).data["logo_url"]
            self.assertIn(f"/companies/{company.pk}/logo/", url)
            self.assertIn(self.client.get(url).status_code, (401, 403))
            user = get_user_model().objects.create_user(
                username="logo-test", password="test-password"
            )
            self.client.force_login(user)
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response["Content-Type"], "image/png")
            self.assertTrue(response.content.startswith(b"\x89PNG"))
            self.assertEqual(
                fetch.call_count, 2, "Serving a logo must not make network calls"
            )
            company.logo_object_key = "documents/private.pdf"
            company.save()
            self.assertEqual(self.client.get(url).status_code, 404)

    def test_rejected_digest_is_never_cached(self):
        company = Company.objects.create(name="Example")
        with (
            patch(
                "jobboard.services.company_logos.fetch_public",
                return_value=("https://example.com/image.png", png()),
            ),
            patch("jobboard.services.company_logos.hashlib.sha256") as digest,
            patch("jobboard.services.company_logos.write_object") as write,
        ):
            digest.return_value.hexdigest.return_value = next(
                iter(REJECTED_LOGO_DIGESTS)
            )
            with self.assertRaisesMessage(
                CatalogueImportError, "platform_logo_rejected"
            ):
                cache_logo(company, "https://example.com/image.png")
            write.assert_not_called()
        company.refresh_from_db()
        self.assertIsNone(company.logo_object_key)

    def test_successful_official_extraction_records_domain_and_provenance(self):
        company = Company.objects.create(
            name="Example", website_url="https://www.linkedin.com"
        )
        from jobboard.models import Offer, OfferSource, SourceBoard

        board = SourceBoard.objects.create(
            company=company,
            provider="wttj",
            instance="global",
            board_key="example",
            base_url="https://www.welcometothejungle.com",
        )
        offer = Offer.objects.create(
            company=company, title="Stage", description="Stage"
        )
        OfferSource.objects.create(
            offer=offer,
            board=board,
            external_id="123",
            origin_url="https://www.welcometothejungle.com/fr/jobs/123",
            apply_url="https://example.com/jobs/123",
            content_hash="a" * 64,
        )
        # An invalid platform website must not prevent repairing the employer identity.
        company.website_url = None
        company.save()
        html = (
            '<script type="application/ld+json">'
            + json.dumps(
                {
                    "@type": "JobPosting",
                    "hiringOrganization": {
                        "@type": "Organization",
                        "name": "Example",
                        "url": "https://example.com/",
                        "logo": "https://cdn.example.com/logo.png",
                    },
                }
            )
            + "</script>"
        )
        calls = []

        def fetch(url, **kwargs):
            calls.append(url)
            return url, png() if kwargs.get("image") else html

        with (
            tempfile.TemporaryDirectory() as root,
            override_settings(
                PRIVATE_STORAGE_BACKEND="local", PRIVATE_STORAGE_ROOT=root
            ),
            patch("jobboard.services.company_logos.fetch_public", side_effect=fetch),
        ):
            extract_logo(company)
        self.assertEqual(
            calls,
            [
                "https://www.welcometothejungle.com/fr/jobs/123",
                "https://cdn.example.com/logo.png",
            ],
        )
        company.refresh_from_db()
        self.assertEqual(company.domain, "example.com")
        self.assertEqual(company.logo_source_kind, "structured_logo")

    def test_refresh_failure_preserves_previous_logo(self):
        company = Company.objects.create(
            name="Example",
            website_url="https://example.com/",
            logo_object_key="company-logos/1/" + "a" * 64 + ".png",
        )
        with (
            patch(
                "jobboard.services.company_logos.fetch_public",
                side_effect=CatalogueImportError("public_http_error"),
            ),
            self.assertRaises(CatalogueImportError),
        ):
            extract_logo(company)
        company.refresh_from_db()
        self.assertTrue(company.logo_object_key)

    def test_repair_only_revokes_confirmed_platform_digest(self):
        from importlib import import_module

        from django.apps import apps
        from django.db import connection

        bad = Company.objects.create(
            name="Bad",
            logo_object_key="company-logos/1/"
            + next(iter(REJECTED_LOGO_DIGESTS))
            + ".png",
        )
        good = Company.objects.create(
            name="Good", logo_object_key="company-logos/2/" + "a" * 64 + ".png"
        )
        import_module(
            "jobboard.migrations.0026_company_logo_provenance"
        ).reject_linkedin_favicon(apps, connection.schema_editor())
        bad.refresh_from_db()
        good.refresh_from_db()
        self.assertIsNone(bad.logo_object_key)
        self.assertEqual(bad.logo_last_error, "platform_logo_rejected")
        self.assertTrue(good.logo_object_key)


class LogoQueueTests(TestCase):
    def test_new_company_is_automatically_due_and_retry_is_delayed(self):
        from django.utils import timezone

        from jobboard.services.company_logos import process_logo_jobs

        company = Company.objects.create(name="New employer")
        self.assertLessEqual(company.logo_next_attempt_at, timezone.now())
        with patch(
            "jobboard.services.company_logos.extract_logo",
            side_effect=CatalogueImportError("public_fetch_failed"),
        ) as extract:
            self.assertEqual(process_logo_jobs(), 1)
            self.assertEqual(process_logo_jobs(), 0)
            extract.assert_called_once()
        company.refresh_from_db()
        self.assertEqual(company.logo_attempts, 1)
        self.assertGreater(company.logo_next_attempt_at, timezone.now())
        self.assertEqual(company.logo_last_error, "public_fetch_failed")

    def test_successful_retry_stops_future_jobs(self):
        from jobboard.services.company_logos import process_logo_jobs

        company = Company.objects.create(
            name="New employer", logo_last_error="old failure", logo_attempts=1
        )
        with (
            tempfile.TemporaryDirectory() as root,
            override_settings(
                PRIVATE_STORAGE_BACKEND="local", PRIVATE_STORAGE_ROOT=root
            ),
            patch(
                "jobboard.services.company_logos.fetch_public",
                return_value=("https://example.com/logo.png", png()),
            ),
            patch(
                "jobboard.services.company_logos.extract_logo",
                side_effect=lambda company: cache_logo(
                    company, "https://example.com/logo.png"
                ),
            ),
        ):
            self.assertEqual(process_logo_jobs(), 1)
            self.assertEqual(process_logo_jobs(), 0)
        company.refresh_from_db()
        self.assertIsNone(company.logo_next_attempt_at)
        self.assertEqual(company.logo_last_error, "")
        self.assertTrue(company.logo_object_key)

    def test_catalogue_worker_consumes_logo_queue(self):
        from django.core.management import call_command

        with (
            patch(
                "jobboard.management.commands.run_catalogue_worker.close_old_connections"
            ),
            patch(
                "jobboard.management.commands.run_catalogue_worker.process_logo_jobs",
                return_value=1,
            ) as logos,
            patch(
                "jobboard.management.commands.run_catalogue_worker.schedule_due",
                return_value=0,
            ),
            patch(
                "jobboard.management.commands.run_catalogue_worker.process_one",
                return_value=False,
            ),
            patch("jobboard.services.engine_discovery.run_discovery"),
            patch("jobboard.services.engine_search_discovery.run_search_discovery"),
            patch("jobboard.services.engine_alerts.run_alerts"),
            patch("jobboard.services.engine_external.process_external_opportunities"),
        ):
            call_command("run_catalogue_worker", once=True, stdout=io.StringIO())
            logos.assert_called_once_with(limit=5)
