"""Bounded public EURES search/detail reads; no search-country inference."""

import json
import re
import time
from dataclasses import dataclass
from urllib.parse import quote

import httpx

from .greenhouse_catalogue import CatalogueImportError
from .personio_catalogue import html_text
from .public_catalogue import _posting

BASE = "https://europa.eu/eures"
COUNTRIES = frozenset(
    ["AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE", "IS", "LI", "NO", "CH"]
)
PAGE_SIZE = 20
MAX_PAGE = 200


@dataclass
class EuresPage:
    records: list
    next_cursor: str
    total: int
    truncated: bool = False


def public_url(identity):
    if not isinstance(identity, str) or not re.fullmatch(
        r"[A-Za-z0-9_=-]{1,300}", identity
    ):
        raise CatalogueImportError("invalid_eures_identity")
    return f"{BASE}/portal/jv-se/jv-details/{quote(identity, safe='')}?lang=en"


def request_json(path, *, body=None, deadline=None):
    deadline = deadline or time.monotonic() + 30
    if time.monotonic() >= deadline:
        raise CatalogueImportError("eures_deadline")
    try:
        with (
            httpx.Client(
                timeout=min(20, max(1, deadline - time.monotonic())),
                follow_redirects=False,
                trust_env=False,
            ) as client,
            client.stream(
                "POST" if body is not None else "GET",
                BASE + path,
                json=body,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "InternCatalogue/1.0",
                },
            ) as response,
        ):
            if response.status_code != 200:
                exc = CatalogueImportError(
                    "eures_rate_limited"
                    if response.status_code == 429
                    else "eures_not_found"
                    if response.status_code == 404
                    else "eures_http_error"
                )
                retry = response.headers.get("Retry-After", "")
                exc.retry_after = min(int(retry), 86400) if retry.isdigit() else None
                raise exc
            data = bytearray()
            for chunk in response.iter_bytes():
                data.extend(chunk)
                if len(data) > 2 * 1024 * 1024:
                    raise CatalogueImportError("eures_response_too_large")
                if time.monotonic() >= deadline:
                    raise CatalogueImportError("eures_deadline")
        result = json.loads(data)
        if not isinstance(result, dict):
            raise CatalogueImportError("eures_invalid_response")
        return result
    except (httpx.HTTPError, ValueError) as exc:
        raise CatalogueImportError("eures_invalid_response") from exc


def profile_record(listing, detail):
    """Retain only posting evidence, excluding named contacts and contact details."""
    identity = listing.get("id")
    url = public_url(identity)
    if detail.get("id") != identity:
        raise CatalogueImportError("eures_identity_mismatch")
    profiles = detail.get("jvProfiles")
    if not isinstance(profiles, dict) or not profiles:
        raise CatalogueImportError("eures_missing_profile")
    language = detail.get("preferredLanguage")
    profile = profiles.get(language) or next(iter(profiles.values()))
    if not isinstance(profile, dict):
        raise CatalogueImportError("eures_missing_profile")
    employer = profile.get("employer") or {}
    if not isinstance(employer, dict):
        raise CatalogueImportError("eures_missing_employer")
    return {
        "id": identity,
        "url": url,
        "company": employer.get("name"),
        "title": profile.get("title"),
        "description": profile.get("description"),
        "locations": profile.get("locations"),
        "positionOfferingCode": profile.get("positionOfferingCode"),
        "source": detail.get("source"),
        "reference": detail.get("reference"),
        "lastModificationDate": detail.get("lastModificationDate"),
        "language": language,
    }


