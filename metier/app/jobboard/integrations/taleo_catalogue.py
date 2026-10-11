"""IAEA's inspected public Taleo career search (read-only POST)."""

import json
import re
import time
from datetime import UTC, datetime
from html.parser import HTMLParser
from urllib.parse import unquote, urlencode

import httpx

from .greenhouse_catalogue import CatalogueImportError
from .icims_catalogue import eligible_row
from .personio_catalogue import html_text
from .public_catalogue import CatalogueSnapshot
from .public_html import fetch_html, validate_url
from .successfactors_catalogue import VOID_TAGS

HOST = "iaea.taleo.net"
BASE = f"https://{HOST}/careersection/ex"
MAX_PAGES = 10
MAX_DETAILS = 100


def parse_taleo_url(url):
    parts = validate_url(url, {HOST})
    if parts.path not in (
        "/careersection/ex",
        "/careersection/ex/",
        "/careersection/ex/jobsearch.ftl",
        "/careersection/ex/jobdetail.ftl",
    ):
        raise CatalogueImportError("expected_board_url")
    return {
        "provider": "taleo",
        "instance": "global",
        "board_key": "iaea-ex",
        "canonical": BASE + "/jobsearch.ftl",
    }


class Detail(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.history = ""
        self.fields = {
            "reqTitleLinkAction": [],
            "reqContestNumberValue": [],
            "descRequisitionContainer": [],
        }

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "input" and attributes.get("id") == "initialHistory":
            self.history = attributes.get("value", "")
        parent = self.stack[-1] if self.stack else ("", set(), False)
        field = dict(attrs).get("id", "").split(".")[-1]
        active = parent[1] | ({field} if field in self.fields else set())
        hidden = parent[2] or tag in ("script", "style")
        if tag in ("p", "div", "br", "li"):
            for name in active:
                self.fields[name].append("\n")
        if tag not in VOID_TAGS:
            self.stack.append((tag, active, hidden))

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break

    def handle_data(self, text):
        if self.stack and not self.stack[-1][2]:
            for name in self.stack[-1][1]:
                self.fields[name].append(text)

    def value(self, key):
        return "\n".join(
            " ".join(line.split())
            for line in "".join(self.fields[key]).splitlines()
            if line.strip()
        )


def normalize_job(job, html):
    from jobboard.services.engine_quality import structured_country_code

    identity = str(job.get("jobId", ""))
    if not re.fullmatch(r"[0-9]{1,30}", identity):
        raise CatalogueImportError("invalid_job_identity")
    parser = Detail()
    parser.feed(html)
    title = parser.value("reqTitleLinkAction")
    contest = parser.value("reqContestNumberValue").strip(" ()")
    description = parser.value("descRequisitionContainer")
    if not title:
        # Taleo hydrates its public HTML from a hidden serialized history field.
        # Map the observed field names; never execute the page's JavaScript.
        schema = re.search(
            r"descRequisition:\s*\{.*?_hlid:\s*\[([^]]+)\]", html, re.DOTALL
        )
        chunks = parser.history.split("!%24!")
        if (
            not schema
            or len(chunks) < 3
            or chunks[1]
            != "requisitionDescriptionInterface!|!descRequisition!|!rdPager"
        ):
            raise CatalogueImportError("job_detail_unconfirmed")
        names = re.findall(r"'([^']+)'", schema[1])
        values = chunks[2].split("!|!")
        if len(names) != len(values):
            raise CatalogueImportError("job_detail_unconfirmed")
        fields = dict(
            zip(
                names,
                (unquote(v).removeprefix("!*!").replace("\\:", ":") for v in values),
            )
        )
        if fields.get("reqlistitem.no") != identity:
            raise CatalogueImportError("job_detail_unconfirmed")
        title = fields.get("reqlistitem.title", "")
        contest = fields.get("reqlistitem.contestnumber", "")
        description = html_text(fields.get("reqlistitem.description", ""))
    if not title or not description or not contest or contest != job.get("contestNo"):
        raise CatalogueImportError("job_detail_unconfirmed")
    locations = []
    try:
        columns = job["column"]
        for index in job["locationsColumns"]:
            for location in json.loads(columns[index]):
                if not isinstance(location, str):
                    raise TypeError()
                segments = location.split("-")
                # The listing provides a location hierarchy, not free description.
                country = structured_country_code(segments[0])
                locations.append(
                    {
                        "name": ", ".join(dict.fromkeys(segments[1:])) or segments[0],
                        "country": country or "",
                    }
                )
        # This inspected board returns its closing column in UTC (request tz).
        closing = datetime.strptime(columns[2], "%Y-%m-%d, %I:%M:%S %p").replace(
            tzinfo=UTC
        )
        if closing <= datetime.now(UTC):
            return None
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise CatalogueImportError("invalid_job") from exc
    url = BASE + "/jobdetail.ftl?" + urlencode({"job": job["contestNo"], "lang": "en"})
    return eligible_row(
        {"listing": job, "description": description},
        identity,
        title,
        description,
        url,
        locations,
    )


def search(client, portal, page, deadline):
    payload = {
        "multilineEnabled": False,
        "sortingSelection": {
            "sortBySelectionParam": "3",
            "ascendingSortingOrder": "false",
        },
        "fieldData": {"fields": {"KEYWORD": "intern", "LOCATION": ""}, "valid": True},
        "filterSelectionParam": {"searchFilterSelections": []},
        "advancedSearchFiltersSelectionParam": {"searchFilterSelections": []},
        "pageNo": page,
    }
    if time.monotonic() >= deadline:
        raise CatalogueImportError("fetch_budget_exceeded")
    url = f"https://{HOST}/careersection/rest/jobboard/searchjobs?" + urlencode(
        {"lang": "en", "portal": portal}
    )
    try:
        with client.stream(
            "POST",
            url,
            json=payload,
            headers={"tz": "GMT+00:00", "tzname": "UTC", "Accept-Encoding": "identity"},
        ) as response:
            if response.status_code != 200:
                raise CatalogueImportError("public_http_error")
            body = bytearray()
            for chunk in response.iter_bytes():
                body.extend(chunk)
                if len(body) > 2 * 1024 * 1024:
                    raise CatalogueImportError("response_too_large")
                if time.monotonic() >= deadline:
                    raise CatalogueImportError("fetch_budget_exceeded")
        result = json.loads(body)
        if (
            not isinstance(result, dict)
            or not isinstance(result.get("requisitionList"), list)
            or result.get("careerSectionUnAvailable")
        ):
            raise CatalogueImportError("invalid_snapshot")
        return result
    except (httpx.HTTPError, ValueError) as exc:
        raise CatalogueImportError("upstream_invalid_response") from exc


def fetch_taleo(key):
    if key != "iaea-ex":
        raise CatalogueImportError("invalid_board_key")
    deadline = time.monotonic() + 300
    rows, seen = [], set()
    errors = [{"code": "keyword_search_partial"}]
    _, html = fetch_html(BASE + "/jobsearch.ftl", {HOST}, deadline=deadline)
    portal = re.search(r"portalNo\s*:\s*['\"]([0-9]+)['\"]", html)
    if not portal:
        raise CatalogueImportError("public_portal_unconfirmed")
    try:
        with httpx.Client(
            timeout=15, follow_redirects=False, trust_env=False
        ) as client:
            for page in range(1, MAX_PAGES + 1):
                result = search(client, portal[1], page, deadline)
                paging = result.get("pagingData", {})
                total = paging.get("totalCount")
                size = paging.get("pageSize")
                if (
                    not isinstance(total, int)
                    or not isinstance(size, int)
                    or size <= 0
                    or total < 0
                    or paging.get("currentPageNo") != page
                ):
                    raise CatalogueImportError("invalid_pagination")
                if not result["requisitionList"] and total > (page - 1) * size:
                    raise CatalogueImportError("invalid_pagination")
                for job in result["requisitionList"]:
                    identity = (
                        str(job.get("jobId", "")) if isinstance(job, dict) else ""
                    )
                    if not re.fullmatch(r"[0-9]{1,30}", identity) or identity in seen:
                        raise CatalogueImportError("invalid_job_identity")
                    if len(seen) >= MAX_DETAILS:
                        raise CatalogueImportError("detail_budget_exceeded")
                    if not isinstance(job.get("contestNo"), str) or not re.fullmatch(
                        r"[A-Za-z0-9_-]{1,100}", job["contestNo"]
                    ):
                        raise CatalogueImportError("invalid_job_identity")
                    seen.add(identity)
                    url = (
                        BASE
                        + "/jobdetail.ftl?"
                        + urlencode({"job": job["contestNo"], "lang": "en"})
                    )
                    final, detail = fetch_html(url, {HOST}, deadline=deadline)
                    if final != url:
                        raise CatalogueImportError("job_detail_unconfirmed")
                    try:
                        row = normalize_job(job, detail)
                        if row:
                            rows.append(row)
                    except CatalogueImportError as exc:
                        errors.append({"external_id": identity, "code": exc.code})
                if page * size >= total:
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
