"""Observed public Workday career requests, not a supported global Workday API.

Country facet IDs are discovered from each employer response. Partitioning avoids
Workday's 2000-result cap; any cap, changing pagination or detail error makes the
snapshot partial and therefore unsuitable for absence/closure reconciliation.
"""

import json
import re
import time
from urllib.parse import urlsplit

import httpx

from .greenhouse_catalogue import MAX_RESPONSE_BYTES, CatalogueImportError, _Text

HOST = re.compile(r"([a-z0-9-]+)\.wd[1-9][0-9]?\.myworkdayjobs\.com")
TOKEN = re.compile(r"[A-Za-z0-9_-]{1,100}")
WORKDAY_SCOPE = "europe-title-internships-v1"
MAX_SECONDS = 600
MAX_REQUESTS = 1800
MAX_BYTES = 80 * 1024 * 1024
FALLBACK_MAX_LISTINGS = 2000
COUNTRY_FACET_LABELS = {
    "country",
    "country/region",
    "location country",
    "location country / territory",
}
COUNTRIES = dict(
    zip(
        [
            "AL",
            "AD",
            "AT",
            "BY",
            "BE",
            "BA",
            "BG",
            "HR",
            "CY",
            "CZ",
            "DK",
            "EE",
            "FI",
            "FR",
            "DE",
            "GR",
            "HU",
            "IS",
            "IE",
            "IT",
            "XK",
            "LV",
            "LI",
            "LT",
            "LU",
            "MT",
            "MD",
            "MC",
            "ME",
            "NL",
            "MK",
            "NO",
            "PL",
            "PT",
            "RO",
            "SM",
            "RS",
            "SK",
            "SI",
            "ES",
            "SE",
            "CH",
            "UA",
            "GB",
            "VA",
            "FO",
            "GI",
        ],
        [
            "Albania",
            "Andorra",
            "Austria",
            "Belarus",
            "Belgium",
            "Bosnia and Herzegovina",
            "Bulgaria",
            "Croatia",
            "Cyprus",
            "Czechia",
            "Denmark",
            "Estonia",
            "Finland",
            "France",
            "Germany",
            "Greece",
            "Hungary",
            "Iceland",
            "Ireland",
            "Italy",
            "Kosovo",
            "Latvia",
            "Liechtenstein",
            "Lithuania",
            "Luxembourg",
            "Malta",
            "Moldova",
            "Monaco",
            "Montenegro",
            "Netherlands",
            "North Macedonia",
            "Norway",
            "Poland",
            "Portugal",
            "Romania",
            "San Marino",
            "Serbia",
            "Slovakia",
            "Slovenia",
            "Spain",
            "Sweden",
            "Switzerland",
            "Ukraine",
            "United Kingdom",
            "Vatican City",
            "Faroe Islands",
            "Gibraltar",
        ],
        strict=True,
    )
)
COUNTRY_NAMES = {name.casefold(): code for code, name in COUNTRIES.items()}
COUNTRY_NAMES.update({"czech republic": "CZ", "holy see": "VA"})


def parse_workday_url(url):
    parsed = urlsplit(url)
    match = HOST.fullmatch(parsed.hostname or "")
    if (
        not match
        or parsed.scheme != "https"
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
    ):
        raise CatalogueImportError("invalid_board_url")
    parts = parsed.path.strip("/").split("/")
    if parts and re.fullmatch(r"[a-z]{2}-[A-Z]{2}", parts[0]):
        parts = parts[1:]
    if not parts or not TOKEN.fullmatch(parts[0]):
        raise CatalogueImportError("invalid_board_url")
    site = parts[0]
    host = parsed.hostname
    return {
        "provider": "workday",
        "instance": "global",
        "board_key": f"{host}/{match[1]}/{site}",
        "canonical": f"https://{host}/en-US/{site}",
    }


def _key(key):
    parts = key.split("/")
    if len(parts) != 3:
        raise CatalogueImportError("invalid_board_key")
    host, tenant, site = parts
    match = HOST.fullmatch(host)
    if not match or match[1] != tenant or not TOKEN.fullmatch(site):
        raise CatalogueImportError("invalid_board_key")
    return host, tenant, site


