"""Opt-in guest HTML discovery, not an official LinkedIn API.

Search markup and its public See more jobs JS verified 2026-09-30.
No account, cookies, challenge solving, tracking-link unwrap or application action.
"""

import re
import time
from html.parser import HTMLParser
from urllib.parse import urlencode, urlsplit, urlunsplit

import httpx

from .greenhouse_catalogue import CatalogueImportError

COUNTRIES = {
    "FR": ("France", "fr", "stage"),
    "DE": ("Germany", "de", "Praktikum"),
    "GB": ("United Kingdom", "en", "internship"),
    "IE": ("Ireland", "en", "internship"),
    "ES": ("Spain", "es", "prácticas"),
    "IT": ("Italy", "it", "tirocinio"),
    "NL": ("Netherlands", "nl", "stage"),
    "BE": ("Belgium", "fr", "stage"),
    "LU": ("Luxembourg", "fr", "stage"),
    "CH": ("Switzerland", "de", "Praktikum"),
    "AT": ("Austria", "de", "Praktikum"),
    "PT": ("Portugal", "pt", "estágio"),
    "PL": ("Poland", "pl", "staż"),
    "SE": ("Sweden", "sv", "praktik"),
    "NO": ("Norway", "no", "internship"),
    "DK": ("Denmark", "da", "praktik"),
    "FI": ("Finland", "fi", "harjoittelu"),
    "IS": ("Iceland", "en", "internship"),
    "CZ": ("Czechia", "cs", "stáž"),
    "SK": ("Slovakia", "sk", "stáž"),
    "HU": ("Hungary", "hu", "gyakornok"),
    "RO": ("Romania", "ro", "internship"),
    "BG": ("Bulgaria", "bg", "стаж"),
    "HR": ("Croatia", "hr", "internship"),
    "SI": ("Slovenia", "sl", "internship"),
    "EE": ("Estonia", "et", "praktika"),
    "LV": ("Latvia", "lv", "prakse"),
    "LT": ("Lithuania", "lt", "praktika"),
    "GR": ("Greece", "el", "internship"),
    "CY": ("Cyprus", "en", "internship"),
    "MT": ("Malta", "en", "internship"),
    "RS": ("Serbia", "sr", "internship"),
    "UA": ("Ukraine", "uk", "internship"),
    "AL": ("Albania", "sq", "internship"),
    "BA": ("Bosnia and Herzegovina", "en", "internship"),
    "ME": ("Montenegro", "en", "internship"),
    "MK": ("North Macedonia", "en", "internship"),
    "MD": ("Moldova", "ro", "internship"),
    "LI": ("Liechtenstein", "de", "Praktikum"),
    "MC": ("Monaco", "fr", "stage"),
    "AD": ("Andorra", "en", "internship"),
    "SM": ("San Marino", "it", "tirocinio"),
    "BY": ("Belarus", "en", "internship"),
    "XK": ("Kosovo", "en", "internship"),
    "VA": ("Vatican City", "it", "tirocinio"),
    "FO": ("Faroe Islands", "en", "internship"),
    "GI": ("Gibraltar", "en", "internship"),
}


class SearchCards(HTMLParser):
    def __init__(self):
        super().__init__()
        self.records = []
        self.current = None
        self.field = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        urn = attrs.get("data-entity-urn", "")
        if urn.startswith("urn:li:jobPosting:"):
            self.current = {
                "id": urn.rsplit(":", 1)[-1],
                "url": "",
                "company": "",
                "raw": {"title": "", "location": ""},
            }
            self.records.append(self.current)
        if not self.current:
            return
        classes = (attrs.get("class") or "").split()
        if "base-card__full-link" in classes:
            parts = urlsplit(attrs.get("href", ""))
            if (
                parts.scheme == "https"
                and (parts.hostname or "").endswith(".linkedin.com")
                and parts.path.startswith("/jobs/view/")
            ):
                self.current["url"] = urlunsplit(
                    (parts.scheme, parts.netloc, parts.path, "", "")
                )
        for classname, field in [
            ("base-search-card__title", "title"),
            ("base-search-card__subtitle", "company"),
            ("job-search-card__location", "location"),
        ]:
            if classname in classes:
                self.field = (tag, field)

    def handle_endtag(self, tag):
        if self.field and self.field[0] == tag:
            self.field = None

    def handle_data(self, data):
        if self.current and self.field:
            field = self.field[1]
            target = self.current if field == "company" else self.current["raw"]
            target[field] = (target.get(field, "") + " " + data.strip()).strip()


