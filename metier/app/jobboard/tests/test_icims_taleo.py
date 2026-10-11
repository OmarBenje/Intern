import json
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase

from jobboard.integrations.greenhouse_catalogue import CatalogueImportError
from jobboard.integrations.icims_catalogue import fetch_icims, normalize_job
from jobboard.integrations.public_catalogue import CatalogueSnapshot
from jobboard.integrations.taleo_catalogue import normalize_job as normalize_taleo
from jobboard.models import Company, OfferSource, SourceBoard
from jobboard.services.catalogue import import_board
from jobboard.services.engine_collection import parse_source_url

URL = "https://careers-hines.icims.com/jobs/123/analyst/job"


def detail(
    country="FR",
    title="Business Analyst Intern",
    expiry="2099-01-01T00:00:00Z",
    url=URL,
):
    return (
        '<script type="application/ld+json">'
        + json.dumps(
            {
                "@type": "JobPosting",
                "url": url,
                "title": title,
                "description": "<p>Internship in analysis.</p>",
                "jobLocation": [
                    {"address": {"addressCountry": country, "addressLocality": "Paris"}}
                ],
                "employmentType": "OTHER",
                "validThrough": expiry,
            }
        )
        + "</script>"
    )


def taleo_detail(contest="INT-123", title="Internship - Analysis"):
    return f"""<div id="requisitionDescriptionInterface.descRequisitionContainer">
    <span id="requisitionDescriptionInterface.reqTitleLinkAction">{title}</span>
    <span id="requisitionDescriptionInterface.reqContestNumberValue">{contest}</span>
    <p>Internship in analysis.</p><script>hidden</script></div>"""


def taleo_row(location="Austria-Vienna-Vienna-IAEA Headquarters"):
    return {
        "jobId": "123",
        "contestNo": "INT-123",
        "column": [
            "Internship - Analysis",
            json.dumps([location]),
            "2099-10-01, 9:59:00 PM",
        ],
        "locationsColumns": [1],
    }


