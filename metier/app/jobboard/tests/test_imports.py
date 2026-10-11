from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from jobboard.integrations.greenhouse_catalogue import (
    CatalogueImportError,
    fetch_snapshot,
    normalize_snapshot,
)
from jobboard.models import Company, ImportRun, Offer, OfferSource, SourceBoard
from jobboard.services.catalogue import import_board


def snapshot(*ids):
    return {
        "meta": {"total": len(ids)},
        "jobs": [
            {
                "id": pk,
                "title": f"Engineer {pk}",
                "content": "&lt;p&gt;Build software&lt;/p&gt;",
                "absolute_url": f"https://boards.greenhouse.io/acme/jobs/{pk}",
                "location": {"name": "Paris"},
            }
            for pk in ids
        ],
    }


class ImportTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Acme")
        self.board = SourceBoard.objects.create(
            provider="greenhouse",
            board_key="acme",
            company=self.company,
            base_url="https://boards.greenhouse.io/acme",
        )

    def run_import(self, payload):
        with patch("jobboard.services.catalogue.fetch_snapshot", return_value=payload):
            return import_board(self.board.pk)

    def test_repeat_import_preserves_identity_and_explicit_unknowns(self):
        self.run_import(snapshot(1, 2))
        before = list(OfferSource.objects.order_by("pk").values_list("pk", "offer_id"))
        self.run_import(snapshot(1, 2))
        self.assertEqual(
            list(OfferSource.objects.order_by("pk").values_list("pk", "offer_id")),
            before,
        )
        self.assertEqual(Offer.objects.count(), 2)
        offer = Offer.objects.first()
        self.assertEqual(offer.contract_type, "unknown")
        self.assertEqual(offer.work_mode, "unknown")
        self.assertIsNone(offer.role_id)
        self.assertEqual(offer.description, "Build software")
        self.assertIsNone(offer.locations.get().country_code)

    def test_complete_snapshot_only_closes_absent_unshared_offers(self):
        self.run_import(snapshot(1, 2))
        first = OfferSource.objects.get(external_id="1")
        other = SourceBoard.objects.create(
            provider="greenhouse",
            board_key="other",
            company=self.company,
            base_url="https://boards.greenhouse.io/other",
        )
        OfferSource.objects.create(
            board=other,
            offer=first.offer,
            external_id="1",
            origin_url=first.origin_url,
            apply_url=first.apply_url,
            content_hash="a" * 64,
        )
        self.run_import(snapshot())
        # An empty board is quarantined before absence confirmation begins.
        self.assertEqual(
            ImportRun.objects.latest("id").error_code, "snapshot_quarantined"
        )
        from jobboard.models import BoardSchedule, SourceObservation

        BoardSchedule.objects.filter(board=self.board).update(
            quarantine_since=timezone.now() - timedelta(hours=7)
        )
        self.run_import(snapshot())
        SourceObservation.objects.filter(source__board=self.board).update(
            missing_since=timezone.now() - timedelta(hours=7)
        )
        self.run_import(snapshot())
        first.offer.refresh_from_db()
        self.assertEqual(first.offer.status, "open")
        self.assertEqual(OfferSource.objects.get(board=other).source_status, "active")
        self.assertEqual(
            OfferSource.objects.get(board=self.board, external_id="2").offer.status,
            "closed",
        )

    def test_invalid_or_incomplete_snapshot_never_closes_or_partially_writes(self):
        self.run_import(snapshot(1))
        invalid = snapshot(2, 3)
        invalid["jobs"][1]["title"] = None
        for payload in [invalid, {"meta": {"total": 2}, "jobs": []}, {"jobs": []}]:
            with self.assertRaises(CatalogueImportError):
                self.run_import(payload)
        self.assertEqual(OfferSource.objects.get().external_id, "1")
        self.assertEqual(Offer.objects.get().status, "open")
        self.assertEqual(ImportRun.objects.filter(status="failed").count(), 3)

    def test_network_failure_keeps_previous_snapshot(self):
        self.run_import(snapshot(1))
        with patch(
            "jobboard.services.catalogue.fetch_snapshot",
            side_effect=CatalogueImportError("timeout"),
        ):
            with self.assertRaises(CatalogueImportError):
                import_board(self.board.pk)
        self.assertEqual(OfferSource.objects.get().source_status, "active")
        self.assertEqual(ImportRun.objects.latest("id").error_code, "timeout")

    def test_atomic_rollback_on_write_failure(self):
        self.run_import(snapshot(1))
        with patch(
            "jobboard.services.catalogue.OfferSource.objects.update_or_create",
            side_effect=RuntimeError("write failure"),
        ):
            with self.assertRaises(RuntimeError):
                self.run_import(snapshot(2))
        self.assertEqual(Offer.objects.count(), 1)
        self.assertEqual(Offer.objects.get().status, "open")

    def test_normalization_rejects_duplicates_and_unsafe_links(self):
        for payload in [snapshot(1, 1), snapshot(True)]:
            with self.assertRaises(CatalogueImportError):
                normalize_snapshot(payload)
        payload = snapshot(1)
        payload["jobs"][0]["absolute_url"] = "javascript:alert(1)"
        with self.assertRaises(CatalogueImportError):
            normalize_snapshot(payload)

    def test_board_path_injection_rejected_before_network(self):
        with patch("jobboard.integrations.greenhouse_catalogue.httpx.Client") as client:
            with self.assertRaises(CatalogueImportError):
                fetch_snapshot("../other?url=http://localhost")
            client.assert_not_called()

    def test_superseded_fetch_cannot_overwrite_newer_success(self):
        self.run_import(snapshot(1))

        def concurrent_fetch(board_key):
            # Another importer finishes while this importer is still fetching.
            from django.utils import timezone

            SourceBoard.objects.filter(pk=self.board.pk).update(
                last_success_at=timezone.now()
            )
            return snapshot(2)

        with patch(
            "jobboard.services.catalogue.fetch_snapshot", side_effect=concurrent_fetch
        ):
            with self.assertRaisesMessage(CatalogueImportError, "superseded_snapshot"):
                import_board(self.board.pk)
        self.assertEqual(OfferSource.objects.get().external_id, "1")

    def test_http_bounds_redirects_and_validation(self):
        import httpx

        for response, expected in [
            (
                httpx.Response(302, headers={"Location": "http://localhost/secret"}),
                "upstream_http_error",
            ),
            (httpx.Response(200, content=b"x" * 51), "response_too_large"),
            (httpx.Response(200, content=b"not json"), "upstream_invalid_response"),
        ]:
            with self.subTest(expected=expected):
                calls = []

                def handler(request):
                    calls.append(request.url)
                    return response

                client = httpx.Client(
                    transport=httpx.MockTransport(handler), follow_redirects=False
                )
                with (
                    patch(
                        "jobboard.integrations.greenhouse_catalogue.httpx.Client",
                        return_value=client,
                    ),
                    patch(
                        "jobboard.integrations.greenhouse_catalogue.MAX_RESPONSE_BYTES",
                        50,
                    ),
                ):
                    with self.assertRaisesMessage(CatalogueImportError, expected):
                        fetch_snapshot("acme")
                self.assertEqual(len(calls), 1)
                self.assertEqual(calls[0].host, "boards-api.greenhouse.io")
