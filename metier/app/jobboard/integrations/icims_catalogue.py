"""Inspected public iCIMS boards: iframe search and JobPosting JSON-LD."""

import re
import time
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit

from .greenhouse_catalogue import CatalogueImportError
from .personio_catalogue import html_text
from .public_catalogue import CatalogueSnapshot, _posting
from .public_html import PublicHTMLParser, fetch_html, validate_url

BOARDS = {
    "hines": ("careers-hines.icims.com", "Hines"),
    "sas": ("global-sas.icims.com", "SAS"),
    "adlittle": ("internships-adlittle.icims.com", "Arthur D. Little"),
    "trinseo": ("emeacareers-trinseo.icims.com", "Trinseo"),
}
JOB_PATH = re.compile(r"/jobs/([0-9]+)/[^/]+/job/?")
MAX_PAGES = 10
MAX_DETAILS = 180


def parse_icims_url(url):
    for key, (host, _) in BOARDS.items():
        if urlsplit(url).hostname == host:
            parts = validate_url(url, {host})
            if parts.path not in (
                "",
                "/",
                "/jobs/search",
                "/jobs/search/",
            ) and not JOB_PATH.fullmatch(parts.path):
                raise CatalogueImportError("expected_board_url")
            return {
                "provider": "icims",
                "instance": "global",
                "board_key": key,
                "canonical": f"https://{host}/jobs/search",
            }
    raise CatalogueImportError("unsupported_source_url")


def eligible_row(raw, identity, title, description, url, locations, contract="unknown"):
    from jobboard.services.engine_quality import extract_facts, structured_country_code

    row = _posting(
        raw, identity, title, description, url, url, [p["name"] for p in locations]
    )
    row["location_details"] = locations
    row["contract_type"] = contract
    facts = extract_facts(
        title,
        description,
        contract_type=contract,
        locations=[
            {"name": p["name"], "country_code": structured_country_code(p["country"])}
            for p in locations
        ],
    )
    return (
        row
        if facts["classification"] == "confirmed"
        and facts["europe_status"] == "in_scope"
        else None
    )


def documents(value):
    if isinstance(value, list):
        for item in value:
            yield from documents(item)
    elif isinstance(value, dict):
        if value.get("@type") == "JobPosting":
            yield value
        yield from documents(value.get("@graph", []))


def normalize_job(html, url, key):
    host = BOARDS[key][0]
    parts = validate_url(url, {host})
    match = JOB_PATH.fullmatch(parts.path)
    if not match:
        raise CatalogueImportError("invalid_job_url")
    parser = PublicHTMLParser()
    parser.feed(html)
    jobs = list(documents(parser.documents))
    if len(jobs) != 1:
        raise CatalogueImportError("job_detail_unconfirmed")
    job = jobs[0]
    source = validate_url(job.get("url", ""), {host})
    source_match = JOB_PATH.fullmatch(source.path)
    if not source_match or source_match[1] != match[1]:
        raise CatalogueImportError("job_detail_unconfirmed")
    if job.get("validThrough"):
        try:
            expiry = datetime.fromisoformat(job["validThrough"])
            if expiry.tzinfo is None:
                raise ValueError()
            if expiry <= datetime.now(UTC):
                return None
        except (ValueError, TypeError, AttributeError) as exc:
            raise CatalogueImportError("invalid_expiry") from exc
    places = job.get("jobLocation", [])
    if isinstance(places, dict):
        places = [places]
    if not isinstance(places, list):
        raise CatalogueImportError("invalid_location")
    locations = []
    for place in places:
        address = place.get("address", {}) if isinstance(place, dict) else {}
        if not isinstance(address, dict):
            raise CatalogueImportError("invalid_location")
        country = address.get("addressCountry", "")
        if isinstance(country, dict):
            country = country.get("name", "")
        country = "GB" if country == "UK" else country
        city = address.get("addressLocality", "")
        if city == "UNAVAILABLE":
            city = ""
        if not isinstance(country, str) or not isinstance(city, str):
            raise CatalogueImportError("invalid_location")
        if city or country:
            locations.append({"name": city or country, "country": country})
    contract = (
        "internship"
        if job.get("employmentType") in ("INTERN", "INTERNSHIP")
        else "unknown"
    )
    return eligible_row(
        job,
        match[1],
        job.get("title"),
        html_text(job.get("description") or ""),
        f"https://{host}{source.path}",
        locations,
        contract,
    )


def fetch_icims(key):
    if key not in BOARDS:
        raise CatalogueImportError("invalid_board_key")
    host = BOARDS[key][0]
    deadline = time.monotonic() + 600
    rows, seen = [], set()
    errors = [{"code": "keyword_search_partial"}]
    total_bytes = 0

    def read(url):
        nonlocal total_bytes
        final, html = fetch_html(url, {host}, deadline=deadline)
        total_bytes += len(html.encode())
        if total_bytes > 80 * 1024 * 1024:
            raise CatalogueImportError("response_too_large")
        return final, html

    try:
        for page in range(MAX_PAGES):
            url = f"https://{host}/jobs/search?" + urlencode(
                {"ss": 1, "searchKeyword": "intern", "in_iframe": 1, "pr": page}
            )
            final, html = read(url)
            parser = PublicHTMLParser()
            parser.feed(html)
            next_page = False
            for link in parser.links:
                absolute = urljoin(final, link)
                parts = urlsplit(absolute)
                if parts.scheme != "https" or parts.hostname != host:
                    continue
                params = parse_qs(parts.query)
                if (
                    parts.path.rstrip("/") == "/jobs/search"
                    and params.get("pr") == [str(page + 1)]
                    and params.get("searchKeyword") == ["intern"]
                ):
                    next_page = True
                match = JOB_PATH.fullmatch(parts.path)
                if not match or match[1] in seen:
                    continue
                if len(seen) >= MAX_DETAILS:
                    errors.append({"code": "detail_budget_exceeded"})
                    return CatalogueSnapshot(rows, complete=False, errors=errors)
                seen.add(match[1])
                detail_url, detail = read(f"https://{host}{parts.path}?in_iframe=1")
                if urlsplit(detail_url).path != parts.path:
                    raise CatalogueImportError("job_detail_unconfirmed")
                try:
                    row = normalize_job(detail, detail_url, key)
                    if row:
                        rows.append(row)
                except CatalogueImportError as exc:
                    errors.append({"external_id": match[1], "code": exc.code})
            if not next_page:
                break
        else:
            errors.append({"code": "page_budget_exceeded"})
    except CatalogueImportError as exc:
        if not rows:
            raise
        errors.append({"code": exc.code})
    if not rows and len(errors) > 1:
        raise CatalogueImportError(errors[-1]["code"])
    return CatalogueSnapshot(rows, complete=False, errors=errors)