def collect(country, page=1):
    if country not in COUNTRIES or type(page) is not int or not 1 <= page <= MAX_PAGE:
        raise CatalogueImportError("invalid_eures_query")
    deadline = time.monotonic() + 240
    payload = request_json(
        "/api/jv-searchengine/public/jv-search/search",
        body={
            "resultsPerPage": PAGE_SIZE,
            "page": page,
            "sortSearch": "MOST_RECENT",
            "keywords": [],
            "positionOfferingCodes": ["internship"],
            "locationCodes": ["el" if country == "GR" else country.lower()],
            "requestLanguage": "en",
        },
        deadline=deadline,
    )
    total, jobs = payload.get("numberRecords"), payload.get("jvs")
    if (
        type(total) is not int
        or total < 0
        or not isinstance(jobs, list)
        or len(jobs) > PAGE_SIZE
    ):
        raise CatalogueImportError("eures_invalid_search")
    if not jobs and (page - 1) * PAGE_SIZE < total:
        raise CatalogueImportError("eures_incomplete_page")
    records, seen = [], set()
    for listing in jobs:
        if not isinstance(listing, dict):
            raise CatalogueImportError("eures_invalid_search")
        identity = listing.get("id")
        url = public_url(identity)
        if identity in seen:
            raise CatalogueImportError("eures_duplicate_page")
        seen.add(identity)
        try:
            detail = request_json(
                f"/api/jv-searchengine/public/jv/id/{quote(identity, safe='')}?lang=en",
                deadline=deadline,
            )
        except CatalogueImportError as exc:
            if exc.code != "eures_not_found":
                raise  # Retry this page, never advance past an unread detail.
            records.append({"id": identity, "url": url, "error": "eures_not_found"})
            continue
        try:
            records.append(profile_record(listing, detail))
        except CatalogueImportError as exc:
            records.append({"id": identity, "url": url, "error": exc.code})
    more = page * PAGE_SIZE < total
    if more and len(jobs) != PAGE_SIZE:
        raise CatalogueImportError("eures_incomplete_page")
    return EuresPage(
        records,
        str(page + 1) if more and page < MAX_PAGE else "",
        total,
        more and page == MAX_PAGE,
    )


def normalize_record(raw, _site=None):
    from jobboard.services.engine_quality import extract_facts, structured_country_code

    if raw.get("error"):
        raise CatalogueImportError(raw["error"])
    identity = raw.get("id")
    url = public_url(identity)
    company, description, title = (
        raw.get("company"),
        raw.get("description"),
        raw.get("title"),
    )
    if (
        not isinstance(company, str)
        or not company.strip()
        or len(company) > 240
        or company.strip().casefold()
        in {"non renseigné", "not specified", "unknown", "confidential", "n/a"}
        or not isinstance(description, str)
        or not 40 <= len(description.strip()) <= 200000
        or not isinstance(title, str)
    ):
        raise CatalogueImportError("eures_missing_details")
    description = html_text(description)
    if len(description.strip()) < 40:
        raise CatalogueImportError("eures_missing_details")
    places = raw.get("locations")
    if not isinstance(places, list) or len(places) > 100:
        raise CatalogueImportError("eures_invalid_location")
    locations = []
    for place in places:
        if not isinstance(place, dict):
            raise CatalogueImportError("eures_invalid_location")
        country = place.get("countryCode") or ""
        city = place.get("cityName") or ""
        if not isinstance(country, str) or not isinstance(city, str):
            raise CatalogueImportError("eures_invalid_location")
        code = structured_country_code(
            "GR" if country.upper() == "EL" else country.upper()
        )
        label = ", ".join(x for x in (city, code) if x)
        locations.append({"name": label, "country_code": code})
    offering = raw.get("positionOfferingCode")
    # Explicit non-stage contracts cannot be rescued by a misleading title.
    facts = extract_facts(
        title, description, contract_type="unknown", locations=locations
    )
    if offering != "internship":
        facts["classification"] = (
            "not_internship"
            if offering in ("apprenticeship", "trainee", "traineeship", "directhire")
            else "uncertain"
        )
    if facts["classification"] != "confirmed" or facts["europe_status"] != "in_scope":
        return None, facts
    row = _posting(
        raw, identity, title, description, url, url, [x["name"] for x in locations]
    )
    row.update(
        contract_type="unknown",
        location_details=[
            {"name": x["name"], "country": x["country_code"]} for x in locations
        ],
    )
    return row, facts
