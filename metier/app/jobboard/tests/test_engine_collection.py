from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from jobboard.integrations.greenhouse_catalogue import CatalogueImportError
from jobboard.integrations.public_catalogue import (
    fetch_normalized,
    normalize_ashby,
    normalize_lever,
)
from jobboard.models import (
    BoardSchedule,
    Company,
    ImportRun,
    OfferSource,
    OutboxMessage,
    SourceBoard,
    SourceObservation,
    SourceRevision,
)
from jobboard.services.catalogue import import_board
from jobboard.services.engine_collection import (
    process_one,
    register_source,
    schedule_due,
)

from .test_imports import snapshot


class ConnectorTests(SimpleTestCase):
    def test_ashby_multilocation_and_unlisted(self):
        job = {
            "title": "Stage droit",
            "descriptionPlain": "Six mois",
            "jobUrl": "https://jobs.ashbyhq.com/acme/a",
            "applyUrl": "https://jobs.ashbyhq.com/acme/a/application",
            "location": "Paris",
            "secondaryLocations": [{"location": "Berlin"}],
        }
        result = normalize_ashby({"jobs": [job, dict(job, isListed=False)]})
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["locations"], ["Paris", "Berlin"])
        self.assertEqual(result[0]["external_id"], "a")

    def test_lever_pagination_exhaustion_and_duplicates(self):
        row = {
            "id": "abc",
            "text": "Praktikum",
            "descriptionPlain": "Test",
            "hostedUrl": "https://jobs.lever.co/acme/abc",
            "categories": {"allLocations": ["Berlin", "Paris"]},
        }
        self.assertEqual(normalize_lever([row])[0]["locations"], ["Berlin", "Paris"])
        with self.assertRaises(CatalogueImportError):
            normalize_lever([row, row])
        with patch(
            "jobboard.integrations.public_catalogue.read_json",
            side_effect=[[dict(row, id=str(n)) for n in range(100)], []],
        ) as read:
            self.assertEqual(
                len(
                    fetch_normalized(
                        SimpleNamespace(
                            provider="lever", instance="eu", board_key="acme"
                        )
                    )
                ),
                100,
            )
            self.assertIn("api.eu.lever.co", read.call_args.args[0])
            self.assertIn("skip=100", read.call_args.args[0])

    def test_bad_board_and_source_urls_never_fetch(self):
        with patch("jobboard.integrations.public_catalogue.read_json") as read:
            with self.assertRaises(CatalogueImportError):
                fetch_normalized(
                    SimpleNamespace(
                        provider="ashby", instance="global", board_key="../private"
                    )
                )
            for url in [
                "http://localhost/a",
                "https://jobs.lever.co.evil/a",
                "https://jobs.lever.co/a?token=x",
                "https://jobs.lever.co/a/job",
            ]:
                with self.assertRaises(CatalogueImportError):
                    register_source(url, "Acme")
            read.assert_not_called()


