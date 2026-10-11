"""Reproducible local catalogue API/SQL measurements, without modifying the corpus."""

import json
import math
import statistics
import time

from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.test import Client, RequestFactory, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.request import Request

from jobboard.api.catalogue import filtered_offers, list_offers, open_offers
from jobboard.models import Offer


class Command(BaseCommand):
    help = "Read-only local catalogue benchmark: warm API median/p95, SQL count, optional EXPLAIN."

    def add_arguments(self, parser):
        parser.add_argument("--query", action="append", dest="queries")
        parser.add_argument("--samples", type=int, default=10)
        parser.add_argument("--page-size", type=int, default=36)
        parser.add_argument("--explain", action="store_true")

    def handle(self, *args, **options):
        if not 3 <= options["samples"] <= 50:
            raise CommandError("samples must be between 3 and 50.")
        if not 1 <= options["page_size"] <= 100:
            raise CommandError("page-size must be between 1 and 100.")
        queries = options["queries"] or [
            "",
            "Python",
            "stage développeur",
            "Bosch software",
            "C++",
            "développement",
        ]
        if len(queries) > 20 or any(len(query) > 300 for query in queries):
            raise CommandError(
                "At most 20 queries, each no longer than 300 characters."
            )
        report = {
            "measured_at": timezone.now().isoformat(),
            "environment": "local Django test client + PostgreSQL; no network or concurrent-load simulation",
            "offers": Offer.objects.count(),
            "public_offers": open_offers().count(),
            "samples_per_query": options["samples"],
            "warmup_per_query": 1,
            "page_size": options["page_size"],
            "queries": [],
        }
        client = Client(HTTP_HOST="localhost")
        # Exercise real routing, middleware and serialization without a session.
        with override_settings(ALLOWED_HOSTS=["localhost"], SECURE_SSL_REDIRECT=False):
            for query in queries:
                parameters = {"q": query, "page_size": options["page_size"]}
                timings, sql_counts = [], []
                for iteration in range(options["samples"] + 1):
                    start = time.perf_counter()
                    with CaptureQueriesContext(connection) as captured:
                        response = client.get("/api/v1/offers/", parameters)
                    elapsed = (time.perf_counter() - start) * 1000
                    if response.status_code != 200:
                        raise CommandError(
                            f"Catalogue returned HTTP {response.status_code}."
                        )
                    if iteration:
                        timings.append(round(elapsed, 2))
                        sql_counts.append(len(captured))
                measurement = {
                    "q": query,
                    "count": response.json()["count"],
                    "median_ms": round(statistics.median(timings), 2),
                    "p95_ms": sorted(timings)[math.ceil(len(timings) * 0.95) - 1],
                    "samples_ms": timings,
                    "sql_queries_min": min(sql_counts),
                    "sql_queries_max": max(sql_counts),
                }
                if options["explain"]:
                    request = Request(
                        RequestFactory().get("/api/v1/offers/", parameters)
                    )
                    measurement["plan"] = json.loads(
                        list_offers(filtered_offers(request)).explain(
                            analyze=True, buffers=True, format="json"
                        )
                    )
                report["queries"].append(measurement)
        self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))
