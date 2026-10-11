"""Public WTTJ search index, bounded date partitions and source-authored excerpts."""

import json
import re
import time
from dataclasses import dataclass

import httpx

from .greenhouse_catalogue import CatalogueImportError
from .personio_catalogue import html_text
from .public_catalogue import _posting

ORIGIN = "https://www.welcometothejungle.com"
# Search-only browser configuration, not a private account/API credential.
APP_ID = "CSEKHVMS53"
SEARCH_KEY = "4bd8f6215d0cc52b26430765769e65a0"
INDEX_URL = "https://csekhvms53-dsn.algolia.net/1/indexes/wttj_jobs_production_fr_published_at_desc/query"
PAGE_SIZE = 50
FIELDS = [
    "reference",
    "objectID",
    "name",
    "organization.name",
    "organization.slug",
    "organization.logo.url",
    "slug",
    "offices",
    "contract_type",
    "remote",
    "summary",
    "key_missions",
    "profile",
    "published_at_timestamp",
]


@dataclass
class WttjPage:
    records: list
    next_cursor: str
    total: int
    truncated: bool = False


def query_index(country, low, high, page, *, company_slug=None, deadline=None):
    deadline = deadline or time.monotonic() + 30
    if company_slug is not None and not re.fullmatch(
        r"[A-Za-z0-9_-][A-Za-z0-9_.-]{0,349}", company_slug
    ):
        raise CatalogueImportError("wttj_invalid_company")
    try:
        with (
            httpx.Client(
                timeout=max(0.1, min(20, deadline - time.monotonic())),
                follow_redirects=False,
                trust_env=False,
            ) as client,
            client.stream(
                "POST",
                INDEX_URL,
                headers={
                    "x-algolia-application-id": APP_ID,
                    "x-algolia-api-key": SEARCH_KEY,
                    "Origin": ORIGIN,
                    "Referer": ORIGIN + "/",
                    "User-Agent": "InternCatalogue/1.0",
                },
                json={
                    "filters": f'organization.slug:"{company_slug}"'
                    if company_slug
                    else f"contract_type:internship AND offices.country_code:{country}",
                    "numericFilters": []
                    if company_slug
                    else [
                        f"published_at_timestamp>={low}",
                        f"published_at_timestamp<={high}",
                    ],
                    "page": page,
                    "hitsPerPage": 1 if company_slug else PAGE_SIZE,
                    "attributesToRetrieve": FIELDS,
                    "attributesToHighlight": [],
                    "attributesToSnippet": [],
                },
            ) as response,
        ):
            if response.status_code != 200:
                exc = CatalogueImportError(
                    "wttj_rate_limited"
                    if response.status_code == 429
                    else "wttj_http_error"
                )
                retry = response.headers.get("Retry-After", "")
                exc.retry_after = min(int(retry), 86400) if retry.isdigit() else None
                raise exc
            body = bytearray()
            for chunk in response.iter_bytes():
                body.extend(chunk)
                if len(body) > 5 * 1024 * 1024 or time.monotonic() >= deadline:
                    raise CatalogueImportError("wttj_response_budget")
        payload = json.loads(body)
    except (httpx.HTTPError, ValueError) as exc:
        raise CatalogueImportError("wttj_invalid_response") from exc
    if not isinstance(payload, dict):
        raise CatalogueImportError("wttj_invalid_response")
    return payload


def company_logo(slug, company_name, *, deadline=None):
    """Reuse the public job index for a known employer slug, never fuzzy name search."""
    payload = query_index(
        "FR", 0, int(time.time()), 0, company_slug=slug, deadline=deadline
    )
    hits = payload.get("hits")
    if not isinstance(hits, list) or not hits or not isinstance(hits[0], dict):
        raise CatalogueImportError("wttj_logo_not_found")
    organization = hits[0].get("organization")
    from jobboard.services.company_logos import same_name

    if (
        not isinstance(organization, dict)
        or organization.get("slug") != slug
        or not isinstance(organization.get("name"), str)
        or not same_name(organization["name"], company_name)
    ):
        raise CatalogueImportError("wttj_logo_company_mismatch")
    logo = organization.get("logo")
    url = logo.get("url") if isinstance(logo, dict) else None
    if not isinstance(url, str) or len(url) > 2048:
        raise CatalogueImportError("wttj_logo_not_found")
    return url


