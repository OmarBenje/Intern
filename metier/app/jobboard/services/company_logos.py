"""Extract employer branding from their existing source boards and cache safe PNGs."""

import hashlib
import io
import json
import re
import time
import warnings
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from django.utils import timezone
from PIL import Image, UnidentifiedImageError

from jobboard.integrations.greenhouse_catalogue import CatalogueImportError
from jobboard.integrations.public_html import fetch_public
from jobboard.integrations.storage import storage_bucket, write_object

ATS_HOSTS = {
    "jobs.ashbyhq.com",
    "jobs.lever.co",
    "job-boards.greenhouse.io",
    "boards.greenhouse.io",
    "careers.smartrecruiters.com",
}
PLATFORM_DOMAINS = ATS_HOSTS | {
    "ashbyhq.com",
    "greenhouse.io",
    "greenhouse.com",
    "lever.co",
    "smartrecruiters.com",
    "recruitee.com",
    "myworkdayjobs.com",
    "workday.com",
    "personio.de",
    "personio.com",
    "teamtailor.com",
    "workable.com",
    "icims.com",
    "successfactors.com",
    "successfactors.eu",
    "linkedin.com",
    "licdn.com",
    "welcometothejungle.com",
    "indeed.com",
    "glassdoor.com",
    "facebook.com",
    "instagram.com",
    "twitter.com",
    "x.com",
}
# Confirmed by inspecting the cached PNG, not by counting shared brand assets.
REJECTED_LOGO_DIGESTS = {
    "037e67fd114b8f2a091d5973a2d89b5705614c3a1812192a51f9358fc73083aa"
}


def platform_host(host):
    host = (host or "").lower()
    return any(
        host == domain or host.endswith("." + domain) for domain in PLATFORM_DOMAINS
    )


def employer_domain(value):
    """Validate an existing identity, never infer a domain from a company name."""
    try:
        parts = urlsplit(
            value if "://" in (value or "") else "https://" + (value or "")
        )
        host = (parts.hostname or "").encode("idna").decode("ascii").lower()
        if (
            parts.scheme != "https"
            or parts.username
            or parts.password
            or parts.port not in (None, 443)
            or parts.query
            or parts.fragment
            or parts.path not in ("", "/")
            or platform_host(host)
            or len(host) > 253
            or not re.fullmatch(
                r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}", host
            )
        ):
            return None
        return host
    except (ValueError, UnicodeError):
        return None


def same_name(left, right):
    return re.sub(r"\W+", "", left.casefold()) == re.sub(r"\W+", "", right.casefold())


