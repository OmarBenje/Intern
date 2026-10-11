"""Public no-key discovery feeds; these records never publish catalogue offers.

Arbeitnow: https://www.arbeitnow.com/blog/job-board-api (attribution retained).
JobSearch: https://jobsearch.api.jobtechdev.se/ (country taxonomy is not ISO).
"""

from dataclasses import dataclass
from urllib.parse import urlencode

from .greenhouse_catalogue import CatalogueImportError
from .public_catalogue import read_json


@dataclass
class FeedPage:
    records: list
    next_cursor: str
    total: int | None


def fetch_page(query, deadline):
    if query.provider == "linkedin_public":
        from .linkedin_discovery import fetch_linkedin

        return fetch_linkedin(query, deadline)
    try:
        cursor = int(query.cursor or (1 if query.provider == "arbeitnow" else 0))
    except ValueError as exc:
        raise CatalogueImportError("invalid_discovery_cursor") from exc
    if cursor < 0 or cursor > 100000:
        raise CatalogueImportError("invalid_discovery_cursor")
    if query.provider == "arbeitnow":
        payload = read_json(
            "https://www.arbeitnow.com/api/job-board-api?"
            + urlencode({"page": cursor}),
            deadline=deadline,
        )
        if not isinstance(payload, dict):
            raise CatalogueImportError("invalid_discovery_feed")
        rows = payload.get("data")
        if not isinstance(rows, list) or len(rows) > 2000:
            raise CatalogueImportError("invalid_discovery_feed")
        # Never follow an upstream next URL: only advance our fixed-host page index.
        links = payload.get("links") or {}
        if not isinstance(links, dict) or any(
            not isinstance(row, dict) for row in rows
        ):
            raise CatalogueImportError("invalid_discovery_feed")
        more = bool(links.get("next"))
        records = [
            {
                "id": str(row.get("slug", "")),
                "url": row.get("url", ""),
                "company": row.get("company_name", ""),
                "raw": row,
            }
            for row in rows
            if isinstance(row, dict)
        ]
        return FeedPage(records, str(cursor + 1) if more and rows else "", None)
    if query.provider == "jobsearch_se":
        params = {"q": query.term, "limit": 100, "offset": cursor}
        payload = read_json(
            "https://jobsearch.api.jobtechdev.se/search?" + urlencode(params),
            deadline=deadline,
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("total"), dict):
            raise CatalogueImportError("invalid_discovery_feed")
        rows, total = payload.get("hits"), payload.get("total", {}).get("value")
        if (
            not isinstance(rows, list)
            or len(rows) > 100
            or type(total) is not int
            or total < 0
        ):
            raise CatalogueImportError("invalid_discovery_feed")
        records = []
        for row in rows:
            if not isinstance(row, dict):
                raise CatalogueImportError("invalid_discovery_feed")
            application = row.get("application_details") or {}
            employer = row.get("employer") or {}
            if not isinstance(application, dict) or not isinstance(employer, dict):
                raise CatalogueImportError("invalid_discovery_feed")
            records.append(
                {
                    "id": str(row.get("id", "")),
                    "url": application.get("url")
                    or employer.get("url")
                    or row.get("webpage_url", ""),
                    "company": employer.get("name", ""),
                    "raw": row,
                }
            )
        return FeedPage(
            records,
            str(cursor + len(rows)) if rows and cursor + len(rows) < total else "",
            total,
        )
    raise CatalogueImportError("unsupported_discovery_provider")
