"""Public Workable widget + Markdown details, sequential and bounded."""

import json
import re
import time

import httpx

from .greenhouse_catalogue import CatalogueImportError
from .public_catalogue import CatalogueSnapshot, _posting
from .teamtailor_catalogue import tenant

MAX_DETAILS = 120


def read_public(url, deadline):
    try:
        with (
            httpx.Client(timeout=15, follow_redirects=False, trust_env=False) as client,
            client.stream(
                "GET",
                url,
                headers={
                    "User-Agent": "InternCatalogue/1.0",
                    "Accept": "application/json,text/markdown",
                },
            ) as response,
        ):
            if response.status_code != 200:
                raise CatalogueImportError(
                    "upstream_rate_limited"
                    if response.status_code == 429
                    else "upstream_http_error"
                )
            body = bytearray()
            for chunk in response.iter_bytes():
                body.extend(chunk)
                if len(body) > 2 * 1024 * 1024:
                    raise CatalogueImportError("response_too_large")
                if time.monotonic() >= deadline:
                    raise CatalogueImportError("snapshot_deadline_exceeded")
        return body.decode("utf-8")
    except (httpx.HTTPError, UnicodeError) as exc:
        raise CatalogueImportError("upstream_invalid_response") from exc


def normalize_workable(payload, key, detail_reader):
    if (
        not isinstance(payload, dict)
        or not isinstance(payload.get("jobs"), list)
        or len(payload["jobs"]) > 20000
    ):
        raise CatalogueImportError("invalid_snapshot")
    grouped = {}
    for job in payload["jobs"]:
        if not isinstance(job, dict):
            raise CatalogueImportError("invalid_job")
        identity = job.get("shortcode") or job.get("code")
        if not isinstance(identity, str) or not re.fullmatch(
            r"[A-Za-z0-9]{1,40}", identity
        ):
            raise CatalogueImportError("invalid_job_identity")
        grouped.setdefault(identity, []).append(job)
    rows, errors = [], []
    from jobboard.services.engine_quality import INTERN

    for identity, jobs in grouped.items():
        job = jobs[0]
        title = job.get("title")
        if not isinstance(title, str):
            errors.append({"external_id": identity, "code": "invalid_job"})
            continue
        contract = str(job.get("type") or job.get("employment_type") or "").lower()
        # Trainee, graduate and working student do not imply internship.
        if contract not in ("internship", "intern") and not re.search(
            INTERN, title, re.IGNORECASE
        ):
            continue
        if len(rows) + len(errors) >= MAX_DETAILS:
            errors.append({"external_id": identity, "code": "detail_budget_exceeded"})
            break
        try:
            if any(j.get("title") != title for j in jobs):
                raise CatalogueImportError("conflicting_identity")
            details = []
            for j in jobs:
                places = j.get("locations") or [j]
                if not isinstance(places, list):
                    raise CatalogueImportError("invalid_location")
                for place in places:
                    country = place.get("country") or ""
                    city = place.get("city") or ""
                    if (
                        not isinstance(country, str)
                        or not isinstance(city, str)
                        or len(country) > 240
                    ):
                        raise CatalogueImportError("invalid_location")
                    label = ", ".join(x for x in (city, country) if x)
                    if label and {"name": label, "country": country} not in details:
                        details.append({"name": label, "country": country})
            description = detail_reader(
                f"https://apply.workable.com/{key}/jobs/view/{identity}.md"
            )
            if len(description.strip()) < 40 or re.search(
                r"<(?:!doctype|html)\b", description, re.IGNORECASE
            ):
                raise CatalogueImportError("invalid_job_detail")
            url = f"https://apply.workable.com/{key}/j/{identity}/"
            row = _posting(
                {"listings": jobs, "markdown": description},
                identity,
                title,
                description,
                url,
                url,
                [x["name"] for x in details],
            )
            row["location_details"] = details
            if contract in ("internship", "intern"):
                row["contract_type"] = "internship"
            row["work_mode"] = (
                "remote"
                if any(
                    j.get("telecommuting") is True or j.get("remote") is True
                    for j in jobs
                )
                else "unknown"
            )
            rows.append(row)
        except (CatalogueImportError, AttributeError, TypeError) as exc:
            code = exc.code if isinstance(exc, CatalogueImportError) else "invalid_job"
            errors.append({"external_id": identity, "code": code})
            if code in (
                "upstream_rate_limited",
                "snapshot_deadline_exceeded",
                "response_too_large",
            ):
                break
    return CatalogueSnapshot(rows, complete=False, errors=errors)


def fetch_workable(key):
    key = tenant(key)
    deadline = time.monotonic() + 300
    used = 0

    def read(url):
        nonlocal used
        if time.monotonic() >= deadline:
            raise CatalogueImportError("snapshot_deadline_exceeded")
        text = read_public(url, deadline)
        used += len(text.encode())
        if used > 20 * 1024 * 1024:
            raise CatalogueImportError("response_too_large")
        return text

    try:
        payload = json.loads(
            read(f"https://apply.workable.com/api/v1/widget/accounts/{key}")
        )
    except ValueError as exc:
        raise CatalogueImportError("invalid_snapshot") from exc
    return normalize_workable(payload, key, read)