class LogoParser(HTMLParser):
    def __init__(self, page_url, company_name):
        super().__init__(convert_charrefs=True)
        self.page_url = page_url
        self.company_name = company_name.casefold()
        self.candidates = []
        self.homepages = []
        self.script = None
        self.structured_homepages = []
        self.kinds = {}

    def add(self, url, priority, kind="page_logo"):
        if not isinstance(url, str) or not url or len(url) > 2048:
            return
        try:
            url = urljoin(self.page_url, url)
            parts = urlsplit(url)
        except ValueError:
            return
        if (
            parts.scheme == "https"
            and parts.hostname
            and not parts.username
            and not parts.password
            and not parts.path.lower().endswith(".svg")
        ):
            self.candidates.append((priority, url))
            self.kinds.setdefault(url, kind)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "script" and attrs.get("type", "").lower() == "application/ld+json":
            self.script = []
        if (
            tag == "a"
            and "logo" in (attrs.get("class") or "").casefold()
            and "footer" not in (attrs.get("class") or "").casefold()
            and attrs.get("href")
        ):
            try:
                target = urljoin(self.page_url, attrs["href"])
                host = employer_domain(target)
            except ValueError:
                host = None
            if (
                host
                and host != urlsplit(self.page_url).hostname
                and not platform_host(host)
                and platform_host(urlsplit(self.page_url).hostname)
            ):
                self.homepages.append(target)
        if tag == "link" and "/api/images/org-theme-logo/" in (attrs.get("href") or ""):
            self.add(attrs["href"], 0)
        if tag == "img":
            description = " ".join(
                (attrs.get(key) or "") for key in ("alt", "class", "id")
            ).casefold()
            if (
                (
                    "logo" in description
                    or (
                        "entity-image" in description
                        and self.company_name in description
                    )
                )
                and not any(
                    term in description
                    for term in (
                        "footer",
                        "customer",
                        "client",
                        "partner",
                        "linkedin",
                        "facebook",
                        "instagram",
                        "twitter",
                        "welcome to the jungle",
                    )
                )
                and not any(
                    vendor in description
                    for vendor in (
                        "lever logo",
                        "greenhouse logo",
                        "smartrecruiters logo",
                        "ashby logo",
                    )
                )
                and (
                    not platform_host(urlsplit(self.page_url).hostname)
                    or self.company_name in description
                )
            ):
                self.add(
                    attrs.get("data-delayed-url")
                    or attrs.get("src")
                    or attrs.get("data-src"),
                    0 if self.company_name in description else 2,
                )
        if (
            tag == "meta"
            and attrs.get("property") == "og:image"
            and "/api/images/org-theme-logo/" in (attrs.get("content") or "")
        ):
            self.add(attrs.get("content"), 0)
        # ATS favicons belong to the platform, not to the employer.
        if tag == "link" and not platform_host(urlsplit(self.page_url).hostname):
            rel = attrs.get("rel") or ""
            if "apple-touch-icon" in rel:
                self.add(attrs.get("href"), 10, "site_icon")
            elif "icon" in rel.split():
                sizes = re.findall(r"(\d+)x\d+", attrs.get("sizes") or "")
                size = max((int(value) for value in sizes), default=16)
                self.add(attrs.get("href"), 11 - min(size, 512) / 512, "site_icon")

    def handle_data(self, data):
        if self.script is not None:
            self.script.append(data)

    def handle_endtag(self, tag):
        if tag != "script" or self.script is None:
            return
        try:
            pending = [json.loads("".join(self.script))]
        except (ValueError, RecursionError):
            pending = []
        self.script = None
        for _ in range(500):
            if not pending:
                break
            value = pending.pop()
            if isinstance(value, list):
                pending.extend(value[:500])
            elif isinstance(value, dict):
                kind = value.get("@type", [])
                kinds = (
                    [kind]
                    if isinstance(kind, str)
                    else kind
                    if isinstance(kind, list)
                    else []
                )
                if "JobPosting" in kinds:
                    pending.append(value.get("hiringOrganization"))
                elif any(k in kinds for k in ("Organization", "Corporation")):
                    name = value.get("name")
                    if isinstance(name, str) and same_name(name, self.company_name):
                        logo = value.get("logo")
                        if isinstance(logo, dict):
                            logo = logo.get("contentUrl") or logo.get("url")
                        self.add(logo, -30, "structured_logo")
                        homepage = value.get("url")
                        if isinstance(homepage, str) and employer_domain(homepage):
                            self.structured_homepages.append(homepage)
                            self.homepages.append(homepage)
                if "@graph" in value:
                    pending.append(value["@graph"])

    def urls(self):
        return list(
            dict.fromkeys(
                url for _, url in sorted(self.candidates, key=lambda item: item[0])
            )
        )[:8]