class CollectionTests(TestCase):
    def setUp(self):
        self.board = SourceBoard.objects.create(
            provider="greenhouse",
            board_key="acme",
            company=Company.objects.create(name="Acme"),
            base_url="https://boards.greenhouse.io/acme",
        )

    def sync(self, payload):
        with patch("jobboard.services.catalogue.fetch_snapshot", return_value=payload):
            return import_board(self.board.pk)

    def test_greenhouse_office_address_preserves_country_without_name_inference(self):
        data = snapshot(1, 2, 3)
        data["jobs"][0]["location"] = {"name": "London; Dublin"}
        data["jobs"][0]["offices"] = [
            {"name": "GB-London", "location": "London, England, United Kingdom"},
            {"name": "IE-Dublin", "location": "Dublin, Dublin, Ireland"},
        ]
        data["jobs"][1]["offices"] = [{"name": "FR-Paris", "location": "Paris"}]
        self.sync(data)
        offer = OfferSource.objects.get(external_id="1").offer
        self.assertEqual(offer.enrichment.country_codes, ["GB", "IE"])
        self.assertEqual(offer.enrichment.europe_status, "in_scope")
        self.assertTrue(offer.locations.filter(name="London; Dublin").exists())
        self.assertTrue(offer.locations.filter(country_code="GB").exists())
        self.assertTrue(offer.locations.filter(country_code="IE").exists())
        data["jobs"][0]["location"] = {"name": "Remote"}
        self.sync(data)
        offer.refresh_from_db()
        self.assertEqual(offer.work_mode, "remote")
        self.assertEqual(offer.enrichment.europe_status, "unknown")
        for identity in ("2", "3"):
            unknown = OfferSource.objects.get(external_id=identity).offer
            self.assertEqual(unknown.enrichment.country_codes, [])
            self.assertEqual(unknown.enrichment.europe_status, "unknown")
            self.assertFalse(unknown.locations.exclude(country_code=None).exists())

    def test_greenhouse_same_city_different_country_does_not_corroborate(self):
        from jobboard.integrations.greenhouse_catalogue import normalize_snapshot

        data = snapshot(1)
        data["jobs"][0]["location"] = {"name": "London, Ontario, Canada"}
        data["jobs"][0]["offices"] = [
            {"name": "London", "location": "London, United Kingdom"}
        ]
        details = normalize_snapshot(data)[0]["location_details"]
        self.assertEqual(details, [{"name": "London, Ontario, Canada", "country": ""}])

    def test_greenhouse_shared_offices_do_not_widen_job_location(self):
        data = snapshot(1, 2, 3)
        offices = [
            {"name": "Amsterdam", "location": "Amsterdam, Netherlands"},
            {"name": "Chicago", "location": "Chicago, United States"},
            {"name": "Sydney", "location": "Sydney,  Australia"},
        ]
        for job, city in zip(
            data["jobs"],
            ["Sydney,  Australia", "Chicago, United States", "Amsterdam, Netherlands"],
            strict=True,
        ):
            job["location"] = {"name": city}
            job["offices"] = offices
        self.sync(data)
        for identity, code, scope in [
            ("1", "AU", "out_of_scope"),
            ("2", "US", "out_of_scope"),
            ("3", "NL", "in_scope"),
        ]:
            offer = OfferSource.objects.get(external_id=identity).offer
            self.assertEqual(offer.enrichment.country_codes, [code])
            self.assertEqual(offer.enrichment.europe_status, scope)
        # Reimport repairs previously incorrect links for a single-source offer.
        offer = OfferSource.objects.get(external_id="1").offer
        dutch = (
            OfferSource.objects.get(external_id="3")
            .offer.locations.filter(country_code="NL")
            .get()
        )
        offer.locations.add(dutch)
        self.sync(data)
        self.assertFalse(offer.locations.filter(country_code="NL").exists())
        offer.refresh_from_db()
        self.assertEqual(offer.enrichment.country_codes, ["AU"])

    def test_ashby_structured_countries_and_contract_survive_import(self):
        self.board.provider = "ashby"
        self.board.save()
        job = {
            "title": "Campaign & CRM Intern",
            "descriptionPlain": "Work with the marketing team.",
            "jobUrl": "https://jobs.ashbyhq.com/acme/a",
            "employmentType": "Intern",
            "location": "Paris",
            "address": {"postalAddress": {"addressCountry": "France"}},
            "secondaryLocations": [
                {
                    "location": "Barcelona",
                    "address": {"postalAddress": {"addressCountry": "Spain"}},
                }
            ],
        }
        with patch(
            "jobboard.integrations.public_catalogue.read_json",
            return_value={"jobs": [job]},
        ):
            import_board(self.board.pk)
        source = OfferSource.objects.get(board=self.board)
        self.assertEqual(
            set(source.offer.locations.values_list("name", "country_code")),
            {("Paris", "FR"), ("Barcelona", "ES")},
        )
        self.assertEqual(source.offer.contract_type, "internship")
        self.assertEqual(source.offer.enrichment.classification, "confirmed")
        self.assertEqual(source.offer.enrichment.country_codes, ["ES", "FR"])
        self.assertEqual(source.offer.enrichment.europe_status, "in_scope")
        job["isRemote"] = True
        with patch(
            "jobboard.integrations.public_catalogue.read_json",
            return_value={"jobs": [job]},
        ):
            import_board(self.board.pk)
        source.refresh_from_db()
        self.assertEqual(source.offer.enrichment.europe_status, "unknown")

    def test_revisions_idempotent_immutable_and_semantic_hash(self):
        data = snapshot(1)
        self.sync(data)
        self.sync(data)
        self.assertEqual(SourceRevision.objects.count(), 1)
        data["jobs"][0]["updated_at"] = "technical timestamp"
        self.sync(data)
        self.assertEqual(SourceRevision.objects.count(), 2)
        self.assertEqual(
            len(set(SourceRevision.objects.values_list("semantic_hash", flat=True))), 1
        )
        revision = SourceRevision.objects.first()
        with self.assertRaises(ValueError):
            revision.save()

    def test_confirmed_absence_and_reappearance(self):
        self.sync(snapshot(1, 2))
        self.sync(snapshot(1))
        absent = OfferSource.objects.get(external_id="2")
        self.assertEqual(absent.source_status, "missing")
        self.assertEqual(absent.offer.status, "open")
        self.sync(snapshot(1))
        absent.refresh_from_db()
        self.assertEqual(absent.source_status, "missing")
        SourceObservation.objects.filter(source=absent).update(
            missing_since=timezone.now() - timedelta(hours=7)
        )
        self.sync(snapshot(1))
        absent.refresh_from_db()
        self.assertEqual(absent.source_status, "closed")
        self.assertEqual(absent.offer.status, "closed")
        self.sync(snapshot(1, 2))
        absent.refresh_from_db()
        self.assertEqual(absent.source_status, "active")
        self.assertEqual(absent.offer.status, "open")
        self.assertEqual(absent.observation.missing_count, 0)

    def test_empty_and_large_drop_quarantined(self):
        self.sync(snapshot(*range(1, 21)))
        run = self.sync(snapshot(1))
        self.assertEqual(run.error_code, "snapshot_quarantined")
        self.assertEqual(OfferSource.objects.filter(source_status="active").count(), 20)

    def test_lease_fencing_busy_and_stolen(self):
        self.sync(snapshot(1))
        BoardSchedule.objects.filter(board=self.board).update(
            lease_expires_at=timezone.now() + timedelta(minutes=1)
        )
        with self.assertRaisesMessage(CatalogueImportError, "board_busy"):
            self.sync(snapshot(2))
        BoardSchedule.objects.filter(board=self.board).update(lease_expires_at=None)

        def steal(_):
            import uuid

            BoardSchedule.objects.filter(board=self.board).update(
                lease_token=uuid.uuid4()
            )
            return snapshot(2)

        with (
            patch("jobboard.services.catalogue.fetch_snapshot", side_effect=steal),
            self.assertRaisesMessage(CatalogueImportError, "lease_lost"),
        ):
            import_board(self.board.pk)
        self.assertEqual(OfferSource.objects.get().external_id, "1")

    def test_backoff_and_isolated_outbox(self):
        schedule_due()
        schedule_due()
        self.assertEqual(OutboxMessage.objects.filter(topic="board.sync").count(), 1)
        untouched = OutboxMessage.objects.create(
            topic="application.submit", dedupe_key="untouched", payload={}
        )
        with patch(
            "jobboard.services.catalogue.fetch_snapshot",
            side_effect=CatalogueImportError("timeout"),
        ):
            self.assertTrue(process_one())
        schedule = BoardSchedule.objects.get(board=self.board)
        self.assertEqual(schedule.failure_count, 1)
        self.assertGreater(schedule.next_run_at, timezone.now())
        untouched.refresh_from_db()
        self.assertIsNone(untouched.processed_at)
        self.assertEqual(ImportRun.objects.get().error_code, "timeout")


