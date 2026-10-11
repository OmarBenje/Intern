"""Bounded JobSpy reads and conservative normalization of public job records."""

import json
import re
import subprocess
import sys
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from .greenhouse_catalogue import CatalogueImportError
from .linkedin_discovery import COUNTRIES
from .public_catalogue import _posting
from .workday_catalogue import COUNTRY_NAMES

SITES = ("linkedin", "indeed", "glassdoor")
PAGE_SIZE = 20
MAX_OFFSET = 200
TIMEOUT = 180


def collect(site, country, term, offset=0, limit=PAGE_SIZE):
    if (
        site not in SITES
        or country not in COUNTRIES
        or not 0 <= offset <= MAX_OFFSET
        or not 1 <= limit <= PAGE_SIZE
        or not isinstance(term, str)
        or len(term) > 120
    ):
        raise CatalogueImportError("invalid_jobspy_query")
    name = COUNTRIES[country][0]
    options = {
        "site": site,
        "term": term,
        "location": name,
        "country_name": "UK" if country == "GB" else name,
        "offset": offset,
        "limit": limit,
    }
    try:
        result = subprocess.run(
            [sys.executable, "-m", "jobboard.integrations.jobspy_runner"],
            input=json.dumps(options),
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise CatalogueImportError("jobspy_timeout") from exc
    if result.returncode:
        raise CatalogueImportError("jobspy_failed")
    if len(result.stdout.encode()) > 5 * 1024 * 1024:
        raise CatalogueImportError("response_too_large")
    try:
        rows = json.loads(result.stdout)
    except ValueError as exc:
        raise CatalogueImportError("jobspy_invalid_response") from exc
    confirmed_empty = False
    if isinstance(rows, dict) and site == "indeed":
        if rows.get("error"):
            error = CatalogueImportError(rows["error"])
            error.retry_after = rows.get("retry_after")
            raise error
        confirmed_empty = rows.get("empty_confirmed") is True
        rows = rows.get("rows")
    if (
        not isinstance(rows, list)
        or len(rows) > limit
        or any(not isinstance(r, dict) for r in rows)
    ):
        raise CatalogueImportError("jobspy_invalid_response")
    # JobSpy sometimes logs an upstream error and returns an empty DataFrame.
    # Empty search is not authoritative proof of a successful full snapshot.
    if not rows and not confirmed_empty:
        raise CatalogueImportError("jobspy_empty_unconfirmed")
    return rows


def canonical_url(url, site):
    parts = urlsplit(url or "")
    if (
        parts.scheme != "https"
        or parts.username
        or parts.password
        or parts.port not in (None, 443)
    ):
        raise CatalogueImportError("invalid_job_url")
    host = parts.hostname or ""
    if site == "linkedin":
        match = re.fullmatch(r"/jobs/view/(?:[^/]*-)?([0-9]+)/?", parts.path)
        if not (host == "linkedin.com" or host.endswith(".linkedin.com")) or not match:
            raise CatalogueImportError("invalid_job_url")
        return match[1], "https://www.linkedin.com/jobs/view/" + match[1]
    if site == "indeed":
        identity = parse_qs(parts.query).get("jk", [""])[0]
        if not (
            host == "indeed.com" or host.endswith(".indeed.com")
        ) or not re.fullmatch(r"[a-zA-Z0-9]{1,80}", identity):
            raise CatalogueImportError("invalid_job_url")
        return identity, "https://www.indeed.com/viewjob?" + urlencode({"jk": identity})
    if site == "glassdoor" and (
        host == "glassdoor.com" or host.endswith(".glassdoor.com")
    ):
        identity = parse_qs(parts.query).get("jobListingId", [""])[0]
        if identity.isdecimal():
            return identity, urlunsplit(
                ("https", host, parts.path, urlencode({"jobListingId": identity}), "")
            )
    raise CatalogueImportError("invalid_job_url")


def normalize_record(raw, site):
    from jobboard.services.engine_quality import extract_facts, structured_country_code

    raw = {**raw, "site": site}
    identity, url = canonical_url(raw.get("url"), site)
    company = raw.get("company")
    title, description, label = (
        raw.get("title"),
        raw.get("description"),
        raw.get("location"),
    )
    if (
        not isinstance(company, str)
        or not company.strip()
        or len(company) > 240
        or not isinstance(description, str)
        or len(description.strip()) < 40
        or len(description) > 200000
        or not isinstance(label, str)
    ):
        raise CatalogueImportError("jobspy_missing_details")
    # Never use the query country or the employer's headquarters as location proof.
    explicit = raw.get("country") or ""
    code = structured_country_code(explicit) or COUNTRY_NAMES.get(explicit.casefold())
    if not code:
        codes = {
            structured_country_code(part.strip())
            or COUNTRY_NAMES.get(part.strip().casefold())
            for part in label.split(",")
        }
        codes.discard(None)
        code = next(iter(codes)) if len(codes) == 1 else None
    contract = (
        "internship" if "internship" in (raw.get("job_types") or []) else "unknown"
    )
    mode = "remote" if raw.get("remote") is True else "unknown"
    facts = extract_facts(
        title or "",
        description,
        contract_type=contract,
        locations=[{"name": label, "country_code": code}],
        work_mode=mode,
    )
    if facts["classification"] != "confirmed" or facts["europe_status"] != "in_scope":
        return None, facts
    # The visible public job URL is a usable application entry point; a board URL
    # or externally hidden direct-apply link is not required.
    row = _posting(raw, identity, title, description, url, url, [label])
    row.update(
        location_details=[{"name": label, "country": code}],
        contract_type=contract,
        work_mode=mode,
    )
    return row, facts