def normalize_logo(data):
    """Decode only raster formats; bound pixels and strip metadata by re-encoding."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        try:
            with Image.open(
                io.BytesIO(data), formats=["PNG", "JPEG", "WEBP", "GIF", "ICO"]
            ) as source:
                if source.width * source.height > 4_000_000 or min(source.size) < 8:
                    raise CatalogueImportError("invalid_logo_dimensions")
                source.seek(0)
                image = source.convert("RGBA")
                image.thumbnail((256, 256), Image.Resampling.LANCZOS)
                output = io.BytesIO()
                image.save(output, format="PNG")
                return output.getvalue()
        except (
            UnidentifiedImageError,
            OSError,
            ValueError,
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
        ) as exc:
            raise CatalogueImportError("invalid_logo_image") from exc


def cache_logo(company, image_url, deadline=None, *, source_kind="manual"):
    try:
        final_url, data = fetch_public(image_url, deadline=deadline, image=True)
    except ValueError as exc:
        raise CatalogueImportError("unsafe_public_url") from exc
    png = normalize_logo(data)
    digest = hashlib.sha256(png).hexdigest()
    if digest in REJECTED_LOGO_DIGESTS:
        raise CatalogueImportError("platform_logo_rejected")
    key = f"company-logos/{company.pk}/{digest}.png"
    try:
        write_object(storage_bucket(), key, png, content_type="image/png")
    except FileExistsError:
        pass
    company.logo_object_key = key
    company.logo_next_attempt_at = None
    company.logo_last_error = ""
    company.logo_source_url = final_url
    company.logo_source_kind = source_kind
    company.logo_fetched_at = timezone.now()
    company.save(
        update_fields=[
            "logo_object_key",
            "logo_next_attempt_at",
            "logo_last_error",
            "logo_source_url",
            "logo_source_kind",
            "logo_fetched_at",
            "updated_at",
        ]
    )
    return key


def extract_logo(company, *, page_url=None):
    from jobboard.models import OfferSource

    failures = []
    deadline = time.monotonic() + 45
    source_homepages = []
    # The catalogue already associates these source records with the employer.
    # Preserve provider-authored company logos instead of scraping a global favicon.
    if not page_url:
        sources = list(
            OfferSource.objects.filter(
                offer__company=company,
                source_status="active",
                board__provider__in=["wttj", "jobspy"],
            )
            .select_related("board")
            .order_by("-last_seen_at", "pk")[:4]
        )
        slugs = set()
        for source in sources:
            raw = source.raw_payload
            if (
                not isinstance(raw, dict)
                or not isinstance(raw.get("company"), str)
                or not same_name(raw["company"], company.name)
            ):
                continue
            try:
                website = raw.get("company_website")
                if isinstance(website, str) and employer_domain(website):
                    source_homepages.append(website)
                logo = raw.get("company_logo")
                if not logo and source.board.provider == "wttj":
                    slug = raw.get("company_slug")
                    if not isinstance(slug, str) or slug in slugs:
                        continue
                    slugs.add(slug)
                    from jobboard.integrations.wttj_catalogue import company_logo

                    logo = company_logo(slug, company.name, deadline=deadline)
                if isinstance(logo, str):
                    return cache_logo(
                        company, logo, deadline, source_kind="source_metadata"
                    )
            except CatalogueImportError as exc:
                failures.append(str(exc))
            if time.monotonic() >= deadline:
                break

    pages = ([page_url] if page_url else []) + (
        [company.website_url] if company.website_url else []
    )
    pages += source_homepages
    pages += list(
        company.source_boards.order_by("pk").values_list("base_url", flat=True)
    )
    if company.domain and not company.website_url:
        pages.append(f"https://{company.domain}/")
    pages += list(
        OfferSource.objects.filter(offer__company=company, source_status="active")
        .order_by("-last_seen_at", "pk")
        .values_list("origin_url", flat=True)[:2]
    )

    def useful_page(page):
        try:
            parts = urlsplit(page)
            # Never read the generic landing page of a job/social platform.
            return (
                parts.scheme == "https"
                and parts.hostname
                and not (platform_host(parts.hostname) and parts.path in ("", "/"))
            )
        except ValueError:
            return False

    pages = [page for page in dict.fromkeys(pages) if useful_page(page)][:5]
    for page in pages:
        if time.monotonic() >= deadline:
            break
        try:
            final_url, html = fetch_public(page, deadline=deadline)
            parser = LogoParser(final_url, company.name)
            parser.feed(html)
            for homepage in parser.homepages:
                if homepage not in pages and len(pages) < 5:
                    pages.append(homepage)
            for url in parser.urls():
                try:
                    key = cache_logo(
                        company, url, deadline, source_kind=parser.kinds[url]
                    )
                    # Only successful first-party reads or matching structured
                    # organization metadata establish a missing employer identity.
                    homepage = next(iter(parser.structured_homepages), None)
                    if not homepage and not platform_host(urlsplit(final_url).hostname):
                        homepage = "https://" + urlsplit(final_url).hostname + "/"
                    domain = employer_domain(homepage)
                    if domain and not company.website_url and not company.domain:
                        company.website_url, company.domain = homepage, domain
                        company.save(
                            update_fields=["website_url", "domain", "updated_at"]
                        )
                    return key
                except CatalogueImportError as exc:
                    failures.append(str(exc))
        except (CatalogueImportError, ValueError) as exc:
            failures.append(str(exc))
    raise CatalogueImportError(
        "logo_not_found"
        + (": " + ", ".join(dict.fromkeys(failures)) if failures else "")
    )


def process_logo_jobs(limit=5):
    """New companies are due by default. Lease work before doing any network I/O."""
    import logging
    from datetime import timedelta

    from django.db import transaction
    from django.db.models import Q
    from django.utils import timezone

    from jobboard.models import Company

    processed = 0
    for _ in range(limit):
        with transaction.atomic():
            company = (
                Company.objects.select_for_update(skip_locked=True)
                .filter(
                    Q(logo_object_key__isnull=True) | Q(logo_object_key=""),
                    logo_next_attempt_at__lte=timezone.now(),
                )
                .order_by("logo_next_attempt_at", "pk")
                .first()
            )
            if company is None:
                break
            company.logo_attempts += 1
            company.logo_next_attempt_at = timezone.now() + timedelta(minutes=10)
            company.save(update_fields=["logo_attempts", "logo_next_attempt_at"])
        try:
            extract_logo(company)
        except Exception as exc:
            # Keep the queue alive; unexpected errors remain visible in worker logs.
            if not isinstance(exc, CatalogueImportError):
                logging.getLogger(__name__).exception(
                    "Company logo extraction failed for %s", company.pk
                )
            delay = min(7 * 24 * 60, 10 * 2 ** min(company.logo_attempts - 1, 10))
            Company.objects.filter(
                pk=company.pk, logo_object_key=company.logo_object_key
            ).update(
                logo_next_attempt_at=timezone.now() + timedelta(minutes=delay),
                logo_last_error=str(exc)[:240],
            )
        processed += 1
    return processed