class MergeTests(TestCase):
    def test_exact_merge_reverse_and_no_title_only_merge(self):
        from jobboard.models import Offer, OfferMergeDecision
        from jobboard.services.engine_merges import merge, propose_merges, reverse_merge

        company = Company.objects.create(name="Acme")
        boards = [
            SourceBoard.objects.create(
                provider="greenhouse",
                board_key=key,
                company=company,
                base_url="https://boards.greenhouse.io/" + key,
            )
            for key in ["one", "two"]
        ]
        offers = [
            Offer.objects.create(company=company, title="Intern", description="Same")
            for _ in range(2)
        ]
        sources = [
            OfferSource.objects.create(
                offer=offer,
                board=board,
                external_id="1",
                origin_url="https://employer.example/jobs/1",
                apply_url="https://employer.example/jobs/1",
                content_hash="a" * 64,
            )
            for board, offer in zip(boards, offers, strict=True)
        ]
        # No candidates in first batch: its limit must still stop scanning.
        self.assertEqual(propose_merges(limit=1), 0)
        self.assertEqual(propose_merges(limit=1, after_source_id=sources[0].pk), 1)
        decision = OfferMergeDecision.objects.get()
        merge(decision.pk)
        sources[1].refresh_from_db()
        offers[1].refresh_from_db()
        self.assertEqual(sources[1].offer_id, offers[0].pk)
        self.assertEqual(offers[1].status, "hidden")
        reverse_merge(decision.pk)
        sources[1].refresh_from_db()
        self.assertEqual(sources[1].offer_id, offers[1].pk)
        sources[1].origin_url = "https://employer.example/jobs/different"
        sources[1].save()
        self.assertEqual(propose_merges(), 0)
