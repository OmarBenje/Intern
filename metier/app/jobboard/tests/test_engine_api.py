from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.utils import timezone

from jobboard import models as m
from jobboard.services.engine_alerts import run_alerts
from jobboard.services.engine_external import process_external_opportunities
from jobboard.tests.engine_fixtures import publishable


class EngineAPITests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="engine-user")
        self.other = get_user_model().objects.create_user(username="engine-other")
        self.client.force_login(self.user)
        self.company = m.Company.objects.create(name="Example")
        self.offer = m.Offer.objects.create(company=self.company, title="Intern")

    def test_search_validation_ownership_and_baseline(self):
        url = "/api/v1/saved-searches/"
        response = self.client.post(
            url,
            {
                "name": "Europe",
                "criteria": {"country_codes": ["FR"]},
                "frequency": "daily",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        item = response.json()
        self.assertIsNotNone(item["last_evaluated_at"])
        self.assertEqual(
            self.client.patch(
                f"{url}{item['id']}/",
                {"criteria": {"arbitrary": "field"}},
                content_type="application/json",
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.patch(
                f"{url}{item['id']}/",
                {"name": "France"},
                content_type="application/json",
            ).json()["version"],
            2,
        )
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(f"{url}{item['id']}/").status_code, 404)
        self.assertEqual(self.client.delete(f"{url}{item['id']}/").status_code, 404)
        self.assertEqual(
            self.client.post(
                url,
                {"name": "x", "user": self.user.pk},
                content_type="application/json",
            ).status_code,
            400,
        )

    def test_private_auth_and_csrf(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.get("/api/v1/saved-searches/").status_code, 401)
        client.force_login(self.user)
        self.assertEqual(
            client.post(
                "/api/v1/saved-searches/",
                {"name": "x"},
                content_type="application/json",
            ).status_code,
            403,
        )

    def test_feedback_idempotent_and_closed_public_detail(self):
        publishable(self.offer)
        url = f"/api/v1/offers/{self.offer.pk}/feedback/"
        for _ in range(2):
            self.assertEqual(
                self.client.put(
                    url, {"reason": "not_interested"}, content_type="application/json"
                ).status_code,
                200,
            )
        self.assertEqual(m.OfferFeedback.objects.count(), 1)
        self.assertEqual(self.client.delete(url).status_code, 200)
        self.offer.status = "closed"
        self.offer.save()
        self.client.logout()
        self.assertEqual(
            self.client.get(f"/api/v1/offers/{self.offer.pk}/").status_code, 200
        )
        self.offer.status = "hidden"
        self.offer.save()
        self.assertEqual(
            self.client.get(f"/api/v1/offers/{self.offer.pk}/").status_code, 404
        )

    def test_url_unsupported_preserved_without_network(self):
        response = self.client.post(
            "/api/v1/external-opportunities/",
            {"url": "https://example.com/career", "title": "My stage"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 202)
        with patch("jobboard.services.engine_external.fetch_normalized") as fetch:
            self.assertEqual(process_external_opportunities(), 1)
            fetch.assert_not_called()
        item = m.ExternalOpportunity.objects.get(pk=response.json()["id"])
        self.assertEqual(
            (item.title, item.status, item.error_code),
            ("My stage", "failed", "unsupported_source"),
        )
        self.client.force_login(self.other)
        self.assertEqual(
            self.client.get(f"/api/v1/external-opportunities/{item.pk}/").status_code,
            404,
        )

    def test_ats_extraction_private(self):
        item = m.ExternalOpportunity.objects.create(
            user=self.user, url="https://jobs.lever.co/example/abc-123"
        )
        with patch(
            "jobboard.services.engine_external.fetch_normalized",
            return_value=[
                {
                    "external_id": "abc-123",
                    "title": "Summer Intern",
                    "description": "Six months",
                }
            ],
        ) as fetch:
            process_external_opportunities()
            self.assertEqual(fetch.call_args.args[0].board_key, "example")
        item.refresh_from_db()
        self.assertEqual(item.status, "ready")
        self.assertEqual(item.title, "Summer Intern")
        self.assertIsNone(item.offer_id)
        self.assertEqual(m.Offer.objects.count(), 1)

    def test_alert_baseline_then_idempotent(self):
        publishable(self.offer)
        search = m.SavedSearch.objects.create(
            user=self.user, name="All", frequency="daily"
        )
        self.assertEqual(run_alerts(), 0)
        search.refresh_from_db()
        self.assertIsNotNone(search.last_evaluated_at)
        search.last_evaluated_at = timezone.now() - timedelta(days=2)
        search.save()
        board = m.SourceBoard.objects.create(
            company=self.company, provider="greenhouse", board_key="example"
        )
        m.OfferSource.objects.create(
            offer=self.offer,
            board=board,
            external_id="123",
            origin_url="https://example.com/job",
            apply_url="https://example.com/job",
            last_checked_at=timezone.now(),
            content_hash="a" * 64,
        )
        self.assertEqual(run_alerts(), 1)
        search.last_evaluated_at = timezone.now() - timedelta(days=2)
        search.save()
        self.assertEqual(run_alerts(), 0)

    def test_semantic_event_baseline_replay_and_changes(self):
        now = timezone.now()
        enrichment = m.OfferEnrichment.objects.create(
            offer=self.offer,
            classification="confirmed",
            europe_status="in_scope",
            event_at=now - timedelta(days=5),
        )
        m.Offer.objects.filter(pk=self.offer.pk).update(
            created_at=now - timedelta(days=5)
        )
        search = m.SavedSearch.objects.create(
            user=self.user,
            name="All",
            frequency="daily",
            last_evaluated_at=now - timedelta(days=2),
        )
        board = m.SourceBoard.objects.create(
            company=self.company, provider="greenhouse", board_key="events"
        )
        m.OfferSource.objects.create(
            offer=self.offer,
            board=board,
            external_id="123",
            origin_url="https://example.com/job",
            apply_url="https://example.com/job",
            last_checked_at=now,
            content_hash="a" * 64,
        )
        self.assertEqual(run_alerts(), 0)
        enrichment.content_version = 2
        enrichment.event_at = timezone.now()
        enrichment.save()
        search.last_evaluated_at = now - timedelta(days=2)
        search.save()
        self.assertEqual(run_alerts(), 1)
        search.last_evaluated_at = now - timedelta(days=2)
        search.save()
        self.assertEqual(run_alerts(), 0)

    def test_stale_offer_never_alerts(self):
        m.SavedSearch.objects.create(
            user=self.user,
            name="All",
            frequency="daily",
            last_evaluated_at=timezone.now() - timedelta(days=2),
        )
        board = m.SourceBoard.objects.create(
            company=self.company, provider="greenhouse", board_key="stale"
        )
        m.OfferSource.objects.create(
            offer=self.offer,
            board=board,
            external_id="123",
            origin_url="https://example.com/job",
            apply_url="https://example.com/job",
            last_checked_at=timezone.now() - timedelta(days=3),
            content_hash="a" * 64,
        )
        self.assertEqual(run_alerts(), 0)

    def test_coverage_uses_enrichment_countries(self):
        m.OfferEnrichment.objects.create(
            offer=self.offer,
            country_codes=["FR"],
            europe_status="in_scope",
            classification="confirmed",
        )
        publishable(self.offer)
        location = m.Location.objects.create(name="Paris", canonical_key="paris")
        self.offer.locations.add(location)
        self.client.logout()
        response = self.client.get("/api/v1/coverage/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            {"locations__country_code": "FR", "offers": 1}, response.json()["countries"]
        )

    def test_merged_alias_keeps_public_identifier(self):
        publishable(self.offer)
        duplicate = m.Offer.objects.create(
            company=self.company, title="Duplicate", status="hidden"
        )
        decision = m.OfferMergeDecision.objects.create(
            canonical_offer=self.offer, duplicate_offer=duplicate, status="merged"
        )
        self.client.logout()
        response = self.client.get(f"/api/v1/offers/{duplicate.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], self.offer.pk)
        self.assertEqual(response.json()["redirected_from_offer_id"], duplicate.pk)
        decision.status = "reversed"
        decision.save()
        self.assertEqual(
            self.client.get(f"/api/v1/offers/{duplicate.pk}/").status_code, 404
        )

    def test_catalogue_typed_filters_and_unknowns(self):
        m.OfferEnrichment.objects.create(
            offer=self.offer,
            country_codes=["FR"],
            classification="confirmed",
            europe_status="in_scope",
            facts={
                "duration": {"value": {"minimum": 2, "maximum": 2, "unit": "weeks"}},
                "start_date": {"value": "2027-06-01"},
                "required_languages": {"value": [{"code": "fr"}]},
            },
        )
        unknown = m.Offer.objects.create(
            company=self.company,
            title="English description, language unspecified",
            language_code="en",
        )

        publishable(self.offer)
        publishable(unknown)
        m.OfferEnrichment.objects.filter(offer=unknown).update(country_codes=["DE"])

        def ids(query):
            response = self.client.get("/api/v1/offers/?" + query)
            self.assertEqual(response.status_code, 200, response.content)
            return {row["id"] for row in response.json()["results"]}

        self.assertEqual(
            ids(
                "duration_min=14&duration_max=14&duration_unit=days&include_unknown=false"
            ),
            {self.offer.pk},
        )
        self.assertEqual(
            ids("duration_min=15&duration_unit=days&include_unknown=false"), set()
        )
        self.assertEqual(
            ids("duration_min=1&duration_unit=months&include_unknown=true"),
            {self.offer.pk, unknown.pk},
        )
        self.assertEqual(
            ids("duration_min=1&duration_unit=months&include_unknown=false"), set()
        )
        self.assertEqual(ids("required_language=en&include_unknown=false"), set())
        self.assertEqual(
            ids("required_language=fr&include_unknown=false"), {self.offer.pk}
        )
        self.assertEqual(
            ids("start_from=2027-07-01&include_unknown=true"), {unknown.pk}
        )
        self.assertEqual(
            ids("start_to=2027-06-01&include_unknown=false"), {self.offer.pk}
        )
        self.assertEqual(ids("country=FR&include_unknown=false"), {self.offer.pk})
        for query in [
            "duration_min=1",
            "duration_min=3&duration_max=2&duration_unit=weeks",
            "start_from=2027-02-30",
            "start_from=2027-07-01&start_to=2027-06-01",
            "include_unknown=maybe",
            "freshness=yesterday",
        ]:
            self.assertEqual(
                self.client.get("/api/v1/offers/?" + query).status_code, 400
            )

    def test_freshness_respects_source_cadence(self):
        board = m.SourceBoard.objects.create(
            company=self.company, provider="greenhouse", board_key="weekly"
        )
        m.BoardSchedule.objects.create(board=board, interval_minutes=1440)
        m.OfferSource.objects.create(
            offer=self.offer,
            board=board,
            external_id="123",
            origin_url="https://example.com/job",
            apply_url="https://example.com/job",
            last_checked_at=timezone.now() - timedelta(hours=30),
            content_hash="a" * 64,
        )
        publishable(self.offer)
        response = self.client.get("/api/v1/offers/?freshness=fresh")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["count"], 1)
        self.assertFalse(response.json()["results"][0]["stale"])
        self.assertEqual(
            self.client.get("/api/v1/offers/?freshness=stale").json()["count"], 0
        )

    def test_confirmed_classification_is_exact_even_with_unknowns(self):
        m.OfferEnrichment.objects.create(
            offer=self.offer, classification="confirmed", europe_status="in_scope"
        )
        senior = m.Offer.objects.create(
            company=self.company, title="Technical Program Manager"
        )
        m.OfferEnrichment.objects.create(
            offer=senior, classification="uncertain", europe_status="unknown"
        )
        publishable(self.offer)
        response = self.client.get(
            "/api/v1/offers/?classification=confirmed&europe_scope=in_scope&unknown_policy=include"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item["id"] for item in response.json()["results"]], [self.offer.pk]
        )
        response = self.client.get("/api/v1/offers/?classification=uncertain")
        self.assertEqual([item["id"] for item in response.json()["results"]], [])

    def test_publication_boundary_cannot_be_relaxed_and_history_stays_private(self):
        publishable(self.offer)
        profile, _ = m.CandidateProfile.objects.get_or_create(
            user=self.user, defaults={"full_name": "Example"}
        )
        preference, _ = m.SearchPreference.objects.get_or_create(profile=profile)
        m.PreferenceContract.objects.create(preference=preference, value="internship")
        m.PreferenceWorkMode.objects.create(preference=preference, value="remote")
        excluded = []
        for title, classification, scope in [
            ("US Internship", "confirmed", "out_of_scope"),
            ("EU Full Time", "not_internship", "in_scope"),
            ("Unclassified EU Role", "uncertain", "in_scope"),
            ("Unknown Location Internship", "confirmed", "unknown"),
        ]:
            offer = m.Offer.objects.create(company=self.company, title=title)
            publishable(offer)
            m.OfferEnrichment.objects.filter(offer=offer).update(
                classification=classification,
                europe_status=scope,
                country_codes=["US"] if scope == "out_of_scope" else ["FR"],
            )
            excluded.append(offer)
        no_evidence = m.Offer.objects.create(company=self.company, title="No evidence")
        excluded.append(no_evidence)
        stale = m.Offer.objects.create(company=self.company, title="Old EU internship")
        publishable(stale)
        stale.sources.update(last_checked_at=timezone.now() - timedelta(days=10))
        excluded.append(stale)
        for query in [
            "",
            "?include_unknown=true",
            "?unknown_policy=include",
            "?freshness=all",
        ]:
            response = self.client.get("/api/v1/offers/" + query)
            self.assertEqual(response.status_code, 200, response.content)
            self.assertEqual(
                [row["id"] for row in response.json()["results"]], [self.offer.pk]
            )
        for query in [
            "?classification=uncertain",
            "?classification=not_internship",
            "?europe_scope=unknown",
            "?europe_scope=out_of_scope",
            "?freshness=stale",
        ]:
            self.assertEqual(
                self.client.get("/api/v1/offers/" + query).json()["count"], 0
            )
        recommendations = self.client.get(
            "/api/v1/recommendations/?include_unknown=true"
        ).json()
        self.assertEqual(
            [row["offer"]["id"] for row in recommendations["results"]], [self.offer.pk]
        )
        dashboard = self.client.get("/api/v1/dashboard/").json()
        self.assertEqual([row["id"] for row in dashboard["offers"]], [self.offer.pk])
        self.assertEqual(
            self.client.get("/api/v1/coverage/").json()["countries"],
            [{"locations__country_code": "FR", "offers": 1}],
        )
        for offer in excluded[:-1]:
            self.assertEqual(
                self.client.get(f"/api/v1/offers/{offer.pk}/").status_code, 404
            )
        m.SavedOffer.objects.create(user=self.user, offer=excluded[0])
        self.assertEqual(
            [
                row["id"]
                for row in self.client.get("/api/v1/saved-offers/").json()["results"]
            ],
            [excluded[0].pk],
        )
        self.client.logout()
        self.assertEqual(self.client.get("/api/v1/offers/").json()["count"], 1)

    def test_coverage_counts_only_europe_for_mixed_locations(self):
        publishable(self.offer)
        m.OfferEnrichment.objects.filter(offer=self.offer).update(
            country_codes=["FR", "DE", "US", "AU"]
        )
        self.client.logout()
        response = self.client.get("/api/v1/coverage/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            response.json()["countries"],
            [
                {"locations__country_code": "DE", "offers": 1},
                {"locations__country_code": "FR", "offers": 1},
            ],
        )
        detail = self.client.get(f"/api/v1/offers/{self.offer.pk}/").json()
        self.assertEqual(detail["quality"]["country_codes"], ["FR", "DE", "US", "AU"])
