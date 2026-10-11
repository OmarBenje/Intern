"""Pinned MIT-licensed tenant inventories, imported as untrusted source candidates."""

import csv
import hashlib
import io
import re
import time

import httpx
from django.utils import timezone

from jobboard.integrations.greenhouse_catalogue import CatalogueImportError
from jobboard.models import DiscoveryQuery, DiscoveryResult
from jobboard.services.engine_collection import parse_source_url, register_source

REVISION = "6b44a1badc9bfbf5cf176f75265cc5729e520e99"
PROVIDERS = (
    "greenhouse",
    "lever",
    "ashby",
    "workday",
    "smartrecruiters",
    "personio",
    "recruitee",
    "teamtailor",
    "workable",
)


def read_inventory(provider):
    if provider not in PROVIDERS:
        raise CatalogueImportError("unsupported_registry_provider")
    url = f"https://raw.githubusercontent.com/kalil0321/ats-scrapers/{REVISION}/ats-companies/{provider}.csv"
    body = bytearray()
    deadline = time.monotonic() + 30
    try:
        with (
            httpx.Client(timeout=10, follow_redirects=False, trust_env=False) as client,
            client.stream("GET", url) as response,
        ):
            if response.status_code != 200:
                raise CatalogueImportError("registry_http_error")
            for chunk in response.iter_bytes():
                body.extend(chunk)
                if len(body) > 4 * 1024 * 1024 or time.monotonic() > deadline:
                    raise CatalogueImportError("registry_budget_exceeded")
        reader = csv.DictReader(io.StringIO(body.decode("utf-8-sig")))
        if not {"name", "url"} <= set(reader.fieldnames or []):
            raise CatalogueImportError("invalid_registry_schema")
        rows = list(reader)
        if len(rows) > 20000:
            raise CatalogueImportError("registry_budget_exceeded")
        return url, hashlib.sha256(body).hexdigest(), rows
    except (httpx.HTTPError, UnicodeError, csv.Error) as exc:
        raise CatalogueImportError("registry_invalid_response") from exc


def import_registry(
    providers=PROVIDERS, limit=500, offset=0, company_pattern="", activate_limit=0
):
    if (
        not 1 <= limit <= 5000
        or offset < 0
        or not 0 <= activate_limit <= 10
        or any(p not in PROVIDERS for p in providers)
    ):
        raise ValueError("invalid_registry_budget")
    pattern = re.compile(company_pattern, re.IGNORECASE) if company_pattern else None
    report = {
        "revision": REVISION,
        "scanned": 0,
        "invalid": 0,
        "registered": 0,
        "activated": 0,
        "failures": [],
        "sources": [],
    }
    eligible_index = 0
    for provider in providers:
        origin, sha, rows = read_inventory(provider)
        query, _ = DiscoveryQuery.objects.get_or_create(
            provider="ats_registry",
            country="",
            language="en",
            domain=provider,
            term=REVISION,
            defaults={"enabled": False},
        )
        for raw in rows:
            report["scanned"] += 1
            name, url = ((raw.get(k) or "").strip() for k in ("name", "url"))
            if pattern and not pattern.search(name):
                continue
            try:
                parsed = parse_source_url(url)
                if parsed["provider"] != provider or not name or len(name) > 240:
                    raise ValueError("registry_provider_mismatch")
            except (ValueError, CatalogueImportError):
                report["invalid"] += 1
                continue
            eligible_index += 1
            if eligible_index <= offset:
                continue
            candidate = register_source(parsed["canonical"], name, enable=False)
            result, _ = DiscoveryResult.objects.update_or_create(
                query=query,
                external_id=hashlib.sha256(parsed["canonical"].encode()).hexdigest(),
                defaults={
                    "source_url": parsed["canonical"],
                    "company_name": name,
                    "candidate": candidate,
                    "payload": {
                        "registry": origin,
                        "sha256": sha,
                        "revision": REVISION,
                        "row": raw,
                    },
                    "attribution": "https://github.com/kalil0321/ats-scrapers",
                    "status": candidate.status,
                    "last_seen_at": timezone.now(),
                },
            )
            report["registered"] += 1
            if report["activated"] < activate_limit and candidate.status != "validated":
                try:
                    candidate = register_source(candidate.url, name, enable=True)
                    report["activated"] += 1
                    result.status = candidate.status
                except CatalogueImportError as exc:
                    result.status, result.error_code = "validation_failed", exc.code
                    report["failures"].append({"url": candidate.url, "code": exc.code})
                    # An attempted activation consumes the network budget too.
                    activate_limit -= 1
                result.last_attempt_at = timezone.now()
                result.save(update_fields=["status", "error_code", "last_attempt_at"])
            report["sources"].append(
                {"company": name, "url": candidate.url, "status": result.status}
            )
            if report["registered"] >= limit:
                report["next_offset"] = eligible_index
                return report
    report["next_offset"] = None
    return report
