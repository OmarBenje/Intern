from unittest.mock import Mock, patch

from django.test import SimpleTestCase, TestCase

from jobboard.integrations.greenhouse_catalogue import CatalogueImportError
from jobboard.integrations.teamtailor_catalogue import normalize_teamtailor
from jobboard.integrations.workable_catalogue import normalize_workable
from jobboard.models import Company, OfferSource, SourceBoard
from jobboard.services.catalogue import import_board
from jobboard.services.engine_collection import parse_source_url

RSS = """<rss xmlns:tt="https://teamtailor.com/locations"><channel><item>
<title>Marketing internship</title><link>https://acme.teamtailor.com/jobs/123-intern</link>
<description>Six month internship in our marketing team working on research and campaigns.</description>
<tt:locations><tt:location><tt:city>Paris</tt:city><tt:country>France</tt:country></tt:location>
<tt:location><tt:city>Boston</tt:city><tt:country>United States</tt:country></tt:location></tt:locations>
<remoteStatus>fully</remoteStatus></item></channel></rss>"""
JOB = {
    "shortcode": "ABC123",
    "title": "Marketing internship",
    "type": "internship",
    "country": "France",
    "city": "Paris",
}
DESCRIPTION = "# Marketing internship\nSix month internship in our marketing team working on research and campaigns."


class PublicATSTests(SimpleTestCase):
    def test_english_title_french_description_requires_explicit_stage_context(self):
        from jobboard.services.engine_quality import extract_facts

        for description in [
            "Votre stage durera six mois.",
            "Nous proposons un stage de 6 mois.",
        ]:
            self.assertEqual(
                extract_facts("Data Engineer Intern", description)["classification"],
                "confirmed",
            )
        self.assertEqual(
            extract_facts(
                "Data Engineer Intern", "Help us launch our early stage startup."
            )["classification"],
            "uncertain",
        )
        self.assertEqual(
            extract_facts("Graduate programme", "Votre stage durera six mois.")[
                "classification"
            ],
            "not_internship",
        )

    def test_linkedin_boolean_class_attributes_do_not_crash_worker(self):
        from jobboard.integrations.linkedin_discovery import VisibleLinks

        parser = VisibleLinks()
        parser.feed(
            '<div class style><a class href="https://example.com">Careers</a></div><div hidden><a href="https://hidden.example">Hidden</a></div>'
        )
        self.assertEqual(parser.links, ["https://example.com"])

    def test_teamtailor_preserves_all_locations_remote_and_partial(self):
        rows = normalize_teamtailor(RSS)
        self.assertFalse(rows.complete)
        self.assertEqual(rows[0]["external_id"], "123")
        self.assertEqual(rows[0]["work_mode"], "remote")
        self.assertEqual(
            [x["country"] for x in rows[0]["location_details"]],
            ["France", "United States"],
        )

    def test_teamtailor_invalid_feed_and_missing_description(self):
        for feed in ["<rss/>", "<html/>", "<!DOCTYPE rss><rss><channel/></rss>"]:
            with self.assertRaises(CatalogueImportError):
                normalize_teamtailor(feed)
        rows = normalize_teamtailor(
            RSS.replace(
                "Six month internship in our marketing team working on research and campaigns.",
                "",
            )
        )
        self.assertEqual(len(rows), 0)
        self.assertEqual(rows.errors[0]["code"], "missing_description")

    def test_workable_multiple_locations_share_identity(self):
        read = Mock(return_value=DESCRIPTION)
        rows = normalize_workable(
            {"jobs": [JOB, dict(JOB, country="United States", city="Boston")]},
            "acme",
            read,
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(rows[0]["location_details"]), 2)
        self.assertEqual(read.call_count, 1)
        self.assertFalse(rows.complete)
        self.assertEqual(rows[0]["contract_type"], "internship")

    def test_workable_detail_failure_does_not_import_listing(self):
        rows = normalize_workable(
            {"jobs": [JOB]},
            "acme",
            Mock(side_effect=CatalogueImportError("upstream_rate_limited")),
        )
        self.assertEqual(len(rows), 0)
        self.assertFalse(rows.complete)
        self.assertEqual(rows.errors[0]["code"], "upstream_rate_limited")
        rows = normalize_workable(
            {"jobs": [JOB]}, "acme", Mock(return_value="<html>" + "Access denied" * 10)
        )
        self.assertEqual(len(rows), 0)

    def test_workable_trainee_not_promoted_and_identity_not_fetchable(self):
        read = Mock(return_value=DESCRIPTION)
        rows = normalize_workable(
            {"jobs": [dict(JOB, title="Management trainee", type="trainee")]},
            "acme",
            read,
        )
        self.assertEqual(len(rows), 0)
        read.assert_not_called()
        with self.assertRaises(CatalogueImportError):
            normalize_workable(
                {"jobs": [dict(JOB, shortcode="../../other")]}, "acme", read
            )

    def test_source_urls_and_spoofed_hosts(self):
        for url, provider in [
            ("https://acme.teamtailor.com/jobs.rss", "teamtailor"),
            ("https://apply.workable.com/acme/j/ABC123/", "workable"),
        ]:
            self.assertEqual(parse_source_url(url)["provider"], provider)
            self.assertEqual(parse_source_url(url)["board_key"], "acme")
        for url in [
            "https://acme.teamtailor.com.evil.org",
            "https://apply.workable.com/acme?redirect=x",
            "https://apply.workable.com/a/b/c/d",
            "https://user@acme.teamtailor.com",
            "https://acme.teamtailor.com:8080",
        ]:
            with self.assertRaises(CatalogueImportError):
                parse_source_url(url)


class PublicATSImportTests(TestCase):
    def test_partial_sync_is_idempotent_and_keeps_absent_source(self):
        board = SourceBoard.objects.create(
            company=Company.objects.create(name="Acme"),
            provider="teamtailor",
            board_key="acme",
            enabled=True,
        )
        snapshot = normalize_teamtailor(
            RSS.replace(
                "<remoteStatus>fully</remoteStatus>",
                "<remoteStatus>none</remoteStatus>",
            )
        )
        with patch(
            "jobboard.services.catalogue.fetch_normalized", return_value=snapshot
        ):
            import_board(board.pk)
            import_board(board.pk)
        self.assertEqual(OfferSource.objects.filter(board=board).count(), 1)
        with patch(
            "jobboard.services.catalogue.fetch_normalized",
            return_value=normalize_teamtailor("<rss><channel/></rss>"),
        ):
            import_board(board.pk)
        source = OfferSource.objects.get(board=board)
        self.assertEqual(source.source_status, "active")
