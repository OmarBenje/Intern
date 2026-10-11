"""Public Ashby/Lever adapters. Fixed HTTPS hosts, no redirects or credentials.

Contracts: developers.ashbyhq.com/docs/public-job-posting-api and
https://github.com/lever/postings-api. Lever pagination is explicitly exhausted.
"""

import hashlib
import json
import re
import time
from urllib.parse import urlsplit

import httpx

from .greenhouse_catalogue import MAX_RESPONSE_BYTES, CatalogueImportError, _Text


class CatalogueSnapshot(list):
    """Valid rows plus explicit completeness; errors never imply absent postings."""

    def __init__(self, rows=(), *, complete=True, errors=()):
        super().__init__(rows)
        self.complete = complete
        self.errors = list(errors)[:500]


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def board_key(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,240}", value):
        raise CatalogueImportError("invalid_board_key")
    return value


def read_json(url, *, deadline=None):
    try:
        with (
            httpx.Client(timeout=20, follow_redirects=False, trust_env=False) as client,
            client.stream(
                "GET", url, headers={"Accept": "application/json"}
            ) as response,
        ):
            if response.status_code != 200:
                error = CatalogueImportError(
                    "upstream_rate_limited"
                    if response.status_code == 429
                    else "upstream_http_error"
                )
                error.status_code = response.status_code
                retry = response.headers.get("Retry-After", "")
                error.retry_after = min(int(retry), 86400) if retry.isdigit() else None
                raise error
            body = bytearray()
            for chunk in response.iter_bytes():
                if deadline is not None and time.monotonic() > deadline:
                    raise CatalogueImportError("snapshot_deadline_exceeded")
                body.extend(chunk)
                if len(body) > MAX_RESPONSE_BYTES:
                    raise CatalogueImportError("response_too_large")
        return json.loads(body)
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        raise CatalogueImportError("upstream_invalid_response") from exc


def _url(value):
    if not isinstance(value, str) or len(value) > 2048:
        raise CatalogueImportError("invalid_job_url")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise CatalogueImportError("invalid_job_url")
    return value


def _posting(job, identity, title, description, url, apply_url, locations):
    if not isinstance(identity, str) or not identity or len(identity) > 300:
        raise CatalogueImportError("invalid_job")
    if (
        not isinstance(title, str)
        or not title.strip()
        or len(title) > 300
        or not isinstance(description, str)
    ):
        raise CatalogueImportError("invalid_job")
    if not isinstance(locations, list) or any(
        not isinstance(x, str) or len(x) > 240 for x in locations
    ):
        raise CatalogueImportError("invalid_location")
    return {
        "external_id": identity,
        "title": title.strip(),
        "description": description,
        "url": _url(url),
        "apply_url": _url(apply_url),
        "location": locations[0] if locations else None,
        "locations": locations,
        "hash": digest(job),
        "raw": job,
    }


def _ashby_location(item):
    address = item.get("address") or {}
    if not isinstance(address, dict):
        raise CatalogueImportError("invalid_location")
    postal = address.get("postalAddress") or {}
    if not isinstance(postal, dict):
        raise CatalogueImportError("invalid_location")
    country = postal.get("addressCountry") or ""
    if not isinstance(country, str) or len(country) > 240:
        raise CatalogueImportError("invalid_location")
    return {"name": item["location"], "country": country}


