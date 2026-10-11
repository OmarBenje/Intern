from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase

from jobboard.integrations.greenhouse_catalogue import CatalogueImportError
from jobboard.integrations.public_catalogue import fetch_normalized
from jobboard.models import Company, OfferSource, SourceBoard, SourceRevision
from jobboard.services.catalogue import import_board
from jobboard.services.engine_collection import register_source


def posting(identity="123", country="fr", contract="intern", remote=False):
    return {
        "id": identity,
        "name": "Stage marketing",
        "location": {"country": country, "city": "Paris", "remote": remote},
        "typeOfEmployment": {"id": contract},
        "visibility": "PUBLIC",
        "ref": "https://evil.invalid/should-not-fetch",
        "postingUrl": f"https://jobs.smartrecruiters.com/Acme/{identity}-stage",
        "applyUrl": f"https://jobs.smartrecruiters.com/Acme/{identity}-stage?oga=true",
        "jobAd": {
            "sections": {
                "jobDescription": {"text": "<p>Stage marketing de six mois.</p>"}
            }
        },
    }


def listing(*jobs, total=None, offset=0):
    return {
        "content": list(jobs),
        "totalFound": len(jobs) if total is None else total,
        "offset": offset,
    }


class SmartRecruitersTests(SimpleTestCase):
    board = SimpleNamespace(
        provider="smartrecruiters", instance="global", board_key="Acme"
    )

    def test_scope_and_fixed_detail_host(self):
        wanted = posting()
        wanted["jobAd"]["sections"]["videos"] = {
            "title": "Videos",
            "urls": ["https://example.org/video"],
        }
        with patch(
            "jobboard.integrations.public_catalogue.read_json",
            side_effect=[
                listing(
                    wanted,
                    posting("2", "us"),
                    dict(posting("3", contract="permanent"), name="Marketing manager"),
                    posting("4", remote=True),
                ),
                wanted,
            ],
        ) as read:
            result = fetch_normalized(self.board)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["contract_type"], "internship")
        self.assertEqual(
            result[0]["location_details"], [{"name": "Paris", "country": "FR"}]
        )
        self.assertEqual(read.call_count, 2)
        self.assertEqual(
            read.call_args.args[0],
            "https://api.smartrecruiters.com/v1/companies/Acme/postings/123",
        )

    def test_title_stage_requires_confirmation_without_coercing_contract(self):
        genuine = posting(contract="permanent")
        genuine["jobAd"]["sections"]["jobDescription"]["text"] = (
            "Nous recherchons un stagiaire en marketing."
        )
        manager = dict(posting("2", contract="permanent"), name="Stage Manager")
        ambiguous = dict(posting("3", contract="permanent"), name="Stage marketing")
        ambiguous["jobAd"]["sections"]["jobDescription"]["text"] = (
            "Join the marketing team."
        )
        with patch(
            "jobboard.integrations.public_catalogue.read_json",
            side_effect=[listing(genuine, manager, ambiguous), genuine, ambiguous],
        ) as read:
            rows = fetch_normalized(self.board)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["external_id"], "123")
        self.assertEqual(rows[0]["contract_type"], "unknown")
        self.assertEqual(read.call_count, 3)

    def test_pagination_uses_actual_offset_and_validates_total(self):
        a, b = posting(), posting("456")
        with patch(
            "jobboard.integrations.public_catalogue.read_json",
            side_effect=[listing(a, total=2), listing(b, total=2, offset=1), a, b],
        ) as read:
            self.assertEqual(len(fetch_normalized(self.board)), 2)
            self.assertIn("offset=1", read.call_args_list[1].args[0])
        for responses, code in [
            ([listing(a, total=2), listing(total=2, offset=1)], "incomplete_snapshot"),
        ]:
            with (
                self.subTest(code=code),
                patch(
                    "jobboard.integrations.public_catalogue.read_json",
                    side_effect=responses,
                ),
                self.assertRaisesMessage(CatalogueImportError, code),
            ):
                fetch_normalized(self.board)

    def test_detail_budget_aborts_snapshot(self):
        with (
            patch(
                "jobboard.integrations.public_catalogue.SMARTRECRUITERS_MAX_DETAILS", 1
            ),
            patch(
                "jobboard.integrations.public_catalogue.read_json",
                return_value=listing(posting(), posting("456")),
            ),
            self.assertRaisesMessage(CatalogueImportError, "incomplete_snapshot"),
        ):
            fetch_normalized(self.board)


class SmartRecruitersImportTests(TestCase):
    def test_register_board_and_job_url_are_idempotent(self):
        first = register_source("https://careers.smartrecruiters.com/Acme", "Acme")
        second = register_source(
            "https://jobs.smartrecruiters.com/Acme/123-stage", "Acme"
        )
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(first.provider, "smartrecruiters")

    def test_import_preserves_scope_and_failure_does_not_close(self):
        board = SourceBoard.objects.create(
            provider="smartrecruiters",
            board_key="Acme",
            company=Company.objects.create(name="Acme"),
            base_url="https://careers.smartrecruiters.com/Acme",
        )
        job = posting()
        for _ in range(2):
            with patch(
                "jobboard.integrations.public_catalogue.read_json",
                side_effect=[listing(job), deepcopy(job)],
            ):
                import_board(board.pk)
        source = OfferSource.objects.get(board=board)
        self.assertEqual(source.offer.enrichment.europe_status, "in_scope")
        self.assertEqual(source.offer.enrichment.classification, "confirmed")
        self.assertEqual(SourceRevision.objects.filter(source=source).count(), 1)
        with (
            patch(
                "jobboard.integrations.public_catalogue.read_json",
                side_effect=[
                    listing(job),
                    CatalogueImportError("upstream_rate_limited"),
                ],
            ),
        ):
            checked = source.last_checked_at
            run = import_board(board.pk)
        self.assertFalse(run.is_full_snapshot)
        self.assertEqual(
            run.diagnostics, [{"external_id": "123", "code": "upstream_rate_limited"}]
        )
        source.refresh_from_db()
        self.assertEqual(source.last_checked_at, checked)
        self.assertEqual(source.source_status, "active")
        self.assertEqual(source.offer.status, "open")
        self.assertEqual(source.observation.missing_count, 0)