class PublicPortalTests(SimpleTestCase):
    def test_icims_country_and_contract(self):
        row = normalize_job(detail(), URL, "hines")
        self.assertEqual(row["external_id"], "123")
        self.assertEqual(row["location_details"], [{"name": "Paris", "country": "FR"}])
        self.assertEqual(
            normalize_job(detail(country="UK"), URL, "hines")["location_details"][0][
                "country"
            ],
            "GB",
        )
        for country in ("US", ""):
            self.assertIsNone(normalize_job(detail(country=country), URL, "hines"))
        for title in (
            "Senior Engineer",
            "Internal Sales Manager",
            "Working Student",
            "Apprenticeship",
        ):
            self.assertIsNone(normalize_job(detail(title=title), URL, "hines"))

    def test_icims_expiry_identity_and_schema(self):
        self.assertIsNone(
            normalize_job(detail(expiry="2020-01-01T00:00:00Z"), URL, "hines")
        )
        for html in (
            detail(url=URL.replace("123", "999")),
            detail(url="https://evil.test/jobs/123/analyst/job"),
            detail(expiry="invalid"),
            "<h1>Internship</h1>",
        ):
            with self.assertRaises(CatalogueImportError):
                normalize_job(html, URL, "hines")

    def test_only_inspected_boards_registered(self):
        self.assertEqual(parse_source_url(URL)["provider"], "icims")
        self.assertEqual(
            parse_source_url(
                "https://iaea.taleo.net/careersection/ex/jobdetail.ftl?job=123"
            )["provider"],
            "taleo",
        )
        for url in (
            "https://careers-hines.icims.com/login",
            "https://careers-hines.icims.com.evil.test/jobs/search",
            "https://iaea.taleo.net/admin",
            "http://iaea.taleo.net/careersection/ex/jobsearch.ftl",
            "https://unknown.icims.com/jobs/search",
        ):
            with self.assertRaises(CatalogueImportError):
                parse_source_url(url)

    @patch("jobboard.integrations.icims_catalogue.fetch_html")
    def test_icims_pagination_deduplication_and_partial(self, fetch):
        fetch.side_effect = [
            (
                "https://careers-hines.icims.com/jobs/search",
                f'<a href="{URL}">Intern</a><a href="?pr=1&searchKeyword=intern">Next</a><a href="https://evil.test/jobs/999/test/job">Bad</a>',
            ),
            (URL + "?in_iframe=1", detail()),
            (
                "https://careers-hines.icims.com/jobs/search",
                f'<a href="{URL}">Duplicate</a>',
            ),
        ]
        rows = fetch_icims("hines")
        self.assertEqual(len(rows), 1)
        self.assertEqual(fetch.call_count, 3)
        self.assertFalse(rows.complete)

    @patch("jobboard.integrations.icims_catalogue.fetch_html")
    def test_network_failures_are_not_empty_success(self, fetch):
        fetch.side_effect = CatalogueImportError("public_http_error")
        with self.assertRaises(CatalogueImportError):
            fetch_icims("hines")
        fetch.side_effect = [
            (
                "https://careers-hines.icims.com/jobs/search",
                f'<a href="{URL}">Intern</a><a href="/jobs/999/analyst/job">Intern</a>',
            ),
            (URL + "?in_iframe=1", detail()),
            CatalogueImportError("public_http_error"),
        ]
        rows = fetch_icims("hines")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows.errors[-1]["code"], "public_http_error")

    def test_taleo_explicit_geography_and_scoped_description(self):
        row = normalize_taleo(taleo_row(), taleo_detail())
        self.assertEqual(row["location_details"][0]["country"], "AT")
        self.assertNotIn("hidden", row["description"])
        for location in ("United States-New York", "Vienna"):
            self.assertIsNone(normalize_taleo(taleo_row(location), taleo_detail()))
        self.assertIsNone(
            normalize_taleo(taleo_row(), taleo_detail(title="Senior Engineer"))
        )

    def test_taleo_hydrated_public_history_is_read_without_javascript(self):
        from urllib.parse import quote

        names = [
            "reqlistitem.no",
            "reqlistitem.title",
            "reqlistitem.contestnumber",
            "reqlistitem.description",
        ]
        values = [
            "123",
            "Internship - Analysis",
            "INT-123",
            "!* !<p>Internship duties.</p>".replace("!* !", "!*!"),
        ]
        history = (
            "ftlx0!%24!requisitionDescriptionInterface!|!descRequisition!|!rdPager!%24!"
            + "!|!".join(quote(v) for v in values)
        )
        html = (
            '<input id="initialHistory" value="'
            + history
            + '"><script>descRequisition: {_hlid: ['
            + ",".join(repr(n) for n in names)
            + "]}</script>"
        )
        row = normalize_taleo(taleo_row(), html)
        self.assertIn("Internship duties.", row["description"])
        with self.assertRaises(CatalogueImportError):
            normalize_taleo(taleo_row(), html.replace("reqlistitem.no", "wrong"))

    def test_taleo_identity_expiry_and_bad_locations(self):
        with self.assertRaises(CatalogueImportError):
            normalize_taleo(taleo_row(), taleo_detail(contest="WRONG"))
        row = taleo_row()
        row["column"][2] = "2020-01-01, 9:59:00 PM"
        self.assertIsNone(normalize_taleo(row, taleo_detail()))
        row["column"][1] = "bad json"
        with self.assertRaises(CatalogueImportError):
            normalize_taleo(row, taleo_detail())

    @patch("jobboard.integrations.taleo_catalogue.search")
    @patch("jobboard.integrations.taleo_catalogue.fetch_html")
    def test_taleo_live_contract_and_failed_second_page(self, fetch, search):
        from jobboard.integrations.taleo_catalogue import BASE, fetch_taleo

        fetch.side_effect = [
            (BASE, "portalNo: '1234'"),
            (BASE + "/jobdetail.ftl?job=INT-123&lang=en", taleo_detail()),
        ]
        search.side_effect = [
            {
                "requisitionList": [taleo_row()],
                "pagingData": {"totalCount": 2, "pageSize": 1, "currentPageNo": 1},
            },
            CatalogueImportError("public_http_error"),
        ]
        rows = fetch_taleo("iaea-ex")
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows.complete)
        self.assertEqual(rows.errors[-1]["code"], "public_http_error")


class PortalImportTests(TestCase):
    @patch("jobboard.services.catalogue.fetch_normalized")
    def test_both_providers_import_idempotently_without_absence_closure(self, fetch):
        for provider, key, row in (
            ("icims", "hines", normalize_job(detail(), URL, "hines")),
            ("taleo", "iaea-ex", normalize_taleo(taleo_row(), taleo_detail())),
        ):
            board = SourceBoard.objects.create(
                provider=provider,
                instance="global",
                board_key=key,
                company=Company.objects.create(name=provider),
                enabled=True,
            )
            fetch.return_value = CatalogueSnapshot([row], complete=False)
            import_board(board.pk)
            import_board(board.pk)
            self.assertEqual(OfferSource.objects.filter(board=board).count(), 1)
            fetch.return_value = CatalogueSnapshot([], complete=False)
            import_board(board.pk)
            self.assertEqual(
                OfferSource.objects.get(board=board).source_status, "active"
            )
