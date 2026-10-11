"""Public BA Jobsuche v6 search/v4 detail. Shared category is not stage proof."""

import base64
import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from datetime import time as daytime
from urllib.parse import quote, urlencode
from zoneinfo import ZoneInfo

import httpx
from django.utils import timezone
from django.utils.dateparse import parse_date

from .greenhouse_catalogue import CatalogueImportError
from .public_catalogue import _posting

BASE = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service"
TERMS = ("Praktikum", "Praktikant", "Internship")
PAGE_SIZE = 20
MAX_PAGE = 500


@dataclass
class BundesagenturPage:
    records: list
    next_cursor: str
    total: int
    truncated: bool = False


def public_url(identity):
    if not isinstance(identity, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_.-]{0,149}", identity
    ):
        raise CatalogueImportError("bundesagentur_invalid_identity")
    return "https://www.arbeitsagentur.de/jobsuche/jobdetail/" + identity


def request_json(path, *, deadline=None):
    deadline = deadline or time.monotonic() + 30
    if time.monotonic() >= deadline:
        raise CatalogueImportError("bundesagentur_deadline")
    try:
        with (
            httpx.Client(
                timeout=min(20, max(1, deadline - time.monotonic())),
                follow_redirects=False,
                trust_env=False,
            ) as client,
            client.stream(
                "GET",
                BASE + path,
                headers={
                    "Accept": "application/json",
                    "X-API-Key": "jobboerse-jobsuche",
                    "User-Agent": "InternCatalogue/1.0",
                },
            ) as response,
        ):
            if response.status_code != 200:
                exc = CatalogueImportError(
                    "bundesagentur_rate_limited"
                    if response.status_code == 429
                    else "bundesagentur_not_found"
                    if response.status_code == 404
                    else "bundesagentur_http_error"
                )
                retry = response.headers.get("Retry-After", "")
                exc.retry_after = min(int(retry), 86400) if retry.isdigit() else None
                raise exc
            data = bytearray()
            for chunk in response.iter_bytes():
                data.extend(chunk)
                if len(data) > 2 * 1024 * 1024:
                    raise CatalogueImportError("bundesagentur_response_too_large")
                if time.monotonic() >= deadline:
                    raise CatalogueImportError("bundesagentur_deadline")
        result = json.loads(data)
        if not isinstance(result, dict):
            raise CatalogueImportError("bundesagentur_invalid_response")
        return result
    except (httpx.HTTPError, ValueError) as exc:
        raise CatalogueImportError("bundesagentur_invalid_response") from exc


def profile_record(identity, detail):
    url = public_url(identity)
    if not isinstance(detail, dict) or detail.get("referenznummer") != identity:
        raise CatalogueImportError("bundesagentur_identity_mismatch")
    places = detail.get("stellenlokationen")
    if not isinstance(places, list) or len(places) > 100:
        raise CatalogueImportError("bundesagentur_invalid_locations")
    locations = []
    for place in places:
        address = place.get("adresse") if isinstance(place, dict) else None
        if not isinstance(address, dict):
            raise CatalogueImportError("bundesagentur_invalid_locations")
        locations.append({"city": address.get("ort"), "country": address.get("land")})
    # Keep posting evidence, excluding named contacts and private contact fields.
    return {
        "id": identity,
        "url": url,
        "company": detail.get("firma"),
        "title": detail.get("stellenangebotsTitel"),
        "description": detail.get("stellenangebotsBeschreibung"),
        "category": detail.get("stellenangebotsart"),
        "locations": locations,
        "publication_window": detail.get("veroeffentlichungszeitraum"),
    }


