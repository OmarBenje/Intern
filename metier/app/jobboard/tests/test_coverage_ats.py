from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase

from jobboard.integrations.greenhouse_catalogue import CatalogueImportError
from jobboard.integrations.personio_catalogue import normalize_personio
from jobboard.integrations.public_catalogue import fetch_normalized
from jobboard.integrations.recruitee_catalogue import (
    normalize_recruitee,
    normalize_recruitee_xml,
)
from jobboard.models import Company, OfferSource, SourceBoard
from jobboard.services.catalogue import import_board
from jobboard.services.engine_collection import parse_source_url

from .test_smartrecruiters import listing, posting


class ATSNormalizationTests(SimpleTestCase):
    def test_personio_entities_country_and_contract(self):
        feed = b"<workzag-jobs><position><id>1</id><name>Marketing Intern</name><office>Berlin, Germany</office><employmentType>internship</employmentType><jobDescriptions><jobDescription><value><![CDATA[<p>Six month internship</p>]]></value></jobDescription></jobDescriptions></position></workzag-jobs>"
        rows = normalize_personio(feed, "acme", "de")
        self.assertTrue(rows.complete)
        self.assertEqual(rows[0]["contract_type"], "internship")
        self.assertIn("Six month", rows[0]["description"])
        self.assertEqual(rows[0]["url"], "https://acme.jobs.personio.de/job/1")
        for attack in [
            b'<!DOCTYPE x [<!ENTITY b "expanded">]><workzag-jobs/>',
            "<!DOCTYPE x><workzag-jobs/>".encode("utf-16"),
        ]:
            with self.assertRaises(CatalogueImportError):
                normalize_personio(attack, "acme", "de")
        student = normalize_personio(
            feed.replace(b"internship</employmentType>", b"student</employmentType>"),
            "acme",
            "de",
        )
        self.assertNotIn("contract_type", student[0])

    def test_recruitee_multicountry_and_remote(self):
        job = {
            "id": 42,
            "title": "Intern",
            "description": "<p>Internship</p>",
            "careers_url": "https://acme.recruitee.com/o/intern",
            "employment_type_code": "internship",
            "remote": True,
            "locations": [
                {"city": "Amsterdam", "country": "Netherlands", "country_code": "NL"},
                {"city": "Boston", "country": "United States", "country_code": "US"},
            ],
        }
        rows = normalize_recruitee({"offers": [job]})
        self.assertEqual(rows[0]["work_mode"], "remote")
        self.assertEqual(
            [x["country"] for x in rows[0]["location_details"]], ["NL", "US"]
        )
        with self.assertRaises(CatalogueImportError):
            normalize_recruitee({"offers": [job, job]})
        rows = normalize_recruitee(
            {"offers": [job, dict(job, id=43, careers_url="file:///etc/passwd")]}
        )
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows.complete)

    def test_recruitee_public_xml_fallback(self):
        feed = b"<offers><offer><id>1</id><slug>intern</slug><title>Intern</title><country_code>NL</country_code><country>Netherlands</country><city>Amsterdam</city><employment_type_code>internship</employment_type_code><remote>false</remote></offer></offers>"
        self.assertEqual(
            normalize_recruitee_xml(feed, "acme")[0]["location_details"][0]["country"],
            "NL",
        )
        with (
            patch(
                "jobboard.integrations.recruitee_catalogue.read_json",
                side_effect=CatalogueImportError("upstream_http_error"),
            ),
            patch(
                "jobboard.integrations.recruitee_catalogue.read_xml", return_value=feed
            ),
        ):
            rows = fetch_normalized(
                SimpleNamespace(
                    provider="recruitee", instance="global", board_key="acme"
                )
            )
        self.assertEqual(len(rows), 1)

    def test_oversized_workday_identity_rejected_before_database(self):
        from jobboard.services.engine_collection import register_source

        tenant = "x" * 63
        site = "y" * 100
        with self.assertRaisesMessage(CatalogueImportError, "invalid_board_key"):
            register_source(f"https://{tenant}.wd3.myworkdayjobs.com/{site}", "Example")

    def test_canonical_source_urls(self):
        for url, provider, key, instance in [
            ("https://acme.jobs.personio.de/job/42", "personio", "acme", "de"),
            ("https://acme.jobs.personio.com/xml", "personio", "acme", "com"),
            ("https://acme.recruitee.com/o/intern", "recruitee", "acme", "global"),
        ]:
            row = parse_source_url(url)
            self.assertEqual(
                (row["provider"], row["board_key"], row["instance"]),
                (provider, key, instance),
            )
        for bad in [
            "https://acme.recruitee.com.evil/o/x",
            "https://acme.jobs.personio.de:444/",
            "https://acme.jobs.personio.de/?url=http://localhost",
            "https://evil@acme.recruitee.com/",
        ]:
            with self.assertRaises(CatalogueImportError):
                parse_source_url(bad)


class PartialSnapshotTests(TestCase):
    def test_bad_smart_detail_keeps_freshness_valid_row_imports_and_no_absence(self):
        board = SourceBoard.objects.create(
            provider="smartrecruiters",
            board_key="Acme",
            company=Company.objects.create(name="Acme"),
            base_url="https://careers.smartrecruiters.com/Acme",
        )
        a, b, c = posting("1"), posting("2"), posting("3")
        with patch(
            "jobboard.integrations.public_catalogue.read_json",
            side_effect=[listing(a, b), a, b],
        ):
            import_board(board.pk)
        before = OfferSource.objects.get(external_id="2").last_checked_at
        with patch(
            "jobboard.integrations.public_catalogue.read_json",
            side_effect=[listing(b, c), posting("2", country="us"), c],
        ):
            run = import_board(board.pk)
        self.assertFalse(run.is_full_snapshot)
        self.assertEqual(run.error_code, "partial_snapshot")
        self.assertEqual(
            run.diagnostics, [{"external_id": "2", "code": "snapshot_changed"}]
        )
        self.assertEqual(
            OfferSource.objects.get(external_id="2").last_checked_at, before
        )
        self.assertEqual(
            OfferSource.objects.get(external_id="1").source_status, "active"
        )
        self.assertTrue(OfferSource.objects.filter(external_id="3").exists())


class PersonioDetailTests(SimpleTestCase):
    def test_jsonld_explicit_country_and_partial_error(self):
        from jobboard.integrations.personio_catalogue import fetch_personio

        feed = b"<workzag-jobs><position><id>1</id><name>Intern</name><office>Berlin</office><employmentType>intern</employmentType></position><position><id>2</id><name>Intern</name><office>Paris</office><employmentType>intern</employmentType></position></workzag-jobs>"
        html = '<script type="application/ld+json">{"@type":"JobPosting","title":"Intern","description":"Internship marketing","jobLocation":{"address":{"addressLocality":"Berlin","addressCountry":"DE"}}}</script>'
        with (
            patch(
                "jobboard.integrations.personio_catalogue.read_xml", return_value=feed
            ),
            patch(
                "jobboard.integrations.personio_catalogue.fetch_html",
                side_effect=[
                    ("https://acme.jobs.personio.de/job/1", html),
                    CatalogueImportError("public_fetch_failed"),
                ],
            ),
        ):
            rows = fetch_personio("acme", "de")
        self.assertFalse(rows.complete)
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            rows[0]["location_details"], [{"name": "Berlin, DE", "country": "DE"}]
        )
        self.assertEqual(
            rows.errors, [{"external_id": "2", "code": "public_fetch_failed"}]
        )