def read_search(url, deadline):
    try:
        with (
            httpx.Client(timeout=15, follow_redirects=False, trust_env=False) as client,
            client.stream(
                "GET",
                url,
                headers={"Accept": "text/html", "User-Agent": "InternCatalogue/1.0"},
            ) as response,
        ):
            if response.status_code in (403, 429, 999):
                error = CatalogueImportError(
                    "linkedin_needs_access"
                    if response.status_code != 429
                    else "linkedin_rate_limited"
                )
                retry = response.headers.get("Retry-After", "")
                error.retry_after = int(retry) if retry.isdigit() else None
                raise error
            if response.status_code != 200:
                raise CatalogueImportError("linkedin_public_unavailable")
            body = bytearray()
            for chunk in response.iter_bytes():
                body.extend(chunk)
                if len(body) > 2 * 1024 * 1024 or time.monotonic() >= deadline:
                    raise CatalogueImportError("linkedin_response_budget")
        return body.decode("utf-8", errors="replace")
    except httpx.HTTPError as exc:
        raise CatalogueImportError("linkedin_public_unavailable") from exc


def fetch_linkedin(query, deadline):
    from .discovery_feeds import FeedPage

    if query.country not in COUNTRIES:
        raise CatalogueImportError("unsupported_discovery_country")
    # A capped cycle deliberately remains truncated, then starts a new daily window.
    start = int(query.cursor or 0)
    if start >= 150:
        start = 0
    params = {
        "keywords": query.term,
        "location": COUNTRIES[query.country][0],
        "f_JT": "I",
        "f_TPR": "r604800",
        "start": start,
    }
    url = (
        "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?"
        + urlencode(params)
    )
    html = read_search(url, deadline)
    parser = SearchCards()
    parser.feed(html)
    records = [row for row in parser.records if row["url"] and row["id"].isdigit()][:25]
    if not records and re.search(r"authwall|challenge|sign-in-form", html, re.IGNORECASE):
        raise CatalogueImportError("linkedin_needs_access")
    for row in records:
        row["raw"].update(
            source="linkedin_public",
            search_url=url,
            country_query=query.country,
            date_window="past_week",
        )
    # Guest endpoint does not supply a reliable total; never infer completeness from 10 rows.
    return FeedPage(records, str(start + len(records)) if records else "", None)


class VisibleLinks(HTMLParser):
    """Only ordinary visible anchors; never modal, hidden, script or encoded apply data."""

    def __init__(self):
        super().__init__()
        self.stack = []
        self.links = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        hidden = (
            any(row[1] for row in self.stack)
            or tag in {"script", "style", "template"}
            or "hidden" in attrs
            or attrs.get("aria-hidden") == "true"
            or "display:none" in (attrs.get("style") or "").replace(" ", "")
            or any(
                token in (attrs.get("class") or "").split()
                for token in ["hidden", "modal", "contextual-sign-in-modal"]
            )
        )
        if tag == "a" and not hidden and attrs.get("href"):
            self.links.append(attrs["href"])
        if tag not in {
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
        }:
            self.stack.append((tag, hidden))

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                self.stack = self.stack[:index]
                break


# Search heuristics, not exhaustive translations or employment classifications.
DOMAIN_SEARCH_TERMS = {
    "it-data": ("informatique", "Software", "software"),
    "engineering-industry": ("ingénierie", "Ingenieur", "engineering"),
    "science-research": ("recherche", "Forschung", "research"),
    "health": ("santé", "Gesundheit", "health"),
    "finance-accounting": ("finance", "Finanzen", "finance"),
    "legal": ("juridique", "Recht", "legal"),
    "marketing-communication": ("marketing", "Marketing", "marketing"),
    "sales": ("commercial", "Vertrieb", "sales"),
    "human-resources": ("ressources humaines", "Personal", "human resources"),
    "design-arts": ("design", "Design", "design"),
    "operations-logistics": ("logistique", "Logistik", "logistics"),
    "hospitality-tourism": ("hôtellerie", "Tourismus", "hospitality"),
    "public-nonprofit": ("association", "gemeinnützig", "nonprofit"),
}