def _country_partitions(facets):
    result = []
    stack = list(facets) if isinstance(facets, list) else []
    visited = 0
    while stack:
        node = stack.pop()
        visited += 1
        if visited > 3000 or not isinstance(node, dict):
            raise CatalogueImportError("invalid_facets")
        values = node.get("values", [])
        if not isinstance(values, list):
            raise CatalogueImportError("invalid_facets")
        parameter = node.get("facetParameter")
        is_country = parameter in ("locationCountry", "locationHierarchy1") or (
            isinstance(parameter, str)
            and TOKEN.fullmatch(parameter)
            and str(node.get("descriptor", "")).casefold() in COUNTRY_FACET_LABELS
        )
        if is_country:
            for item in values:
                if not isinstance(item, dict):
                    raise CatalogueImportError("invalid_facets")
                code = COUNTRY_NAMES.get(str(item.get("descriptor", "")).casefold())
                identity = item.get("id")
                if code and isinstance(identity, str) and TOKEN.fullmatch(identity):
                    result.append((parameter, identity, code))
        else:
            stack.extend(
                v for v in values if isinstance(v, dict) and "facetParameter" in v
            )
    return sorted(set(result))


def _candidate(title):
    from jobboard.services.engine_quality import (
        APPRENTICESHIP_TITLE,
        INTERN,
        NEGATIVE_TITLE,
        NON_INTERNSHIP_TITLE,
    )

    return isinstance(title, str) and bool(
        re.search(INTERN + r"|\bplacement\b", title, re.IGNORECASE)
        and not re.search(
            APPRENTICESHIP_TITLE + "|" + NEGATIVE_TITLE + "|" + NON_INTERNSHIP_TITLE,
            title,
            re.IGNORECASE,
        )
    )


def normalize_workday(payload, *, host, site, path):
    from jobboard.integrations.public_catalogue import _posting
    from jobboard.services.engine_quality import extract_facts

    info = payload.get("jobPostingInfo") if isinstance(payload, dict) else None
    if not isinstance(info, dict):
        raise CatalogueImportError("invalid_job")
    if info.get("canApply") is False or info.get("posted") is False:
        return None
    title = info.get("title")
    description = info.get("jobDescription")
    if not _candidate(title) or not isinstance(description, str):
        return None
    parser = _Text()
    parser.feed(description)
    text = "\n".join(parser.parts)
    if extract_facts(title, text)["classification"] != "confirmed":
        return None
    location = info.get("location")
    requisition_location = info.get("jobRequisitionLocation") or {}
    if not isinstance(requisition_location, dict):
        raise CatalogueImportError("invalid_location")
    country = requisition_location.get("country") or info.get("country") or {}
    if not isinstance(country, dict) or not isinstance(location, str):
        raise CatalogueImportError("invalid_location")
    code = country.get("alpha2Code") or COUNTRY_NAMES.get(
        str(country.get("descriptor", "")).casefold()
    )
    # Remote residence eligibility isn't established by an office country.
    if (
        not isinstance(code, str)
        or code not in COUNTRIES
        or re.search(r"\bremote\b", location, re.IGNORECASE)
    ):
        return None
    url = f"https://{host}/en-US/{site}{path}"
    # Keep only the public advertisement; discard questionnaire/user metadata.
    raw = {
        "jobPostingInfo": {
            k: v
            for k, v in info.items()
            if k
            in (
                "id",
                "title",
                "jobDescription",
                "location",
                "country",
                "jobRequisitionLocation",
                "additionalLocations",
                "timeType",
                "jobReqId",
                "startDate",
                "posted",
                "canApply",
            )
        }
    }
    row = _posting(raw, info.get("jobReqId"), title, text, url, url, [location])
    row["location_details"] = [{"name": location, "country": code}]
    row["published_at"] = info.get(
        "startDate"
    )  # Workday startDate is publication date.
    row["contract_type"] = "unknown"  # Full time is hours, never a contract type.
    return row


