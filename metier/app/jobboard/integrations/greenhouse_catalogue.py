"""Bounded, public Greenhouse board reads. No submission credentials involved."""

import hashlib
import html
import json
import re
from html.parser import HTMLParser
from urllib.parse import urlsplit

import httpx

MAX_RESPONSE_BYTES = 20 * 1024 * 1024


class CatalogueImportError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def _office_matches_job(location, office, address, explicit_locations=()):
    """Office metadata corroborates a job location, never widens its geography.

    Greenhouse may attach the entire department's offices to city-specific jobs.
    Match complete location labels or their city component, not substrings (York
    must not match New York). Unknown/remote-only locations stay unknown.
    """

    def normalized(value):
        return " ".join(value.casefold().split())

    if not location:
        return False
    office_name = office.get("name")
    aliases = {normalized(address), normalized(address.split(",", 1)[0])}
    if isinstance(office_name, str):
        aliases.add(normalized(office_name))
    aliases -= {"", "remote", "global", "worldwide", "anywhere", "all offices"}
    segments = re.split(r"[;|]", location)
    comma_labels = [normalized(value) for value in location.split(",")]
    if len(comma_labels) > 1 and set(comma_labels) == {
        normalized(value) for value in explicit_locations
    }:
        segments = location.split(",")
    for segment in segments:
        label = normalized(segment)
        if label in aliases:
            return True
    return False


def normalize_snapshot(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
        raise CatalogueImportError("invalid_snapshot")
    total = (
        payload.get("meta", {}).get("total")
        if isinstance(payload.get("meta"), dict)
        else None
    )
    jobs = payload["jobs"]
    if type(total) is not int or total != len(jobs):
        raise CatalogueImportError("incomplete_snapshot")
    normalized, ids = [], set()
    for job in jobs:
        if (
            not isinstance(job, dict)
            or type(job.get("id")) is not int
            or job["id"] <= 0
        ):
            raise CatalogueImportError("invalid_job")
        external_id = str(job["id"])
        title, content, url = (
            job.get("title"),
            job.get("content"),
            job.get("absolute_url"),
        )
        if (
            external_id in ids
            or not isinstance(title, str)
            or not title.strip()
            or len(title) > 300
        ):
            raise CatalogueImportError("invalid_job")
        if not isinstance(content, str) or not isinstance(url, str) or len(url) > 2048:
            raise CatalogueImportError("invalid_job")
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            raise CatalogueImportError("invalid_job_url")
        location = job.get("location")
        location = location.get("name") if isinstance(location, dict) else None
        if location is not None and (
            not isinstance(location, str) or len(location) > 240
        ):
            raise CatalogueImportError("invalid_location")
        # Office location is an explicit address label. Office name is only an
        # organization-defined identifier (e.g. GB-London), not a country fact.
        details = [{"name": location.strip(), "country": ""}] if location else []
        offices = job.get("offices", [])
        if not isinstance(offices, list):
            raise CatalogueImportError("invalid_location")
        metadata = job.get("metadata") or []
        location_fields = (
            [
                field.get("value")
                for field in metadata
                if isinstance(field, dict)
                and field.get("name") == "Locations"
                and field.get("value_type") == "multi_select"
            ]
            if isinstance(metadata, list)
            else []
        )
        explicit_locations = location_fields[0] if len(location_fields) == 1 else []
        if not isinstance(explicit_locations, list) or not all(
            isinstance(value, str) and value.strip() for value in explicit_locations
        ):
            explicit_locations = []
        for office in offices:
            if not isinstance(office, dict):
                raise CatalogueImportError("invalid_location")
            address = office.get("location")
            if address is None:
                continue
            if not isinstance(address, str) or len(address) > 240:
                raise CatalogueImportError("invalid_location")
            address = address.strip()
            if address and _office_matches_job(
                location, office, address, explicit_locations
            ):
                # The importer resolves this literal country/address component
                # against known country names; unrecognized cities stay unknown.
                detail = {
                    "name": address,
                    "country": address.rsplit(",", 1)[-1].strip(),
                }
                if detail not in details:
                    details.append(detail)
        parser = _Text()
        parser.feed(html.unescape(content))
        normalized.append(
            {
                "external_id": external_id,
                "title": title.strip(),
                "description": "\n".join(parser.parts),
                "url": url,
                "location": location.strip() if location else None,
                "location_details": details,
                "work_mode": "remote"
                if location
                and re.search(
                    r"\b(?:remote|télétravail|remoto|home.?office)\b",
                    location,
                    re.IGNORECASE,
                )
                else "unknown",
                "hash": hashlib.sha256(
                    json.dumps(
                        job, sort_keys=True, separators=(",", ":"), allow_nan=False
                    ).encode()
                ).hexdigest(),
                "raw": job,
            }
        )
        ids.add(external_id)
    return normalized


def fetch_snapshot(board_key):
    if not isinstance(board_key, str) or not re.fullmatch(
        r"[A-Za-z0-9_-]{1,240}", board_key
    ):
        raise CatalogueImportError("invalid_board_key")
    url = f"https://boards-api.greenhouse.io/v1/boards/{board_key}/jobs?content=true"
    try:
        with (
            httpx.Client(timeout=20, follow_redirects=False, trust_env=False) as client,
            client.stream(
                "GET", url, headers={"Accept": "application/json"}
            ) as response,
        ):
            if response.status_code != 200:
                error = CatalogueImportError("upstream_http_error")
                retry = response.headers.get("Retry-After", "")
                error.retry_after = min(int(retry), 86400) if retry.isdigit() else None
                raise error
            data = bytearray()
            for chunk in response.iter_bytes():
                data.extend(chunk)
                if len(data) > MAX_RESPONSE_BYTES:
                    raise CatalogueImportError("response_too_large")
        payload = json.loads(data)
        normalize_snapshot(
            payload
        )  # Validate the whole response before touching catalogue rows.
        return payload
    except (httpx.HTTPError, ValueError, TypeError, OverflowError) as exc:
        raise CatalogueImportError("upstream_invalid_response") from exc
