"""NAV event feed: bounded backfill, current details, explicit withdrawals."""

import json
import os
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from datetime import time as daytime
from email.utils import format_datetime
from uuid import UUID
from zoneinfo import ZoneInfo

import httpx
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from .greenhouse_catalogue import CatalogueImportError
from .personio_catalogue import html_text
from .public_catalogue import _posting, _url

BASE = "https://pam-stilling-feed.nav.no"
CANDIDATE = r"\b(?:internship|intern|praktikant|praksisplass|student placement)\b"


@dataclass
class NavPage:
    records: list
    next_cursor: str
    total: int | None = None
    truncated: bool = False
    scanned: int = 0
    at_tail: bool = False


def identity(value):
    try:
        return str(UUID(value))
    except (ValueError, TypeError, AttributeError) as exc:
        raise CatalogueImportError("nav_invalid_identity") from exc


def public_url(value):
    return "https://arbeidsplassen.nav.no/stillinger/stilling/" + identity(value)


def request(path, *, token=None, since=None, deadline=None):
    if not re.fullmatch(
        r"/api/(?:publicToken|v1/feed(?:/[a-f0-9-]{36})?|v1/feedentry/[a-f0-9-]{36})",
        path,
    ):
        raise CatalogueImportError("nav_invalid_path")
    deadline = deadline or time.monotonic() + 30
    headers = {"Accept": "application/json"}
    if token:
        if not re.fullmatch(r"[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", token):
            raise CatalogueImportError("nav_invalid_token")
        headers["Authorization"] = "Bearer " + token
    if since:
        headers["If-Modified-Since"] = since
    try:
        with (
            httpx.Client(
                timeout=60 if path == "/api/v1/feed" else 20,
                trust_env=False,
                follow_redirects=False,
            ) as client,
            client.stream("GET", BASE + path, headers=headers) as response,
        ):
            if response.status_code != 200:
                error = CatalogueImportError(
                    "nav_access_denied"
                    if response.status_code in (401, 403)
                    else "nav_not_found"
                    if response.status_code == 404
                    else "nav_rate_limited"
                    if response.status_code == 429
                    else "nav_http_error"
                )
                retry = response.headers.get("Retry-After", "")
                error.retry_after = int(retry) if retry.isdigit() else None
                raise error
            body = bytearray()
            for chunk in response.iter_bytes():
                body.extend(chunk)
                if len(body) > 5 * 1024 * 1024 or time.monotonic() >= deadline:
                    raise CatalogueImportError("nav_response_budget")
        return body.decode()
    except httpx.HTTPError:
        # Do not include request headers/tokens in exception chains or logs.
        raise CatalogueImportError("nav_network_error") from None