def normalize_ashby(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
        raise CatalogueImportError("invalid_snapshot")
    result, seen = [], set()
    for job in payload["jobs"]:
        if not isinstance(job, dict):
            raise CatalogueImportError("invalid_job")
        # The API also exposes unlisted direct-link jobs; never publish them.
        if job.get("isListed") is False:
            continue
        url = _url(job.get("jobUrl"))
        identity = urlsplit(url).path.rstrip("/").split("/")[-1]
        locations = [job["location"]] if job.get("location") else []
        secondary = job.get("secondaryLocations", [])
        if not isinstance(secondary, list):
            raise CatalogueImportError("invalid_location")
        for item in secondary:
            if not isinstance(item, dict):
                raise CatalogueImportError("invalid_location")
            if item.get("location"):
                locations.append(item["location"])
        row = _posting(
            job,
            identity,
            job.get("title"),
            job.get("descriptionPlain", ""),
            url,
            job.get("applyUrl", url),
            locations,
        )
        row["location_details"] = (
            [_ashby_location(job)] if job.get("location") else []
        ) + [_ashby_location(item) for item in secondary if item.get("location")]
        if job.get("employmentType") == "Intern":
            row["contract_type"] = "internship"
        # Hybrid postings can also set isRemote=True; the enum is more precise.
        workplace = {"Hybrid": "hybrid", "OnSite": "onsite", "Remote": "remote"}.get(
            job.get("workplaceType")
        )
        if workplace:
            row["work_mode"] = workplace
        elif job.get("isRemote") is True:
            row["work_mode"] = "remote"
        if identity in seen:
            raise CatalogueImportError("duplicate_job")
        seen.add(identity)
        result.append(row)
    return result


def normalize_lever(payload):
    if not isinstance(payload, list):
        raise CatalogueImportError("invalid_snapshot")
    result, seen = [], set()
    for job in payload:
        if not isinstance(job, dict) or not isinstance(job.get("categories", {}), dict):
            raise CatalogueImportError("invalid_job")
        categories = job.get("categories", {})
        locations = categories.get("allLocations")
        if locations is None:
            locations = [categories["location"]] if categories.get("location") else []
        description = job.get("descriptionPlain", "")
        if not isinstance(description, str) or not isinstance(
            job.get("lists", []), list
        ):
            raise CatalogueImportError("invalid_job")
        for item in job.get("lists", []):
            if not isinstance(item, dict) or not isinstance(
                item.get("content", ""), str
            ):
                raise CatalogueImportError("invalid_job")
            parser = _Text()
            parser.feed(item.get("content", ""))
            description += (
                "\n" + str(item.get("text", "")) + "\n" + "\n".join(parser.parts)
            )
        extra = job.get("additionalPlain", "")
        if not isinstance(extra, str):
            raise CatalogueImportError("invalid_job")
        description += "\n" + extra
        row = _posting(
            job,
            job.get("id"),
            job.get("text"),
            description,
            job.get("hostedUrl"),
            job.get("applyUrl", job.get("hostedUrl")),
            locations,
        )
        country = job.get("country")
        primary = categories.get("location")
        if isinstance(country, str) and re.fullmatch(r"[A-Za-z]{2}", country):
            row["location_details"] = [
                {"name": label, "country": country.upper() if label == primary else ""}
                for label in locations
            ]
        # A generic label may hide a role-specific country list in the public text.
        from .lever_locations import explicit_role_locations

        if job.get("workplaceType") == "remote":
            row["work_mode"] = "remote"
        elif not job.get("country"):
            resolved = explicit_role_locations(
                job.get("descriptionPlain", ""), locations
            )
            if resolved:
                row["location_details"] = resolved["details"]
                row["locations"] = [place["name"] for place in resolved["details"]]
                row["location"] = row["locations"][0]
                row["raw"] = dict(
                    job,
                    location_resolution={
                        "method": "explicit_role_country_list_v1",
                        "source_field": "descriptionPlain",
                        "evidence": resolved["evidence"],
                        "locations": resolved["details"],
                    },
                )
                row["hash"] = digest(row["raw"])
        if row["external_id"] in seen:
            raise CatalogueImportError("duplicate_job")
        seen.add(row["external_id"])
        result.append(row)
    return result


def fetch_normalized(board):
    if board.provider == "eightfold" and board.instance == "global":
        from .eightfold_catalogue import fetch_eightfold

        return fetch_eightfold(
            board.board_key, checkpoint=getattr(board, "collection_checkpoint", None)
        )

    if board.provider == "teamtailor" and board.instance == "global":
        from .teamtailor_catalogue import fetch_teamtailor

        return fetch_teamtailor(board.board_key)
    if board.provider == "workable" and board.instance == "global":
        from .workable_catalogue import fetch_workable

        return fetch_workable(board.board_key)

    if board.provider == "icims" and board.instance == "global":
        from .icims_catalogue import fetch_icims

        return fetch_icims(board.board_key)
    if board.provider == "taleo" and board.instance == "global":
        from .taleo_catalogue import fetch_taleo

        return fetch_taleo(board.board_key)
    if board.provider == "successfactors" and board.instance == "global":
        from .successfactors_catalogue import fetch_successfactors

        return fetch_successfactors(board.board_key)
    if board.provider == "workday":
        from .workday_catalogue import fetch_workday_snapshot

        return fetch_workday_snapshot(board.board_key)
    key = board_key(board.board_key)
    if board.provider == "personio" and board.instance in ("de", "com"):
        from .personio_catalogue import fetch_personio

        return fetch_personio(key, board.instance)
    if board.provider == "recruitee" and board.instance == "global":
        from .recruitee_catalogue import fetch_recruitee

        return fetch_recruitee(key)
    if board.provider == "smartrecruiters" and board.instance == "global":
        return fetch_smartrecruiters(key)
    if board.provider == "ashby" and board.instance == "global":
        return normalize_ashby(
            read_json(f"https://api.ashbyhq.com/posting-api/job-board/{key}")
        )
    if board.provider == "lever" and board.instance in ("global", "eu"):
        host = "api.eu.lever.co" if board.instance == "eu" else "api.lever.co"
        rows = []
        response_bytes = 0
        for page in range(100):
            batch = read_json(
                f"https://{host}/v0/postings/{key}?mode=json&limit=100&skip={page * 100}"
            )
            if not isinstance(batch, list):
                raise CatalogueImportError("invalid_snapshot")
            response_bytes += len(json.dumps(batch).encode())
            if response_bytes > MAX_RESPONSE_BYTES:
                raise CatalogueImportError("response_too_large")
            rows.extend(batch)
            if len(batch) < 100:
                return normalize_lever(rows)
        raise CatalogueImportError("incomplete_snapshot")
    raise CatalogueImportError("board_not_configured")


# Scope v2 expands v1 with text-confirmed internships despite generic ATS
# employment labels. No existing in-scope contract is removed by this expansion.
# Full snapshots still cover only confirmed European non-remote internships.
SMARTRECRUITERS_SCOPE = "europe-confirmed-internships-onsite-hybrid-v2"
SMARTRECRUITERS_MAX_DETAILS = 1000
SMARTRECRUITERS_MAX_BYTES = 80 * 1024 * 1024
SMARTRECRUITERS_DEADLINE_SECONDS = 600


def _smart_in_scope(job):
    from jobboard.services.engine_quality import (
        APPRENTICESHIP_TITLE,
        EUROPE_COUNTRIES,
        INTERN,
        NEGATIVE_TITLE,
    )

    if not isinstance(job, dict):
        raise CatalogueImportError("invalid_job")
    location = job.get("location")
    contract = job.get("typeOfEmployment") or {}
    if not isinstance(location, dict) or not isinstance(contract, dict):
        raise CatalogueImportError("invalid_job")
    country = location.get("country")
    if not isinstance(country, str):
        raise CatalogueImportError("invalid_location")
    return (
        (
            contract.get("id") == "intern"
            or (
                isinstance(job.get("name"), str)
                and re.search(INTERN, job["name"], re.IGNORECASE)
                and not re.search(NEGATIVE_TITLE, job["name"], re.IGNORECASE)
                and not re.search(APPRENTICESHIP_TITLE, job["name"], re.IGNORECASE)
            )
        )
        and country.upper() in EUROPE_COUNTRIES
        and location.get("remote") is False
        and job.get("visibility", "PUBLIC") == "PUBLIC"
    )


def normalize_smartrecruiters(job):
    if not _smart_in_scope(job):
        raise CatalogueImportError("snapshot_changed")
    location = job["location"]
    label = (
        location.get("fullLocation")
        or location.get("city")
        or location["country"].upper()
    )
    ad = job.get("jobAd")
    if not isinstance(ad, dict) or not isinstance(ad.get("sections"), dict):
        raise CatalogueImportError("invalid_job")
    parts = []
    for section_name, section in ad["sections"].items():
        # SmartRecruiters also supplies a videos section with URLs, not text.
        if section_name == "videos":
            continue
        if not isinstance(section, dict) or not isinstance(section.get("text"), str):
            raise CatalogueImportError("invalid_job")
        parser = _Text()
        parser.feed(section["text"])
        parts.append("\n".join(parser.parts))
    description = "\n\n".join(parts)
    if not description.strip():
        raise CatalogueImportError("invalid_job")
    row = _posting(
        job,
        job.get("id"),
        job.get("name"),
        description,
        job.get("postingUrl"),
        job.get("applyUrl"),
        [label],
    )
    from jobboard.services.engine_quality import extract_facts

    contract = (
        "internship"
        if (job.get("typeOfEmployment") or {}).get("id") == "intern"
        else "unknown"
    )
    if (
        extract_facts(row["title"], description, contract_type=contract)[
            "classification"
        ]
        != "confirmed"
    ):
        return None
    row["contract_type"] = contract
    row["work_mode"] = "hybrid" if location.get("hybrid") is True else "onsite"
    row["location_details"] = [{"name": label, "country": location["country"].upper()}]
    row["published_at"] = job.get("releasedDate")
    return row


def fetch_smartrecruiters(key):
    key = board_key(key)
    base = f"https://api.smartrecruiters.com/v1/companies/{key}/postings"
    deadline = time.monotonic() + SMARTRECRUITERS_DEADLINE_SECONDS
    total_bytes = 0

    def read(url):
        nonlocal total_bytes
        if time.monotonic() >= deadline:
            raise CatalogueImportError("snapshot_deadline_exceeded")
        payload = read_json(url, deadline=deadline)
        total_bytes += len(json.dumps(payload).encode())
        if total_bytes > SMARTRECRUITERS_MAX_BYTES:
            raise CatalogueImportError("response_too_large")
        return payload

    ids, selected = set(), []
    errors = []
    total = None
    offset = 0
    for _ in range(200):
        payload = read(f"{base}?limit=100&offset={offset}")
        if (
            not isinstance(payload, dict)
            or not isinstance(payload.get("content"), list)
            or type(payload.get("totalFound")) is not int
            or payload["totalFound"] < 0
            or payload.get("offset") != offset
        ):
            raise CatalogueImportError("invalid_snapshot")
        if total is None:
            total = payload["totalFound"]
        if total != payload["totalFound"]:
            errors.append({"code": "snapshot_changed"})
            total = payload["totalFound"]
        batch = payload["content"]
        if len(batch) > 100:
            raise CatalogueImportError("invalid_snapshot")
        if offset + len(batch) > total:
            errors.append({"code": "snapshot_changed"})
        for job in batch:
            if not isinstance(job, dict):
                raise CatalogueImportError("invalid_job")
            identity = job.get("id")
            if not isinstance(identity, str) or not re.fullmatch(
                r"[0-9]{1,30}", identity
            ):
                raise CatalogueImportError("invalid_job")
            if identity in ids:
                errors.append({"external_id": identity, "code": "duplicate_job"})
                continue
            ids.add(identity)
            if _smart_in_scope(job):
                selected.append(identity)
                if len(selected) > SMARTRECRUITERS_MAX_DETAILS:
                    raise CatalogueImportError("incomplete_snapshot")
        offset += len(batch)
        if offset >= total:
            break
        if not batch:
            raise CatalogueImportError("incomplete_snapshot")
    else:
        raise CatalogueImportError("incomplete_snapshot")
    rows = []
    for identity in selected:
        # Never follow the upstream ref URL, even if the listing supplied one.
        try:
            job = read(f"{base}/{identity}")
            if not isinstance(job, dict) or job.get("id") != identity:
                raise CatalogueImportError("snapshot_changed")
            row = normalize_smartrecruiters(job)
            if row is not None:
                rows.append(row)
        except CatalogueImportError as exc:
            errors.append({"external_id": identity, "code": exc.code})
            if exc.code in (
                "snapshot_deadline_exceeded",
                "response_too_large",
                "upstream_rate_limited",
            ):
                break
    return CatalogueSnapshot(rows, complete=not errors, errors=errors)