def fetch_workday_snapshot(key):
    from jobboard.integrations.public_catalogue import CatalogueSnapshot

    host, tenant, site = _key(key)
    base = f"https://{host}/wday/cxs/{tenant}/{site}"
    deadline = time.monotonic() + MAX_SECONDS
    size = requests = 0
    rows, errors, seen = [], [], set()
    row_ids = set()

    def error(identity, code):
        if len(errors) < 500:
            errors.append({"external_id": identity, "code": code})

    with httpx.Client(timeout=20, follow_redirects=False, trust_env=False) as client:

        def read(path, body=None):
            nonlocal size, requests
            requests += 1
            if requests > MAX_REQUESTS or time.monotonic() >= deadline:
                raise CatalogueImportError("snapshot_budget_exceeded")
            try:
                with client.stream(
                    "POST" if body is not None else "GET",
                    base + path,
                    json=body,
                    headers={"Accept": "application/json"},
                ) as response:
                    if response.status_code != 200:
                        exc = CatalogueImportError(
                            "upstream_rate_limited"
                            if response.status_code == 429
                            else "upstream_http_error"
                        )
                        retry = response.headers.get("Retry-After", "")
                        exc.retry_after = (
                            min(int(retry), 86400) if retry.isdigit() else None
                        )
                        raise exc
                    data = bytearray()
                    for chunk in response.iter_bytes():
                        data.extend(chunk)
                        size += len(chunk)
                        if (
                            size > MAX_BYTES
                            or len(data) > MAX_RESPONSE_BYTES
                            or time.monotonic() >= deadline
                        ):
                            raise CatalogueImportError("snapshot_budget_exceeded")
                return json.loads(data)
            except (httpx.HTTPError, ValueError, TypeError) as exc:
                raise CatalogueImportError("upstream_invalid_response") from exc

        def listing(facets, offset):
            payload = read(
                "/jobs",
                {
                    "appliedFacets": facets,
                    "limit": 20,
                    "offset": offset,
                    "searchText": "",
                },
            )
            if (
                not isinstance(payload, dict)
                or type(payload.get("total")) is not int
                or payload["total"] < 0
                or not isinstance(payload.get("jobPostings"), list)
            ):
                raise CatalogueImportError("invalid_snapshot")
            return payload

        initial = listing({}, 0)
        partitions = _country_partitions(initial.get("facets"))
        fallback = not partitions
        if fallback:
            # No trustworthy country partition: scan a bounded global listing.
            # Always partial: this path may collect, never infer disappeared jobs.
            error("", "country_facets_fallback")
            partitions = [(None, "global_fallback", None)]
        for parameter, identity, _code in partitions:
            offset, total, partition_seen = 0, None, set()
            try:
                while True:
                    payload = (
                        initial
                        if fallback and offset == 0
                        else listing(
                            {parameter: [identity]} if parameter else {}, offset
                        )
                    )
                    if total is None:
                        total = payload["total"]
                        if total >= 2000:
                            error(identity, "upstream_result_cap")
                    # CXS only supplies total on offset zero; later pages return 0.
                    if payload["total"] not in (0, total):
                        raise CatalogueImportError("snapshot_changed")
                    batch = payload["jobPostings"]
                    if len(batch) > 20 or (not batch and offset < total):
                        raise CatalogueImportError("incomplete_snapshot")
                    for job in batch:
                        if not isinstance(job, dict):
                            raise CatalogueImportError("invalid_job")
                        path = job.get("externalPath")
                        if (
                            not isinstance(path, str)
                            or len(path) > 1500
                            or not re.fullmatch(r"/job/[A-Za-z0-9_/%.-]+", path)
                            or ".." in path
                            or "%" in path
                        ):
                            error("", "invalid_job_path")
                            continue
                        if path in partition_seen:
                            raise CatalogueImportError("duplicate_job")
                        partition_seen.add(path)
                        if path in seen or not _candidate(job.get("title")):
                            continue
                        seen.add(path)
                        try:
                            row = normalize_workday(
                                read(path), host=host, site=site, path=path
                            )
                            if row is not None and row["external_id"] not in row_ids:
                                rows.append(row)
                                row_ids.add(row["external_id"])
                        except CatalogueImportError as exc:
                            error(path, str(exc))
                            if str(exc) in (
                                "snapshot_budget_exceeded",
                                "upstream_rate_limited",
                            ):
                                raise
                    offset += len(batch)
                    if fallback and offset >= FALLBACK_MAX_LISTINGS and offset < total:
                        error(identity, "fallback_listing_cap")
                        break
                    if offset >= total:
                        if offset != total:
                            raise CatalogueImportError("snapshot_changed")
                        break
            except CatalogueImportError as exc:
                error(identity, str(exc))
                if exc.code == "upstream_rate_limited":
                    # Do not immediately re-import a partial preflight after 429.
                    # Keep Retry-After available to both probe and board schedulers.
                    raise
                if exc.code == "snapshot_budget_exceeded":
                    break
    return CatalogueSnapshot(rows, complete=not errors, errors=errors)
