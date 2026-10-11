"""Public RMK career pages from inspected employers, not the recruiting API."""

import re
import time
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit

from .greenhouse_catalogue import CatalogueImportError
from .public_catalogue import CatalogueSnapshot, _posting
from .public_html import PublicHTMLParser, fetch_html, validate_url

BOARDS = {
    "sap": ("careers.sap.com", "SAP"),
    "schaeffler": ("jobs.schaeffler.com", "Schaeffler"),
    "zf": ("jobs.zf.com", "ZF Group"),
}
TERMS = ("internship", "Praktikum", "stage", "tirocinio")
MAX_PAGES_PER_TERM = 4
MAX_DETAILS = 240
MAX_BYTES = 80 * 1024 * 1024
DEADLINE_SECONDS = 600
VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}


def parse_successfactors_url(url):
    host = urlsplit(url).hostname
    for key, (allowed, _) in BOARDS.items():
        if host == allowed:
            parts = validate_url(url, {allowed})
            if parts.query or not (
                parts.path in ("", "/", "/search", "/search/")
                or re.fullmatch(r"/job/[^/]+/[0-9]+/?", parts.path)
            ):
                raise CatalogueImportError("expected_board_url")
            return {
                "provider": "successfactors",
                "instance": "global",
                "board_key": key,
                "canonical": f"https://{allowed}",
            }
    raise CatalogueImportError("unsupported_source_url")


