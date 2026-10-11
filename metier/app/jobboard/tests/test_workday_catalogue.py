import json
from unittest.mock import patch

import httpx
from django.test import SimpleTestCase

from jobboard.integrations.greenhouse_catalogue import CatalogueImportError
from jobboard.integrations.workday_catalogue import (
    _country_partitions,
    fetch_workday_snapshot,
    normalize_workday,
    parse_workday_url,
)

HOST = "ag.wd3.myworkdayjobs.com"
KEY = HOST + "/ag/Airbus"
PATH = "/job/Paris/Stage_JR1"


def detail(title="Stage en finance", country="FR", **extra):
    return {
        "jobPostingInfo": {
            "id": "abc",
            "title": title,
            "jobDescription": "<p>Le stagiaire participe pendant 6 mois.</p>",
            "location": "Paris",
            "jobRequisitionLocation": {"country": {"alpha2Code": country}},
            "jobReqId": "JR1",
            "timeType": "Full time",
            "startDate": "2026-09-30",
            **extra,
        }
    }


def normalized(payload):
    return normalize_workday(payload, host=HOST, site="Airbus", path=PATH)


class WorkdayTests(SimpleTestCase):
    def test_registry_url_canonical_and_job_path(self):
        parsed = parse_workday_url(
            "https://" + HOST + "/fr-FR/Airbus" + PATH + "?foo=x"
        )
        self.assertEqual(parsed["board_key"], KEY)
        self.assertEqual(parsed["canonical"], "https://" + HOST + "/en-US/Airbus")

    def test_registry_rejects_arbitrary_hosts_credentials_and_ports(self):
        for url in [
            "http://" + HOST + "/Airbus",
            "https://evil.com/Airbus",
            "https://" + HOST + ".evil.com/Airbus",
            "https://u@" + HOST + "/Airbus",
            "https://" + HOST + ":123/Airbus",
        ]:
            with self.subTest(url=url), self.assertRaises(CatalogueImportError):
                parse_workday_url(url)

    def test_country_ids_discovered_nested_not_hardcoded(self):
        facets = [
            {
                "facetParameter": "locationMainGroup",
                "values": [
                    {
                        "facetParameter": "locationCountry",
                        "values": [
                            {"descriptor": "France", "id": "some_new_employer_id"},
                            {"descriptor": "United States", "id": "usa"},
                        ],
                    }
                ],
            }
        ]
        self.assertEqual(
            _country_partitions(facets),
            [("locationCountry", "some_new_employer_id", "FR")],
        )

    def test_stage_europe_hours_not_contract(self):
        row = normalized(detail())
        self.assertEqual(row["location_details"][0]["country"], "FR")
        self.assertEqual(row["contract_type"], "unknown")
        self.assertEqual(row["description"], "Le stagiaire participe pendant 6 mois.")
        self.assertEqual(row["published_at"], "2026-09-30")
        self.assertNotIn("questionnaireId", row["raw"]["jobPostingInfo"])

    def test_nonintern_non_europe_remote_and_closed_excluded(self):
        for payload in [
            detail(title="Finance Manager"),
            detail(country="US"),
            detail(location="Remote, France"),
            detail(canApply=False),
            detail(title="Stage Manager"),
            detail(title="Apprentice Intern"),
        ]:
            with self.subTest(payload=payload):
                self.assertIsNone(normalized(payload))

    def _fetch(self, handler):
        client = httpx.Client(transport=httpx.MockTransport(handler))
        with patch(
            "jobboard.integrations.workday_catalogue.httpx.Client", return_value=client
        ):
            return fetch_workday_snapshot(KEY)

    def test_complete_pagination_and_detail_error_is_partial(self):
        offsets = []

        def handler(request):
            if request.method == "POST":
                body = json.loads(request.content)
                if not body["appliedFacets"]:
                    return httpx.Response(
                        200,
                        json={
                            "total": 2000,
                            "jobPostings": [],
                            "facets": [
                                {
                                    "facetParameter": "locationCountry",
                                    "values": [{"descriptor": "France", "id": "fr"}],
                                }
                            ],
                        },
                    )
                offsets.append(body["offset"])
                posts = [
                    {
                        "externalPath": f"/job/Paris/Stage_JR{i}",
                        "title": "Stage finance",
                    }
                    for i in range(body["offset"], min(body["offset"] + 20, 21))
                ]
                return httpx.Response(
                    200,
                    json={
                        "total": 21 if not body["offset"] else 0,
                        "jobPostings": posts,
                    },
                )
            index = int(request.url.path.split("JR")[-1])
            if index == 3:
                return httpx.Response(503)
            return httpx.Response(200, json=detail(jobReqId=f"JR{index}"))

        result = self._fetch(handler)
        self.assertEqual(offsets, [0, 20])
        self.assertEqual(len(result), 20)
        self.assertFalse(result.complete)
        self.assertTrue(result.errors)

    def test_missing_facets_empty_is_partial(self):
        result = self._fetch(
            lambda req: httpx.Response(200, json={"total": 0, "jobPostings": []})
        )
        self.assertEqual(len(result), 0)
        self.assertFalse(result.complete)
        self.assertEqual(result.errors[0]["code"], "country_facets_fallback")

    def test_custom_country_parameter_requires_explicit_label(self):
        facets = [
            {
                "facetParameter": "Custom_Country",
                "descriptor": "Country/Region",
                "values": [{"descriptor": "France", "id": "fr"}],
            }
        ]
        self.assertEqual(_country_partitions(facets), [("Custom_Country", "fr", "FR")])
        facets[0]["descriptor"] = "Job Family"
        self.assertEqual(_country_partitions(facets), [])
        facets[0]["descriptor"] = "Country"
        facets[0]["facetParameter"] = "../unsafe"
        self.assertEqual(_country_partitions(facets), [])

    def test_global_fallback_filters_details_and_reuses_initial_page(self):
        offsets = []

        def handler(request):
            if request.method == "POST":
                body = json.loads(request.content)
                self.assertEqual(body["appliedFacets"], {})
                offsets.append(body["offset"])
                posts = [
                    {
                        "externalPath": f"/job/Paris/Stage_JR{i}",
                        "title": "Stage finance",
                    }
                    for i in range(body["offset"], min(body["offset"] + 20, 21))
                ]
                return httpx.Response(
                    200,
                    json={
                        "total": 21 if not body["offset"] else 0,
                        "jobPostings": posts,
                    },
                )
            i = int(request.url.path.split("JR")[-1])
            return httpx.Response(
                200, json=detail(country="US" if i else "FR", jobReqId=f"JR{i}")
            )

        result = self._fetch(handler)
        self.assertEqual(offsets, [0, 20])
        self.assertEqual(len(result), 1)
        self.assertFalse(result.complete)

    def test_global_fallback_cap_is_explicit(self):
        calls = []

        def handler(request):
            body = json.loads(request.content)
            calls.append(body["offset"])
            return httpx.Response(
                200,
                json={
                    "total": 45 if not body["offset"] else 0,
                    "jobPostings": [
                        {
                            "externalPath": f"/job/Paris/Job_{i}",
                            "title": "Finance Manager",
                        }
                        for i in range(body["offset"], body["offset"] + 20)
                    ],
                },
            )

        with patch("jobboard.integrations.workday_catalogue.FALLBACK_MAX_LISTINGS", 40):
            result = self._fetch(handler)
        self.assertEqual(calls, [0, 20])
        self.assertFalse(result.complete)
        self.assertIn("fallback_listing_cap", [e["code"] for e in result.errors])

    def test_fallback_duplicate_and_rate_limit_stop(self):
        for limited in [False, True]:
            with self.subTest(limited=limited):

                def handler(request, limited=limited):
                    body = json.loads(request.content)
                    if body["offset"] and limited:
                        return httpx.Response(429, headers={"Retry-After": "60"})
                    return httpx.Response(
                        200,
                        json={
                            "total": 40 if not body["offset"] else 0,
                            "jobPostings": [
                                {
                                    "externalPath": f"/job/Paris/Job_{i}",
                                    "title": "Finance Manager",
                                }
                                for i in range(20)
                            ],
                        },
                    )

                if limited:
                    with self.assertRaises(CatalogueImportError) as caught:
                        self._fetch(handler)
                    self.assertEqual(caught.exception.code, "upstream_rate_limited")
                    self.assertEqual(caught.exception.retry_after, 60)
                else:
                    result = self._fetch(handler)
                    self.assertFalse(result.complete)
                    self.assertIn("duplicate_job", [e["code"] for e in result.errors])

    def test_rate_limit_does_not_follow_or_close(self):
        with self.assertRaisesMessage(CatalogueImportError, "upstream_rate_limited"):
            self._fetch(lambda req: httpx.Response(429, headers={"Retry-After": "60"}))

    def test_capped_country_snapshot_is_partial(self):
        def handler(request):
            body = json.loads(request.content)
            if not body["appliedFacets"]:
                return httpx.Response(
                    200,
                    json={
                        "total": 2000,
                        "jobPostings": [],
                        "facets": [
                            {
                                "facetParameter": "locationCountry",
                                "values": [{"descriptor": "France", "id": "fr"}],
                            }
                        ],
                    },
                )
            return httpx.Response(200, json={"total": 2000, "jobPostings": []})

        result = self._fetch(handler)
        self.assertFalse(result.complete)
        self.assertEqual(result.errors[0]["code"], "upstream_result_cap")
