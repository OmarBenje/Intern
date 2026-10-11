"""Personio's opt-in public XML feed; no credentialed recruiting API.

https://support.personio.de/hc/en-us/articles/207576365
"""

import re
import time
import xml.etree.ElementTree as ET

import httpx

from .greenhouse_catalogue import MAX_RESPONSE_BYTES, CatalogueImportError, _Text
from .public_catalogue import CatalogueSnapshot, _posting, board_key, digest
from .public_html import PublicHTMLParser, fetch_html


def read_xml(url):
    deadline = time.monotonic() + 30
    try:
        with httpx.Client(
            timeout=10, follow_redirects=False, trust_env=False
        ) as client:
            with client.stream(
                "GET", url, headers={"Accept": "application/xml"}
            ) as response:
                if response.status_code != 200:
                    raise CatalogueImportError("upstream_http_error")
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_RESPONSE_BYTES:
                        raise CatalogueImportError("response_too_large")
                    if time.monotonic() > deadline:
                        raise CatalogueImportError("snapshot_deadline_exceeded")
        return bytes(body)
    except httpx.HTTPError as exc:
        raise CatalogueImportError("upstream_invalid_response") from exc


def xml_root(payload, expected):
    # UTF-8 only, rejecting declarations before XML parsing prevents external entities
    # and entity expansion, including UTF-16 tricks against byte-pattern guards.
    try:
        text = payload.decode("utf-8-sig") if isinstance(payload, bytes) else payload
        if (
            len(text.encode()) > MAX_RESPONSE_BYTES
            or re.search(r"<!\s*(DOCTYPE|ENTITY)", text, re.I)
            or "\x00" in text
        ):
            raise CatalogueImportError("unsafe_xml")
        root = ET.fromstring(text)
    except (UnicodeError, ET.ParseError, TypeError) as exc:
        raise CatalogueImportError("invalid_xml") from exc
    if root.tag != expected or len(root) > 20000:
        raise CatalogueImportError("invalid_snapshot")
    return root


def html_text(value):
    parser = _Text()
    parser.feed(value)
    return "\n".join(parser.parts)


def normalize_personio(payload, key, instance):
    root = xml_root(payload, "workzag-jobs")
    rows, errors, seen = [], [], set()
    for job in root:
        if job.tag != "position":
            raise CatalogueImportError("invalid_snapshot")
        identity = job.findtext("id", "")
        if not re.fullmatch(r"[0-9]{1,30}", identity) or identity in seen:
            raise CatalogueImportError("invalid_job_identity")
        seen.add(identity)
        raw = {child.tag: "".join(child.itertext()) for child in job}
        try:
            description = "\n".join(
                html_text("".join(node.itertext()))
                for node in job.findall("jobDescriptions/jobDescription")
            )
            office = job.findtext("office", "")
            offices = [office] if office else []
            offices += [
                n.text for n in job.findall("additionalOffices/office") if n.text
            ]
            url = f"https://{key}.jobs.personio.{instance}/job/{identity}"
            row = _posting(
                raw, identity, job.findtext("name"), description, url, url, offices
            )
            # 'student' includes working-student jobs: only internship is conclusive.
            if job.findtext("employmentType") in ("intern", "internship"):
                row["contract_type"] = "internship"
            row["location_details"] = [
                {"name": name, "country": job.findtext("country", "")}
                for name in offices
            ]
            rows.append(row)
        except CatalogueImportError as exc:
            errors.append({"external_id": identity, "code": exc.code})
    return CatalogueSnapshot(rows, complete=not errors, errors=errors)


def fetch_personio(key, instance):
    key = board_key(key)
    if instance not in ("de", "com"):
        raise CatalogueImportError("invalid_instance")
    snapshot = normalize_personio(
        read_xml(f"https://{key}.jobs.personio.{instance}/xml"), key, instance
    )
    rows, errors = [], list(snapshot.errors)
    deadline = time.monotonic() + 300
    detail_count = 0
    from jobboard.services.engine_quality import INTERN

    for row in snapshot:
        if row.get("contract_type") != "internship" and not re.search(
            INTERN, row["title"], re.I
        ):
            rows.append(row)
            continue
        try:
            detail_count += 1
            if detail_count > 120 or time.monotonic() >= deadline:
                raise CatalogueImportError("detail_budget_exceeded")
            _, html = fetch_html(
                row["url"],
                {f"{key}.jobs.personio.{instance}"},
                deadline=min(deadline, time.monotonic() + 25),
            )
            parser = PublicHTMLParser()
            parser.feed(html)
            matches = [
                x
                for x in parser.documents
                if isinstance(x, dict)
                and x.get("@type") == "JobPosting"
                and x.get("title", "").strip() == row["title"]
            ]
            if len(matches) != 1:
                raise CatalogueImportError("job_detail_unconfirmed")
            detail = matches[0]
            row["description"] = html_text(detail.get("description") or "")
            places = detail.get("jobLocation") or []
            if isinstance(places, dict):
                places = [places]
            locations = []
            for place in places:
                address = place.get("address", {})
                country = address.get("addressCountry", "")
                if isinstance(country, dict):
                    country = country.get("name", "")
                city = address.get("addressLocality", "")
                if not isinstance(country, str) or not isinstance(city, str):
                    raise CatalogueImportError("invalid_location")
                label = ", ".join(x for x in (city, country) if x)
                if len(label) > 240 or len(country) > 240:
                    raise CatalogueImportError("invalid_location")
                if label:
                    locations.append({"name": label, "country": country})
            if locations:
                row["location_details"] = locations
                row["locations"] = [x["name"] for x in locations]
                row["location"] = row["locations"][0]
            if detail.get("jobLocationType") == "TELECOMMUTE":
                row["work_mode"] = "remote"
            row["raw"] = {"xml": row["raw"], "job_posting": detail}
            row["hash"] = digest(row["raw"])
            rows.append(row)
        except (CatalogueImportError, AttributeError, TypeError) as exc:
            errors.append(
                {
                    "external_id": row["external_id"],
                    "code": exc.code
                    if isinstance(exc, CatalogueImportError)
                    else "invalid_job_detail",
                }
            )
    return CatalogueSnapshot(rows, complete=not errors, errors=errors)
