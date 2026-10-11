from unittest.mock import patch

from django.test import SimpleTestCase, TestCase

from jobboard.integrations.eightfold_catalogue import (
    fetch_eightfold,
    normalize_eightfold,
    parse_eightfold_url,
)
from jobboard.integrations.greenhouse_catalogue import CatalogueImportError
from jobboard.models import Company, OfferSource, SourceBoard
from jobboard.services.catalogue import import_board


def detail(**changes):
    return dict(
        {
            "id": 123,
            "name": "Software Engineer Intern",
            "standardizedLocations": ["Paris, France, FR"],
            "jobDescription": "<p>Six month internship working with our engineering team on software and testing.</p>",
            "workLocationOption": "onsite",
            "displayJobId": "JR456",
        },
        **changes,
    )


class EightfoldTests(SimpleTestCase):
    def test_requests_are_spaced_and_429_is_not_retried(self):
        now = [100.0]
        starts = []

        def sleep(seconds):
            now[0] += seconds

        def read(url, **kwargs):
            starts.append(now[0])
            if len(starts) == 2:
                raise CatalogueImportError("upstream_rate_limited")
            return {"status": 200, "data": {"count": 0, "positions": []}}

        with (
            patch(
                "jobboard.integrations.eightfold_catalogue.time.monotonic",
                side_effect=lambda: now[0],
            ),
            patch(
                "jobboard.integrations.eightfold_catalogue.time.sleep",
                side_effect=sleep,
            ),
            patch(
                "jobboard.integrations.eightfold_catalogue.read_json", side_effect=read
            ),
        ):
            rows = fetch_eightfold("microsoft")
        self.assertEqual(starts, [100.0, 102.0])
        self.assertEqual(rows.errors[0]["code"], "upstream_rate_limited")
        self.assertEqual(rows.checkpoint["term"], 1)

    def test_identity_country_and_full_description(self):
        row = normalize_eightfold(detail(), "nvidia", "123")
        self.assertEqual(row["external_id"], "123")
        self.assertEqual(row["raw"]["displayJobId"], "JR456")
        self.assertEqual(row["location_details"][0]["country"], "FR")
        self.assertEqual(row["url"], "https://jobs.nvidia.com/careers/job/123")
        for changes in [
            {"standardizedLocations": ["Shanghai, China, CN"]},
            {"standardizedLocations": ["Paris"]},
            {"workLocationOption": "remote"},
            {"name": "Working Student Software Engineering"},
        ]:
            self.assertIsNone(normalize_eightfold(detail(**changes), "nvidia", "123"))

    def test_incomplete_or_mismatched_detail_rejected(self):
        for changes in [
            {"id": 456},
            {"jobDescription": ""},
            {"standardizedLocations": "Paris"},
        ]:
            with self.assertRaises(CatalogueImportError):
                normalize_eightfold(detail(**changes), "nvidia", "123")

    def test_source_hosts_and_paths(self):
        self.assertEqual(
            parse_eightfold_url("https://jobs.nvidia.com/careers/job/123")["board_key"],
            "nvidia",
        )
        for url in [
            "https://nvidia.eightfold.ai.evil.org/careers",
            "https://user@nvidia.eightfold.ai/careers",
            "https://nvidia.eightfold.ai/api/pcsx/search",
        ]:
            with self.assertRaises(CatalogueImportError):
                parse_eightfold_url(url)

    def test_dedup_across_terms_and_skip_non_europe(self):
        listing = {
            "status": 200,
            "data": {
                "count": 2,
                "positions": [
                    detail(),
                    detail(id=456, standardizedLocations=["Shanghai, China, CN"]),
                ],
            },
        }

        def read(url, **kwargs):
            return (
                {"status": 200, "data": detail()}
                if "position_details" in url
                else listing
            )

        with patch(
            "jobboard.integrations.eightfold_catalogue.read_json", side_effect=read
        ) as call:
            rows = fetch_eightfold("nvidia")
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows.complete)
        self.assertEqual(
            sum("position_details" in c.args[0] for c in call.call_args_list), 1
        )

    def test_rate_limit_never_means_complete_or_closed(self):
        with patch(
            "jobboard.integrations.eightfold_catalogue.read_json",
            side_effect=[
                {"status": 200, "data": {"count": 1, "positions": [detail()]}},
                CatalogueImportError("upstream_rate_limited"),
            ],
        ):
            rows = fetch_eightfold("nvidia")
        self.assertFalse(rows.complete)
        self.assertEqual(len(rows), 0)
        self.assertEqual(rows.errors[0]["code"], "upstream_rate_limited")


class EightfoldImportTests(TestCase):
    def test_board_is_supported_and_import_is_idempotent(self):
        from jobboard.integrations.public_catalogue import CatalogueSnapshot

        board = SourceBoard.objects.create(
            provider="eightfold",
            board_key="nvidia",
            company=Company.objects.create(name="NVIDIA"),
            enabled=True,
        )
        rows = CatalogueSnapshot(
            [normalize_eightfold(detail(), "nvidia", "123")], complete=False
        )
        with patch("jobboard.services.catalogue.fetch_normalized", return_value=rows):
            import_board(board.pk)
            import_board(board.pk)
        self.assertEqual(OfferSource.objects.filter(board=board).count(), 1)
        from jobboard.api.catalogue import open_offers

        self.assertEqual(open_offers().filter(sources__board=board).count(), 1)
