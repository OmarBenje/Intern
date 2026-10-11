"""Public Recruitee career feed. Auth-required sites fall back to public XML.

https://docs.recruitee.com/reference/authentication-1
https://support.recruitee.com/en/articles/8213076-faq-api
"""

from .greenhouse_catalogue import CatalogueImportError
from .personio_catalogue import html_text, read_xml, xml_root
from .public_catalogue import CatalogueSnapshot, _posting, board_key, read_json


def normalize_recruitee(payload):
    if (
        not isinstance(payload, dict)
        or not isinstance(payload.get("offers"), list)
        or len(payload["offers"]) > 20000
    ):
        raise CatalogueImportError("invalid_snapshot")
    rows, errors, seen = [], [], set()
    for job in payload["offers"]:
        if not isinstance(job, dict) or not isinstance(job.get("id"), (str, int)):
            raise CatalogueImportError("invalid_job_identity")
        identity = str(job["id"])
        if not identity or identity in seen:
            raise CatalogueImportError("duplicate_job")
        seen.add(identity)
        try:
            locations = job.get("locations") or [
                {
                    "city": job.get("city", ""),
                    "country": job.get("country", ""),
                    "country_code": job.get("country_code", ""),
                }
            ]
            details = []
            for place in locations:
                label = ", ".join(
                    x for x in [place.get("city"), place.get("country")] if x
                )
                if label:
                    details.append(
                        {
                            "name": label,
                            "country": place.get("country_code")
                            or place.get("country", ""),
                        }
                    )
            description = html_text(
                (job.get("description") or "") + "\n" + (job.get("requirements") or "")
            )
            row = _posting(
                job,
                identity,
                job.get("title"),
                description,
                job.get("careers_url"),
                job.get("careers_apply_url") or job.get("careers_url"),
                [x["name"] for x in details],
            )
            row["location_details"] = details
            if job.get("employment_type_code") == "internship":
                row["contract_type"] = "internship"
            row["work_mode"] = (
                "remote"
                if job.get("remote") is True
                else "hybrid"
                if job.get("hybrid") is True
                else "unknown"
            )
            rows.append(row)
        except (CatalogueImportError, TypeError, AttributeError) as exc:
            errors.append(
                {
                    "external_id": identity,
                    "code": exc.code
                    if isinstance(exc, CatalogueImportError)
                    else "invalid_job",
                }
            )
    return CatalogueSnapshot(rows, complete=not errors, errors=errors)


def normalize_recruitee_xml(payload, key):
    root = xml_root(payload, "offers")
    jobs = []
    for node in root:
        if node.tag != "offer":
            raise CatalogueImportError("invalid_snapshot")
        job = {child.tag: child.text or "" for child in node}
        slug = job.get("slug", "")
        if not slug or "/" in slug or "?" in slug or "#" in slug:
            raise CatalogueImportError("invalid_job_identity")
        job["careers_url"] = f"https://{key}.recruitee.com/o/{slug}"
        job["remote"] = job.get("remote") == "true"
        job["hybrid"] = job.get("hybrid") == "true"
        jobs.append(job)
    return normalize_recruitee({"offers": jobs})


def fetch_recruitee(key):
    key = board_key(key)
    base = f"https://{key}.recruitee.com"
    try:
        payload = read_json(f"{base}/api/offers/")
    except CatalogueImportError as exc:
        # No credentials or access-control bypass: the separate public XML feed
        # is explicitly outside the Careers API token scope.
        if exc.code != "upstream_http_error":
            raise
        return normalize_recruitee_xml(read_xml(f"{base}/api/feeds/offers.xml"), key)
    return normalize_recruitee(payload)