def source_record(hit):
    if not isinstance(hit, dict):
        raise CatalogueImportError("wttj_invalid_hit")
    org = hit.get("organization") or {}
    identity = hit.get("reference") or hit.get("objectID")
    if not isinstance(identity, str) or not re.fullmatch(
        r"[A-Za-z0-9_-]{1,150}", identity
    ):
        raise CatalogueImportError("wttj_invalid_identity")
    if not isinstance(org, dict):
        raise CatalogueImportError("wttj_invalid_company")
    company_slug, slug = org.get("slug"), hit.get("slug")
    for value in (company_slug, slug):
        if not isinstance(value, str) or not re.fullmatch(
            r"[A-Za-z0-9_-][A-Za-z0-9_.-]{0,349}", value
        ):
            raise CatalogueImportError("wttj_invalid_url")
    return {
        **{k: hit.get(k) for k in FIELDS if "." not in k},
        "id": identity,
        "company": org.get("name"),
        "company_slug": company_slug,
        "company_logo": (org.get("logo") or {}).get("url")
        if isinstance(org.get("logo"), dict)
        else None,
        "url": f"{ORIGIN}/fr/companies/{company_slug}/jobs/{slug}",
        "description_kind": "source_summary",
    }


def collect(country, cursor=""):
    from jobboard.services.engine_quality import EUROPE_COUNTRIES

    if country not in EUROPE_COUNTRIES:
        raise CatalogueImportError("invalid_wttj_country")
    try:
        low, high, page = (
            map(int, cursor.split(":")) if cursor else (0, int(time.time()), 0)
        )
        if not 0 <= low <= high <= int(time.time()) + 60 or not 0 <= page < 20:
            raise ValueError()
    except (ValueError, AttributeError) as exc:
        raise CatalogueImportError("invalid_wttj_cursor") from exc
    for _ in range(12):
        payload = query_index(country, low, high, page)
        total, hits = payload.get("nbHits"), payload.get("hits")
        if (
            type(total) is not int
            or total < 0
            or not isinstance(hits, list)
            or len(hits) > PAGE_SIZE
            or payload.get("page") != page
            or payload.get("exhaustiveNbHits") is not True
        ):
            raise CatalogueImportError("wttj_invalid_page")
        if total > 1000:
            if page or low == high:
                raise CatalogueImportError("wttj_partition_saturated")
            low = (low + high) // 2 + 1
            continue
        if len(hits) != max(0, min(PAGE_SIZE, total - page * PAGE_SIZE)):
            raise CatalogueImportError("wttj_incomplete_page")
        records = [source_record(hit) for hit in hits]
        if len({r["id"] for r in records}) != len(records):
            raise CatalogueImportError("wttj_duplicate_page")
        if (page + 1) * PAGE_SIZE < total:
            next_cursor = f"{low}:{high}:{page + 1}"
        else:
            next_cursor = f"0:{low - 1}:0" if low else ""
        return WttjPage(records, next_cursor, total)
    # Persist the smaller date window; older windows follow after it is exhausted.
    return WttjPage([], f"{low}:{high}:0", total, True)


def normalize_record(raw, _site=None):
    from jobboard.services.engine_quality import extract_facts, structured_country_code

    if (
        not isinstance(raw.get("company"), str)
        or not raw["company"].strip()
        or len(raw["company"]) > 240
    ):
        raise CatalogueImportError("wttj_missing_company")
    # Reconstruct the canonical URL from validated source slugs, never an arbitrary URL.
    checked = source_record(
        {
            **raw,
            "organization": {"name": raw["company"], "slug": raw.get("company_slug")},
        }
    )
    parts = [
        raw[k]
        for k in ("summary", "profile")
        if isinstance(raw.get(k), str) and raw[k].strip()
    ]
    missions = raw.get("key_missions")
    if isinstance(missions, list):
        parts.extend(x for x in missions if isinstance(x, str))
    description = html_text("\n\n".join(parts))
    if not 40 <= len(description.strip()) <= 200000:
        raise CatalogueImportError("wttj_missing_description")
    offices = raw.get("offices")
    if not isinstance(offices, list) or len(offices) > 100:
        raise CatalogueImportError("wttj_invalid_location")
    places = []
    for office in offices:
        if not isinstance(office, dict):
            raise CatalogueImportError("wttj_invalid_location")
        city, country = office.get("city") or "", office.get("country_code") or ""
        if not isinstance(city, str) or not isinstance(country, str):
            raise CatalogueImportError("wttj_invalid_location")
        code = structured_country_code(country)
        places.append(
            {"name": ", ".join(x for x in (city, code) if x), "country_code": code}
        )
    mode = {
        "full": "remote",
        "fully": "remote",
        "partial": "hybrid",
        "no": "onsite",
        "punctual": "hybrid",
    }.get(raw.get("remote"), "unknown")
    facts = extract_facts(
        raw.get("name") or "", description, locations=places, work_mode=mode
    )
    if raw.get("contract_type") != "internship":
        facts["classification"] = "not_internship"
    if facts["classification"] != "confirmed" or facts["europe_status"] != "in_scope":
        return None, facts
    row = _posting(
        raw,
        checked["id"],
        raw.get("name"),
        "Résumé publié par Welcome to the Jungle\n\n" + description,
        checked["url"],
        checked["url"],
        [x["name"] for x in places],
    )
    row.update(
        work_mode=mode,
        contract_type="unknown",
        location_details=[
            {"name": x["name"], "country": x["country_code"]} for x in places
        ],
    )
    return row, facts