def collect(term, page=1):
    if term not in TERMS or type(page) is not int or not 1 <= page <= MAX_PAGE:
        raise CatalogueImportError("bundesagentur_invalid_query")
    deadline = time.monotonic() + 240
    payload = request_json(
        "/pc/v6/jobs?"
        + urlencode(
            {
                "angebotsart": 34,
                "was": term,
                "page": page,
                "size": PAGE_SIZE,
            }
        ),
        deadline=deadline,
    )
    total, hits = payload.get("maxErgebnisse"), payload.get("ergebnisliste")
    if (
        type(total) is not int
        or total < 0
        or not isinstance(hits, list)
        or len(hits) > PAGE_SIZE
    ):
        raise CatalogueImportError("bundesagentur_invalid_search")
    if len(hits) < min(PAGE_SIZE, max(0, total - (page - 1) * PAGE_SIZE)):
        raise CatalogueImportError("bundesagentur_incomplete_page")
    records, seen = [], set()
    for hit in hits:
        identity = hit.get("referenznummer") if isinstance(hit, dict) else None
        url = public_url(identity)
        if identity in seen:
            raise CatalogueImportError("bundesagentur_duplicate_page")
        seen.add(identity)
        encoded = quote(base64.b64encode(identity.encode()).decode(), safe="")
        try:
            detail = request_json("/pc/v4/jobdetails/" + encoded, deadline=deadline)
        except CatalogueImportError as exc:
            if exc.code != "bundesagentur_not_found":
                raise
            records.append({"id": identity, "url": url, "error": exc.code})
            continue
        try:
            records.append(profile_record(identity, detail))
        except CatalogueImportError as exc:
            records.append({"id": identity, "url": url, "error": exc.code})
    more = page * PAGE_SIZE < total
    return BundesagenturPage(
        records,
        str(page + 1) if more and page < MAX_PAGE else "",
        total,
        more and page == MAX_PAGE,
    )


def normalize_record(raw, _site=None):
    from jobboard.services.engine_quality import extract_facts, structured_country_code

    if raw.get("error"):
        raise CatalogueImportError(raw["error"])
    url = public_url(raw.get("id"))
    company, title, description = (
        raw.get("company"),
        raw.get("title"),
        raw.get("description"),
    )
    if (
        not isinstance(company, str)
        or not company.strip()
        or len(company) > 240
        or not isinstance(title, str)
        or not isinstance(description, str)
        or not 40 <= len(description.strip()) <= 200000
    ):
        raise CatalogueImportError("bundesagentur_missing_details")
    places = raw.get("locations")
    if not isinstance(places, list) or not places or len(places) > 100:
        raise CatalogueImportError("bundesagentur_invalid_locations")
    locations = []
    for place in places:
        if not isinstance(place, dict):
            raise CatalogueImportError("bundesagentur_invalid_locations")
        country, city = place.get("country") or "", place.get("city") or ""
        if not isinstance(country, str) or not isinstance(city, str):
            raise CatalogueImportError("bundesagentur_invalid_locations")
        code = structured_country_code(
            {"DEUTSCHLAND": "DE", "OESTERREICH": "AT", "SCHWEIZ": "CH"}.get(
                country, country
            )
        )
        locations.append(
            {
                "name": ", ".join(x for x in (city, code) if x) or "Lieu non précisé",
                "country_code": code,
            }
        )
    window = raw.get("publication_window") or {}
    if not isinstance(window, dict):
        raise CatalogueImportError("bundesagentur_invalid_dates")
    expires = None
    for field in ("von", "bis"):
        value = window.get(field)
        if value:
            try:
                day = parse_date(value)
            except (ValueError, TypeError):
                day = None
            if day is None:
                raise CatalogueImportError("bundesagentur_invalid_dates")
            moment = datetime.combine(
                day + (timedelta(days=1) if field == "bis" else timedelta()),
                daytime.min,
                ZoneInfo("Europe/Berlin"),
            )
            if field == "bis":
                expires = moment
                if expires <= timezone.now():
                    raise CatalogueImportError("bundesagentur_expired")
            elif moment > timezone.now():
                raise CatalogueImportError("bundesagentur_not_yet_published")
    # homeofficemoeglich is optional hybrid work, not evidence of full remote.
    mode = (
        "remote"
        if re.search(r"\bremote\b|100\s*%\s*(?:homeoffice|mobil)", title, re.IGNORECASE)
        else "unknown"
    )
    facts = extract_facts(title, description, locations=locations, work_mode=mode)
    if raw.get("category") != "PRAKTIKUM_TRAINEE":
        facts["classification"] = "uncertain"
    if facts["classification"] != "confirmed" or facts["europe_status"] != "in_scope":
        return None, facts
    row = _posting(
        raw, raw["id"], title, description, url, url, [x["name"] for x in locations]
    )
    row.update(
        contract_type="unknown",
        work_mode=mode,
        expires_at=expires,
        location_details=[
            {"name": x["name"], "country": x["country_code"]} for x in locations
        ],
    )
    return row, facts
