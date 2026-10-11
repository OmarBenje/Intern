"""Private ATS extraction through fixed-host connectors, never arbitrary URLs."""

import re
from types import SimpleNamespace
from urllib.parse import urlsplit

from django.contrib.auth import get_user_model
from django.db import transaction

from jobboard.integrations.greenhouse_catalogue import (
    CatalogueImportError,
    fetch_snapshot,
    normalize_snapshot,
)
from jobboard.integrations.public_catalogue import fetch_normalized
from jobboard.integrations.public_html import fetch_html, parse_job_postings
from jobboard.models import ExternalOpportunity, OfferSource, SourceDiscoverySeed


def parse_target(url):
    parts = urlsplit(url)
    if (
        parts.scheme != "https"
        or parts.username
        or parts.password
        or parts.port not in (None, 443)
        or parts.query
        or parts.fragment
    ):
        raise CatalogueImportError("unsupported_source")
    path = parts.path.strip("/").split("/")
    host = parts.hostname
    if (
        host in ("boards.greenhouse.io", "job-boards.greenhouse.io")
        and len(path) == 3
        and path[1] == "jobs"
        and re.fullmatch(r"[0-9]{1,30}", path[2])
    ):
        provider, instance, key, identity = "greenhouse", "global", path[0], path[2]
    elif (
        host in ("jobs.lever.co", "jobs.eu.lever.co", "jobs.ashbyhq.com")
        and len(path) in (2, 3)
        and (len(path) == 2 or path[2] == "application")
        and re.fullmatch(r"[A-Za-z0-9_-]{1,100}", path[1])
    ):
        provider, instance, key, identity = (
            ("ashby" if host == "jobs.ashbyhq.com" else "lever"),
            ("eu" if host == "jobs.eu.lever.co" else "global"),
            path[0],
            path[1],
        )
    else:
        raise CatalogueImportError("unsupported_source")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,240}", key):
        raise CatalogueImportError("unsupported_source")
    return SimpleNamespace(
        provider=provider, instance=instance, board_key=key
    ), identity


def extract_ats(board, identity):
    source = (
        OfferSource.objects.filter(
            board__provider=board.provider,
            board__instance=board.instance,
            board__board_key=board.board_key,
            external_id=identity,
            source_status="active",
            board__enabled=True,
            offer__status="open",
        )
        .select_related("offer__company")
        .first()
    )
    if source:
        updates = {
            "title": source.offer.title,
            "company_name": source.offer.company.name,
            "description": source.offer.description,
            "offer_id": source.offer_id,
        }
    else:
        rows = (
            normalize_snapshot(fetch_snapshot(board.board_key))
            if board.provider == "greenhouse"
            else fetch_normalized(board)
        )
        row = next((row for row in rows if row["external_id"] == identity), None)
        if row is None:
            raise CatalogueImportError("posting_not_found")
        updates = {"title": row["title"], "description": row["description"]}
    return updates


def process_external_opportunities(limit=100):
    processed = 0
    for snapshot in ExternalOpportunity.objects.filter(
        status="pending", user__is_active=True
    ).order_by("id")[:limit]:
        updates = {}
        try:
            try:
                board, identity = parse_target(snapshot.url)
            except CatalogueImportError:
                host = urlsplit(snapshot.url).hostname
                if not SourceDiscoverySeed.objects.filter(
                    allowed_host=host, enabled=True
                ).exists():
                    raise
                _, html = fetch_html(snapshot.url, {host})
                rows = parse_job_postings(html)
                if len(rows) != 1 or not rows[0]["title"]:
                    raise CatalogueImportError("ambiguous_or_missing_job_posting")
                updates = rows[0]
                board = None
            if board is not None:
                updates = extract_ats(board, identity)
            status, error = "ready", ""
        except (CatalogueImportError, ValueError) as exc:
            status, error = "failed", getattr(exc, "code", "unsupported_source")
        with transaction.atomic():
            user = (
                get_user_model()
                .objects.select_for_update()
                .filter(pk=snapshot.user_id, is_active=True)
                .first()
            )
            if not user:
                continue
            # Network runs without locks; a user edit/deletion wins over this result.
            item = (
                ExternalOpportunity.objects.select_for_update()
                .filter(
                    pk=snapshot.pk,
                    status="pending",
                    updated_at=snapshot.updated_at,
                    user__is_active=True,
                )
                .first()
            )
            if not item:
                continue
            for key, value in updates.items():
                if key == "offer_id" or not getattr(item, key):
                    setattr(item, key, value)
            item.status, item.error_code = status, error
            item.save()
            processed += 1
    return processed
