"""Daily bounded traversal of explicitly approved public employer sites."""

import time
import uuid
from datetime import timedelta
from urllib.parse import urljoin, urlsplit, urlunsplit

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from jobboard.integrations.greenhouse_catalogue import CatalogueImportError
from jobboard.integrations.public_html import PublicHTMLParser, fetch_html, validate_url
from jobboard.models import SourceDiscoverySeed

from .engine_search_discovery import candidate_from_url

ATS_HOSTS = {
    "boards.greenhouse.io",
    "job-boards.greenhouse.io",
    "jobs.ashbyhq.com",
    "jobs.lever.co",
    "jobs.eu.lever.co",
}


def discover(seed):
    queue, visited = [seed.url], set()
    deadline = time.monotonic() + 25
    while queue and len(visited) < 3:
        url = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)
        final_url, html = fetch_html(url, {seed.allowed_host}, deadline=deadline)
        parser = PublicHTMLParser()
        parser.feed(html)
        for href in parser.links[:1000]:
            try:
                target = urlsplit(urljoin(final_url, href))
                canonical = urlunsplit(
                    (target.scheme, target.netloc, target.path, "", "")
                )
                candidate = candidate_from_url(canonical, seed.company_name)
                if candidate:
                    continue
                if target.hostname == seed.allowed_host and any(
                    word in target.path.lower()
                    for word in (
                        "career",
                        "job",
                        "emploi",
                        "recrut",
                        "karriere",
                        "stage",
                        "trabaj",
                        "lavor",
                    )
                ):
                    validate_url(canonical, {seed.allowed_host})
                    if canonical not in visited and canonical not in queue:
                        queue.append(canonical)
            except (ValueError, CatalogueImportError):
                continue


def run_discovery(limit=10):
    processed = 0
    for _ in range(min(limit, 10)):
        now = timezone.now()
        token = uuid.uuid4()
        with transaction.atomic():
            seed = (
                SourceDiscoverySeed.objects.select_for_update(skip_locked=True)
                .filter(enabled=True, next_run_at__lte=now)
                .filter(Q(lease_expires_at__isnull=True) | Q(lease_expires_at__lte=now))
                .order_by("next_run_at", "pk")
                .first()
            )
            if not seed:
                break
            seed.lease_token, seed.lease_expires_at = token, now + timedelta(minutes=2)
            seed.save(update_fields=["lease_token", "lease_expires_at"])
        updates = {
            "lease_token": None,
            "lease_expires_at": None,
            "next_run_at": now + timedelta(days=1),
        }
        try:
            discover(seed)
            updates.update(
                last_success_at=timezone.now(), failure_count=0, last_error_code=""
            )
        except (CatalogueImportError, ValueError) as exc:
            updates.update(
                failure_count=seed.failure_count + 1,
                last_error_code=getattr(exc, "code", "invalid_public_page"),
            )
        SourceDiscoverySeed.objects.filter(pk=seed.pk, lease_token=token).update(
            **updates
        )
        processed += 1
    return processed
