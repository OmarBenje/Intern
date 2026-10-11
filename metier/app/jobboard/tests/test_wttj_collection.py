from unittest.mock import patch

from django.test import SimpleTestCase, TestCase

from jobboard.integrations.greenhouse_catalogue import CatalogueImportError
from jobboard.integrations.wttj_catalogue import (
    WttjPage,
    collect,
    company_logo,
    normalize_record,
    source_record,
)
from jobboard.models import DiscoveryQuery, OfferSource
from jobboard.services.wttj_collection import run_queries, seed_queries


def hit(**changes):
    return dict(
        {
            "reference": "ABC",
            "name": "Marketing internship",
            "organization": {"name": "Example", "slug": "example"},
            "slug": "marketing-internship",
            "contract_type": "internship",
            "offices": [{"city": "Paris", "country_code": "FR"}],
            "summary": "A six month internship in our marketing team, working on campaigns and research.",
            "remote": "partial",
        },
        **changes,
    )


class WttjTests(SimpleTestCase):
    def test_source_record_preserves_organization_logo(self):
        raw = source_record(
            hit(
                organization={
                    "name": "Example",
                    "slug": "example",
                    "logo": {"url": "https://cdn.example.com/brand.png"},
                }
            )
        )
        self.assertEqual(raw["company_logo"], "https://cdn.example.com/brand.png")

    def test_brand_lookup_requires_both_slug_and_matching_company(self):
        with patch(
            "jobboard.integrations.wttj_catalogue.query_index",
            return_value={
                "hits": [
                    hit(
                        organization={
                            "name": "Example",
                            "slug": "example",
                            "logo": {"url": "https://cdn.example.com/brand.png"},
                        }
                    )
                ]
            },
        ) as read:
            self.assertEqual(
                company_logo("example", "Example"), "https://cdn.example.com/brand.png"
            )
            self.assertEqual(read.call_args.kwargs["company_slug"], "example")
            with self.assertRaisesMessage(
                CatalogueImportError, "wttj_logo_company_mismatch"
            ):
                company_logo("example", "Different company")
            with self.assertRaisesMessage(
                CatalogueImportError, "wttj_logo_company_mismatch"
            ):
                company_logo("other", "Example")

    def test_normalization_and_strict_scope(self):
        row, facts = normalize_record(source_record(hit()))
        self.assertEqual(facts["classification"], "confirmed")
        self.assertEqual(row["location_details"][0]["country"], "FR")
        self.assertIn("Résumé publié", row["description"])
        for changes in [
            {"contract_type": "apprenticeship"},
            {"offices": [{"city": "Boston", "country_code": "US"}]},
            {"offices": [{"city": "Paris"}]},
            {"remote": "full"},
            {
                "name": "Permanent sales manager",
                "summary": "We are a growing company. Work with our sales department every day.",
            },
        ]:
            self.assertIsNone(normalize_record(source_record(hit(**changes)))[0])

    def test_empty_summary_and_url_injection(self):
        with self.assertRaises(CatalogueImportError):
            normalize_record(source_record(hit(summary="")))
        with self.assertRaises(CatalogueImportError):
            source_record(hit(slug="../secret"))

    def test_partition_keeps_older_timestamps(self):
        with patch(
            "jobboard.integrations.wttj_catalogue.query_index",
            side_effect=[
                {"nbHits": 1200, "hits": [], "page": 0, "exhaustiveNbHits": True},
                {"nbHits": 1, "hits": [hit()], "page": 0, "exhaustiveNbHits": True},
            ],
        ) as read:
            page = collect("FR", "0:100:0")
        self.assertEqual(read.call_args.args, ("FR", 51, 100, 0))
        self.assertEqual(page.next_cursor, "0:50:0")
        self.assertEqual(len(page.records), 1)

    def test_saturated_timestamp_and_malformed_page(self):
        with (
            patch(
                "jobboard.integrations.wttj_catalogue.query_index",
                return_value={
                    "nbHits": 1200,
                    "hits": [],
                    "page": 0,
                    "exhaustiveNbHits": True,
                },
            ),
            self.assertRaisesMessage(CatalogueImportError, "wttj_partition_saturated"),
        ):
            collect("FR", "10:10:0")
        with (
            patch(
                "jobboard.integrations.wttj_catalogue.query_index",
                return_value={
                    "nbHits": 10,
                    "hits": [],
                    "page": 0,
                    "exhaustiveNbHits": True,
                },
            ),
            self.assertRaises(CatalogueImportError),
        ):
            collect("FR")


class WttjWorkerTests(TestCase):
    def test_worker_import_cursor_and_retry(self):
        seed_queries(["FR"])
        q = DiscoveryQuery.objects.get(provider="wttj")
        with patch(
            "jobboard.services.wttj_collection.collect",
            return_value=WttjPage([source_record(hit())], "0:50:0", 1),
        ):
            self.assertEqual(run_queries()[0]["imported"], 1)
        q.refresh_from_db()
        self.assertEqual(q.cursor, "0:50:0")
        self.assertEqual(OfferSource.objects.get().board.provider, "wttj")
        from django.utils import timezone

        DiscoveryQuery.objects.filter(pk=q.pk).update(next_run_at=timezone.now())
        with patch(
            "jobboard.services.wttj_collection.collect",
            side_effect=CatalogueImportError("wttj_http_error"),
        ):
            run_queries()
        q.refresh_from_db()
        self.assertEqual(q.cursor, "0:50:0")
        self.assertIsNone(q.lease_token)
