"""Public Swedish JobSearch search + detail ingestion, with explicit country evidence."""

import re
import time
from dataclasses import dataclass
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .greenhouse_catalogue import CatalogueImportError
from .public_catalogue import _posting, read_json

BASE = "https://jobsearch.api.jobtechdev.se"
TERMS = ("internship", "praktik", "praktikant", "LIA")
PAGE_SIZE = 20
MAX_OFFSET = 2000


@dataclass
class JobtechPage:
    records: list
    next_cursor: str
    total: int
    truncated: bool = False


def public_url(identity):
    if not isinstance(identity, str) or not re.fullmatch(r"[0-9]{1,20}", identity):
        raise CatalogueImportError("jobtech_invalid_identity")
    return "https://arbetsformedlingen.se/platsbanken/annonser/" + identity


def profile_record(identity, detail):
    url = public_url(identity)
    if not isinstance(detail, dict) or detail.get("id") != identity:
        raise CatalogueImportError("jobtech_identity_mismatch")
    employer = detail.get("employer") or {}
    description = detail.get("description") or {}
    if not isinstance(employer, dict) or not isinstance(description, dict):
        raise CatalogueImportError("jobtech_invalid_detail")
    # Whitelist posting fields; do not persist contact lists or employer emails.
    return {
        "id": identity,
        "url": url,
        "company": employer.get("name"),
        "title": detail.get("headline"),
        "description": description.get("text"),
        "locations": detail.get("workplace_addresses")
        or [detail.get("workplace_address")],
        "removed": detail.get("removed"),
        "deadline": detail.get("application_deadline"),
        "workplace_model": detail.get("workplace_model"),
    }


def collect(term, offset=0):
    if term not in TERMS or type(offset) is not int or not 0 <= offset <= MAX_OFFSET:
        raise CatalogueImportError("jobtech_invalid_query")
    deadline = time.monotonic() + 240
    payload = read_json(
        BASE
        + "/search?"
        + urlencode(
            {
                "q": term,
                "offset": offset,
                "limit": PAGE_SIZE,
                "sort": "pubdate-desc",
            }
        ),
        deadline=deadline,
    )
    if not isinstance(payload, dict) or not isinstance(payload.get("total"), dict):
        raise CatalogueImportError("jobtech_invalid_search")
    total, hits = payload["total"].get("value"), payload.get("hits")
    if (
        type(total) is not int
        or total < 0
        or not isinstance(hits, list)
        or len(hits) > PAGE_SIZE
    ):
        raise CatalogueImportError("jobtech_invalid_search")
    if len(hits) < min(PAGE_SIZE, max(0, total - offset)):
        raise CatalogueImportError("jobtech_incomplete_page")
    records, seen = [], set()
    for hit in hits:
        identity = hit.get("id") if isinstance(hit, dict) else None
        public_url(identity)
        if identity in seen:
            raise CatalogueImportError("jobtech_duplicate_page")
        seen.add(identity)
        # Any unread detail keeps the page cursor unchanged for a later retry.
        detail = read_json(BASE + "/ad/" + identity, deadline=deadline)
        records.append(profile_record(identity, detail))
    next_offset = offset + len(hits)
    more = next_offset < total
    return JobtechPage(
        records,
        str(next_offset) if more and next_offset <= MAX_OFFSET else "",
        total,
        more and next_offset > MAX_OFFSET,
    )


def normalize_record(raw, _site=None):
    from jobboard.services.engine_quality import extract_facts

    url = public_url(raw.get("id"))
    title, description, company = (
        raw.get("title"),
        raw.get("description"),
        raw.get("company"),
    )
    if (
        not isinstance(title, str)
        or not isinstance(description, str)
        or not 40 <= len(description.strip()) <= 200000
        or not isinstance(company, str)
        or not company.strip()
        or len(company) > 240
    ):
        raise CatalogueImportError("jobtech_missing_details")
    if raw.get("removed") is not False:
        raise CatalogueImportError("jobtech_removed_or_unknown")
    try:
        expires = parse_datetime(raw.get("deadline") or "")
    except (ValueError, TypeError):
        expires = None
    if expires is None:
        raise CatalogueImportError("jobtech_missing_deadline")
    if timezone.is_naive(expires):
        expires = timezone.make_aware(expires, ZoneInfo("Europe/Stockholm"))
    if expires <= timezone.now():
        raise CatalogueImportError("jobtech_expired")
    places = raw.get("locations")
    if not isinstance(places, list) or not places or len(places) > 100:
        raise CatalogueImportError("jobtech_invalid_locations")
    locations = []
    for place in places:
        if not isinstance(place, dict):
            raise CatalogueImportError("jobtech_invalid_locations")
        # These are Swedish taxonomy identifiers, not ISO codes. Unknown/foreign
        # places stay unknown instead of borrowing the search country.
        code = (
            "SE"
            if (
                place.get("country") == "Sverige"
                and str(place.get("country_code")) == "199"
            )
            else None
        )
        city = place.get("city") or place.get("municipality") or ""
        if not isinstance(city, str):
            raise CatalogueImportError("jobtech_invalid_locations")
        locations.append(
            {
                "name": ", ".join(x for x in (city, code) if x) or "Lieu non précisé",
                "country_code": code,
            }
        )
    model = raw.get("workplace_model") or {}
    if not isinstance(model, dict):
        raise CatalogueImportError("jobtech_invalid_workplace_model")
    mode = (
        "remote"
        if re.search(r"remote|distans", model.get("label") or "", re.IGNORECASE)
        or re.search(r"\b(?:remote|distans)\b", title, re.IGNORECASE)
        or re.search(
            r"(?:100\s*%|helt)\s+(?:på\s+)?distans\b", description, re.IGNORECASE
        )
        else "unknown"
    )
    facts = extract_facts(title, description, locations=locations, work_mode=mode)
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