def get_token():
    private = os.environ.get("NAV_FEED_TOKEN")
    if private:
        return private
    body = request("/api/publicToken")
    matches = re.findall(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", body)
    if len(matches) != 1:
        raise CatalogueImportError("nav_public_token_unavailable")
    return matches[0]


def read_json(path, **kwargs):
    try:
        value = json.loads(request(path, **kwargs))
    except (ValueError, UnicodeError):
        raise CatalogueImportError("nav_invalid_response") from None
    if not isinstance(value, dict):
        raise CatalogueImportError("nav_invalid_response")
    return value


def profile_record(ad_id, detail):
    ad_id = identity(ad_id)
    if detail.get("uuid") != ad_id:
        raise CatalogueImportError("nav_identity_mismatch")
    base = {"id": ad_id, "url": public_url(ad_id)}
    if detail.get("status") != "ACTIVE":
        return {**base, "error": "nav_inactive"}
    ad = detail.get("ad_content")
    if not isinstance(ad, dict) or ad.get("uuid") != ad_id:
        raise CatalogueImportError("nav_invalid_detail")
    employer = ad.get("employer") or {}
    places = ad.get("workLocations")
    if (
        not isinstance(employer, dict)
        or not isinstance(places, list)
        or any(not isinstance(p, dict) for p in places)
    ):
        raise CatalogueImportError("nav_invalid_detail")
    return {
        **base,
        "title": ad.get("title"),
        "description": ad.get("description"),
        "company": employer.get("name"),
        "expires": ad.get("expires"),
        "application_url": ad.get("applicationUrl"),
        "locations": [
            {"city": p.get("city"), "country": p.get("country")} for p in places
        ],
    }


def collect(since, cursor="", known_ids=()):
    day = parse_date(since)
    if day is None:
        raise CatalogueImportError("nav_invalid_start")
    cursor = cursor.removeprefix("tail:")
    page_id, offset = (cursor.split(":")) if cursor else ("", "0")
    offset = int(offset)
    if not 0 <= offset <= 1000:
        raise CatalogueImportError("nav_invalid_cursor")
    if page_id:
        page_id = identity(page_id)
    deadline = time.monotonic() + 240
    token = get_token()
    payload = read_json(
        "/api/v1/feed" + ("/" + page_id if page_id else ""),
        token=token,
        deadline=deadline,
        since=None
        if page_id
        else format_datetime(datetime.combine(day, daytime.min, UTC), usegmt=True),
    )
    current = identity(payload.get("id"))
    if page_id and page_id != current:
        raise CatalogueImportError("nav_page_mismatch")
    items = payload.get("items")
    if not isinstance(items, list) or len(items) > 1000 or offset > len(items):
        raise CatalogueImportError("nav_invalid_page")
    next_id = identity(payload["next_id"]) if payload.get("next_id") else None
    if next_id == current:
        raise CatalogueImportError("nav_page_loop")
    records, fetched = [], set()
    position = offset
    for item in items[offset:]:
        if not isinstance(item, dict) or not isinstance(item.get("_feed_entry"), dict):
            raise CatalogueImportError("nav_invalid_event")
        meta = item["_feed_entry"]
        ad_id = identity(meta.get("uuid"))
        title = meta.get("title") or ""
        if not isinstance(title, str):
            raise CatalogueImportError("nav_invalid_event")
        if ad_id not in fetched and (
            ad_id in known_ids or re.search(CANDIDATE, title, re.IGNORECASE)
        ):
            if len(fetched) >= 20:
                break
            fetched.add(ad_id)
            try:
                detail = read_json(
                    "/api/v1/feedentry/" + ad_id, token=token, deadline=deadline
                )
                records.append(profile_record(ad_id, detail))
            except CatalogueImportError as exc:
                if exc.code != "nav_not_found":
                    raise
                records.append(
                    {"id": ad_id, "url": public_url(ad_id), "error": exc.code}
                )
        position += 1
    at_tail = position == len(items) and not next_id
    next_cursor = (
        next_id + ":0"
        if position == len(items) and next_id
        else current + ":" + str(position)
    )
    return NavPage(
        records,
        ("tail:" if at_tail else "") + next_cursor,
        scanned=position - offset,
        at_tail=at_tail,
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
    ):
        raise CatalogueImportError("nav_missing_details")
    description = html_text(description)
    if not 40 <= len(description) <= 200000:
        raise CatalogueImportError("nav_missing_details")
    try:
        expiry = parse_datetime(raw.get("expires") or "")
    except (ValueError, TypeError):
        expiry = None
    if expiry is None or timezone.is_naive(expiry):
        raise CatalogueImportError("nav_invalid_expiry")
    # NAV keeps vacancies visible through their expiry day (Norwegian local time).
    expiry = datetime.combine(
        expiry.astimezone(ZoneInfo("Europe/Oslo")).date() + timedelta(days=1),
        daytime.min,
        ZoneInfo("Europe/Oslo"),
    )
    if expiry <= timezone.now():
        raise CatalogueImportError("nav_expired")
    places = raw.get("locations")
    if not isinstance(places, list) or not places or len(places) > 100:
        raise CatalogueImportError("nav_invalid_locations")
    locations = []
    for place in places:
        country, city = place.get("country") or "", place.get("city") or ""
        if not isinstance(country, str) or not isinstance(city, str):
            raise CatalogueImportError("nav_invalid_locations")
        code = structured_country_code(country)
        locations.append(
            {"name": ", ".join(x for x in (city, code) if x), "country_code": code}
        )
    mode = (
        "remote"
        if re.search(r"\bremote\b|100\s*%\s*hjemmekontor", title, re.IGNORECASE)
        else "unknown"
    )
    facts = extract_facts(title, description, locations=locations, work_mode=mode)
    if facts["classification"] != "confirmed" or facts["europe_status"] != "in_scope":
        return None, facts
    apply = _url(raw["application_url"]) if raw.get("application_url") else url
    row = _posting(
        raw, raw["id"], title, description, url, apply, [x["name"] for x in locations]
    )
    row.update(
        contract_type="unknown",
        work_mode=mode,
        expires_at=expiry,
        location_details=[
            {"name": x["name"], "country": x["country_code"]} for x in locations
        ],
    )
    return row, facts
