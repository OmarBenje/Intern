from unittest.mock import patch

from django.test import SimpleTestCase, TestCase

from jobboard.integrations.greenhouse_catalogue import CatalogueImportError
from jobboard.integrations.public_catalogue import CatalogueSnapshot
from jobboard.integrations.successfactors_catalogue import (
    fetch_successfactors,
    normalize_job,
)
from jobboard.models import Company, OfferSource, SourceBoard
from jobboard.services.catalogue import import_board
from jobboard.services.engine_collection import parse_source_url
from jobboard.services.engine_search_discovery import candidate_from_url

URL = "https://careers.sap.com/job/Paris-Intern/123/"


def detail(
    title="Marketing Intern",
    address='<meta itemprop="addressCountry" content="FR"><meta itemprop="addressLocality" content="Paris">',
):
    return f"""<div itemscope itemtype="http://schema.org/JobPosting"><span itemprop="address">{address}</span><h1><span itemprop="title">{title}</span></h1><span itemprop="description"><p>Internship in <strong>marketing</strong>.</p><p>Six months.</p><script>ignore me</script></span></div>"""


class SuccessFactorsParserTests(SimpleTestCase):
    def test_country_and_description_are_scoped_to_posting(self):
        row = normalize_job(
            '<meta itemprop="addressCountry" content="US">' + detail(), URL, "sap"
        )
        self.assertEqual(row["external_id"], "123")
        self.assertEqual(row["location_details"], [{"name": "Paris", "country": "FR"}])
        self.assertIn("Internship in marketing.", row["description"])
        self.assertNotIn("ignore me", row["description"])

    def test_explicit_country_in_structured_address_and_multiple_locations(self):
        row = normalize_job(
            detail(
                address='<meta itemprop="streetAddress" content="Walldorf, DE, 69190">'
            ),
            URL,
            "sap",
        )
        self.assertEqual(row["location_details"][0]["country"], "DE")
        html = detail().replace(
            "<h1>",
            '<span itemprop="address"><meta itemprop="addressCountry" content="DE"><meta itemprop="addressLocality" content="Berlin"></span><h1>',
        )
        self.assertEqual(len(normalize_job(html, URL, "sap")["locations"]), 2)

    def test_unknown_country_outside_europe_and_wrong_contract_excluded(self):
        for address in (
            '<meta itemprop="streetAddress" content="Paris">',
            '<meta itemprop="streetAddress" content="Paris, TX, US">',
        ):
            self.assertIsNone(normalize_job(detail(address=address), URL, "sap"))
        for title in (
            "Working Student Marketing",
            "Apprenticeship in Marketing",
            "Senior Engineer",
        ):
            self.assertIsNone(normalize_job(detail(title=title), URL, "sap"))
        with self.assertRaises(CatalogueImportError):
            normalize_job("<h1>Intern</h1>", URL, "sap")

    def test_registered_urls_reject_unverified_hosts_and_login_paths(self):
        self.assertEqual(parse_source_url(URL)["board_key"], "sap")
        for url in (
            "https://careers.sap.com/login",
            "https://careers.sap.com.evil.test/job/x/123/",
            "http://careers.sap.com",
            "https://careers.sap.com:444/",
            "https://careers.sap.com/?q=test",
        ):
            with self.assertRaises(CatalogueImportError):
                parse_source_url(url)

    @patch("jobboard.integrations.successfactors_catalogue.TERMS", ("internship",))
    @patch("jobboard.integrations.successfactors_catalogue.fetch_html")
    def test_pagination_deduplication_and_partial_snapshot(self, fetch):
        def response(url, *_args, **_kwargs):
            if "/job/" in url:
                return url, detail()
            if "startrow=25" in url:
                return (
                    url,
                    '<a href="/job/Paris-Intern/123/">duplicate</a><a href="?q=internship&startrow=0">Back</a>',
                )
            return (
                url,
                '<a href="/job/Paris-Intern/123/">Intern</a><a href="https://evil.test/job/x/456/">Bad</a><a href="?q=internship&startrow=25">Next</a>',
            )

        fetch.side_effect = response
        rows = fetch_successfactors("sap")
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows.complete)
        self.assertEqual(fetch.call_count, 3)
        self.assertEqual(rows.errors[0]["code"], "keyword_search_partial")

    @patch("jobboard.integrations.successfactors_catalogue.TERMS", ("internship",))
    @patch("jobboard.integrations.successfactors_catalogue.fetch_html")
    def test_bad_detail_does_not_discard_valid_sibling(self, fetch):
        fetch.side_effect = [
            (
                "https://careers.sap.com/search/?q=internship",
                '<a href="/job/x/1/">Intern One</a><a href="/job/x/2/">Intern Two</a>',
            ),
            ("https://careers.sap.com/job/x/1/", "not a job"),
            ("https://careers.sap.com/job/x/2/", detail()),
        ]
        rows = fetch_successfactors("sap")
        self.assertEqual([row["external_id"] for row in rows], ["2"])
        self.assertIn(
            {"external_id": "1", "code": "job_detail_unconfirmed"}, rows.errors
        )

    @patch("jobboard.integrations.successfactors_catalogue.fetch_html")
    def test_access_failure_stops_requests_and_is_durable(self, fetch):
        fetch.side_effect = CatalogueImportError("public_http_error")
        with self.assertRaises(CatalogueImportError) as error:
            fetch_successfactors("sap")
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(error.exception.code, "public_http_error")

    @patch("jobboard.integrations.successfactors_catalogue.TERMS", ("internship",))
    @patch("jobboard.integrations.successfactors_catalogue.MAX_PAGES_PER_TERM", 1)
    @patch("jobboard.integrations.successfactors_catalogue.fetch_html")
    def test_page_cap_and_non_intern_title_do_not_issue_extra_requests(self, fetch):
        fetch.return_value = (
            "https://careers.sap.com/search/?q=internship",
            '<a href="/job/Manager/1/">Production Stage Manager</a><a href="/job/Engineer/2/">Senior Engineer</a><a href="?q=internship&startrow=25">Next</a>',
        )
        # Stage Manager is inspected then rejected by the common classifier;
        # Senior Engineer never consumes a detail request.
        fetch.side_effect = [
            fetch.return_value,
            ("https://careers.sap.com/job/Manager/1/", detail(title="Stage Manager")),
        ]
        rows = fetch_successfactors("sap")
        self.assertEqual(len(rows), 0)
        self.assertEqual(fetch.call_count, 2)
        self.assertIn(
            {"query": "internship", "code": "page_budget_exceeded"}, rows.errors
        )

    @patch("jobboard.integrations.successfactors_catalogue.TERMS", ("internship",))
    @patch("jobboard.integrations.successfactors_catalogue.fetch_html")
    def test_later_network_failure_keeps_successful_detail(self, fetch):
        fetch.side_effect = [
            (
                "https://careers.sap.com/search/?q=internship",
                '<a href="/job/x/1/">Intern</a><a href="/job/x/2/">Intern</a>',
            ),
            ("https://careers.sap.com/job/x/1/", detail()),
            CatalogueImportError("public_http_error"),
        ]
        rows = fetch_successfactors("sap")
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows.complete)
        self.assertEqual(rows.errors[-1]["code"], "public_http_error")


class SuccessFactorsImportTests(TestCase):
    @patch("jobboard.services.catalogue.fetch_normalized")
    def test_partial_import_is_idempotent_and_never_reconciles_absence(self, fetch):
        board = SourceBoard.objects.create(
            provider="successfactors",
            instance="global",
            board_key="sap",
            company=Company.objects.create(name="SAP"),
            base_url="https://careers.sap.com",
            enabled=True,
        )
        row = normalize_job(detail(), URL, "sap")
        fetch.return_value = CatalogueSnapshot(
            [row], complete=False, errors=[{"code": "keyword_search_partial"}]
        )
        import_board(board.pk)
        import_board(board.pk)
        self.assertEqual(OfferSource.objects.filter(board=board).count(), 1)
        fetch.return_value = CatalogueSnapshot(
            [], complete=False, errors=[{"code": "public_http_error"}]
        )
        run = import_board(board.pk)
        self.assertFalse(run.is_full_snapshot)
        self.assertEqual(OfferSource.objects.get(board=board).source_status, "active")

    def test_discovery_recognizes_employer_job_link(self):
        candidate = candidate_from_url(URL, "SAP")
        self.assertEqual(candidate.provider, "successfactors")
        self.assertEqual(candidate.url, "https://careers.sap.com")