class JobPage(HTMLParser):
    """Read only the employer's JobPosting scope; ignore navigation and scripts."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.posting = False
        self.fields = {"title": [], "description": []}
        self.addresses = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        parent = self.stack[-1] if self.stack else ("", False, "", False)
        scoped = parent[1] or attrs.get("itemtype", "").rstrip("/").endswith(
            "schema.org/JobPosting"
        )
        if scoped:
            self.posting = True
        field = attrs.get("data-careersite-propertyid") or attrs.get("itemprop")
        field = field if field in self.fields else parent[2]
        hidden = parent[3] or tag in ("script", "style")
        if scoped and attrs.get("itemprop") == "address":
            self.addresses.append({})
        if scoped and tag == "meta" and self.addresses:
            prop = attrs.get("itemprop")
            if prop in ("addressCountry", "addressLocality", "streetAddress"):
                self.addresses[-1][prop] = attrs.get("content", "")
        if (
            scoped
            and field == "description"
            and tag in ("p", "div", "br", "li", "h2", "h3")
        ):
            self.fields[field].append("\n")
        if tag not in VOID_TAGS:
            self.stack.append((tag, scoped, field, hidden))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        if self.stack:
            _, scoped, field, hidden = self.stack[-1]
            if scoped and field in self.fields and not hidden:
                self.fields[field].append(data)


class SearchPage(PublicHTMLParser):
    def __init__(self):
        super().__init__()
        self.anchor = None
        self.labels = {}

    def handle_starttag(self, tag, attrs):
        super().handle_starttag(tag, attrs)
        if tag == "a":
            self.anchor = dict(attrs).get("href")

    def handle_endtag(self, tag):
        super().handle_endtag(tag)
        if tag == "a":
            self.anchor = None

    def handle_data(self, data):
        super().handle_data(data)
        if self.anchor:
            self.labels[self.anchor] = self.labels.get(self.anchor, "") + data


INTERNSHIP_TITLE = re.compile(
    r"\b(?:intern(?:ship)?s?|stage|stagiaire|praktik(?:um|ant|antin)|pflichtpraktikum|freiwilligespraktikum|tirocinio|tirocinante|stagista)\b",
    re.IGNORECASE,
)


def normalize_job(html, url, key):
    from jobboard.services.engine_quality import extract_facts, structured_country_code

    host = BOARDS[key][0]
    parts = validate_url(url, {host})
    identity = re.fullmatch(r"/job/[^/]+/([0-9]+)/?", parts.path)
    if not identity:
        raise CatalogueImportError("invalid_job_url")
    parser = JobPage()
    parser.feed(html)
    title = " ".join("".join(parser.fields["title"]).split())
    description = "\n".join(
        line.strip()
        for line in "".join(parser.fields["description"]).splitlines()
        if line.strip()
    )
    if not parser.posting or not title or not description:
        raise CatalogueImportError("job_detail_unconfirmed")
    locations = []
    for address in parser.addresses:
        country = address.get("addressCountry", "")
        name = address.get("addressLocality", "") or address.get("streetAddress", "")
        if not country and address.get("streetAddress"):
            # RMK streetAddress explicitly encodes city, [region,] ISO country,
            # [postal code]. Never infer a country from a city name.
            tokens = [part.strip() for part in address["streetAddress"].split(",")]
            tail = tokens[-1:]
            if len(tokens) >= 3:
                tail.append(tokens[-2])
            country = next(
                (
                    token
                    for token in tail
                    if re.fullmatch(r"[A-Z]{2}", token)
                    and structured_country_code(token)
                ),
                "",
            )
        if name:
            locations.append({"name": name, "country": country})
    raw = {
        "provider": "successfactors",
        "url": url,
        "title": title,
        "description": description,
        "addresses": parser.addresses,
        "location_details": locations,
    }
    row = _posting(
        raw,
        identity[1],
        title,
        description,
        url,
        url,
        [location["name"] for location in locations],
    )
    row["location_details"] = locations
    quality = extract_facts(
        title,
        description,
        locations=[
            {
                "name": place["name"],
                "country_code": structured_country_code(place["country"]),
            }
            for place in locations
        ],
    )
    # Keep publication gating common to all sources; this prefilter avoids
    # importing unrelated jobs matched by 'stage' in their description.
    if (
        quality["classification"] != "confirmed"
        or quality["europe_status"] != "in_scope"
    ):
        return None
    return row


def fetch_successfactors(key):
    if key not in BOARDS:
        raise CatalogueImportError("invalid_board_key")
    host = BOARDS[key][0]
    base = f"https://{host}"
    deadline = time.monotonic() + DEADLINE_SECONDS
    total_bytes = 0
    seen = set()
    rows = []
    errors = [{"code": "keyword_search_partial"}]

    def read(url):
        nonlocal total_bytes
        final, html = fetch_html(url, {host}, deadline=deadline)
        total_bytes += len(html.encode())
        if total_bytes > MAX_BYTES:
            raise CatalogueImportError("response_too_large")
        return final, html

    for term in TERMS:
        offset = 0
        visited = set()
        for _ in range(MAX_PAGES_PER_TERM):
            search_url = base + "/search/?" + urlencode({"q": term, "startrow": offset})
            try:
                final, html = read(search_url)
                parser = SearchPage()
                parser.feed(html)
                links = []
                offsets = []
                for link in parser.links:
                    absolute = urljoin(final, link)
                    parts = urlsplit(absolute)
                    if parts.scheme != "https" or parts.hostname != host:
                        continue
                    match = re.fullmatch(r"/job/[^/]+/([0-9]+)/?", parts.path)
                    label = parser.labels.get(link, "").strip()
                    if match and label and not INTERNSHIP_TITLE.search(label):
                        continue
                    if match and match[1] not in seen:
                        validate_url(absolute, {host})
                        seen.add(match[1])
                        links.append((match[1], absolute))
                    params = parse_qs(parts.query)
                    start = params.get("startrow", [""])[0]
                    if (
                        parts.path == "/search/"
                        and params.get("q") == [term]
                        and start.isdecimal()
                        and offset < int(start) <= 10000
                    ):
                        offsets.append(int(start))
                for identity, url in links:
                    if len(seen) > MAX_DETAILS:
                        errors.append({"code": "detail_budget_exceeded"})
                        return CatalogueSnapshot(rows, complete=False, errors=errors)
                    try:
                        final, detail = read(url)
                        if urlsplit(final).path.rstrip("/").split("/")[-1] != identity:
                            raise CatalogueImportError("job_detail_unconfirmed")
                        row = normalize_job(detail, final, key)
                        if row:
                            rows.append(row)
                    except CatalogueImportError as exc:
                        errors.append({"external_id": identity, "code": exc.code})
                        if exc.code not in (
                            "job_detail_unconfirmed",
                            "invalid_job",
                            "invalid_location",
                        ):
                            if not rows:
                                raise
                            return CatalogueSnapshot(
                                rows, complete=False, errors=errors
                            )
                visited.add(offset)
                next_offset = min(offsets) if offsets else None
                if next_offset is None or next_offset in visited:
                    break
                offset = next_offset
            except CatalogueImportError as exc:
                if not rows:
                    raise
                errors.append({"query": term, "code": exc.code})
                return CatalogueSnapshot(rows, complete=False, errors=errors)
        else:
            errors.append({"query": term, "code": "page_budget_exceeded"})
    return CatalogueSnapshot(rows, complete=False, errors=errors)
