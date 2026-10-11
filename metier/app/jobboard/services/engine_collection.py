"""Operator source discovery and bounded board.sync outbox consumer."""

import re
import uuid
from datetime import timedelta
from urllib.parse import urlsplit

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from jobboard.integrations.greenhouse_catalogue import CatalogueImportError
from jobboard.integrations.public_catalogue import board_key
from jobboard.models import (
    BoardSchedule,
    Company,
    OutboxMessage,
    SourceBoard,
    SourceCandidate,
)

from .catalogue import import_board


def parse_source_url(url):
    parsed = urlsplit(url)
    from jobboard.integrations.eightfold_catalogue import (
        BOARDS as EIGHTFOLD_BOARDS,
    )
    from jobboard.integrations.eightfold_catalogue import (
        parse_eightfold_url,
    )

    if parsed.hostname in {
        host for board in EIGHTFOLD_BOARDS.values() for host in (board[0], board[2])
    }:
        return parse_eightfold_url(url)
    from jobboard.integrations.icims_catalogue import (
        BOARDS as ICIMS_BOARDS,
    )
    from jobboard.integrations.icims_catalogue import (
        parse_icims_url,
    )
    from jobboard.integrations.taleo_catalogue import (
        HOST as TALEO_HOST,
    )
    from jobboard.integrations.taleo_catalogue import (
        parse_taleo_url,
    )

    if parsed.hostname in {host for host, _ in ICIMS_BOARDS.values()}:
        return parse_icims_url(url)
    if parsed.hostname == TALEO_HOST:
        return parse_taleo_url(url)
    from jobboard.integrations.successfactors_catalogue import (
        BOARDS,
        parse_successfactors_url,
    )

    if parsed.hostname in {host for host, _ in BOARDS.values()}:
        return parse_successfactors_url(url)
    hosts = {
        "boards.greenhouse.io": ("greenhouse", "global"),
        "job-boards.greenhouse.io": ("greenhouse", "global"),
        "careers.smartrecruiters.com": ("smartrecruiters", "global"),
        "jobs.smartrecruiters.com": ("smartrecruiters", "global"),
        "jobs.ashbyhq.com": ("ashby", "global"),
        "jobs.lever.co": ("lever", "global"),
        "jobs.eu.lever.co": ("lever", "eu"),
    }
    personio = re.fullmatch(
        r"([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)\.jobs\.personio\.(de|com)",
        parsed.hostname or "",
    )
    recruitee = re.fullmatch(
        r"([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)\.recruitee\.com", parsed.hostname or ""
    )
    if parsed.hostname and parsed.hostname.endswith(".myworkdayjobs.com"):
        from jobboard.integrations.workday_catalogue import parse_workday_url

        return parse_workday_url(url)
    try:
        valid = (
            parsed.scheme == "https"
            and not parsed.username
            and not parsed.password
            and parsed.port in (None, 443)
            and not parsed.query
            and not parsed.fragment
        )
    except ValueError:
        valid = False
    if not valid:
        raise CatalogueImportError("unsupported_source_url")
    teamtailor = re.fullmatch(
        r"([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)\.teamtailor\.com",
        parsed.hostname or "",
    )
    if teamtailor or parsed.hostname == "apply.workable.com":
        from jobboard.integrations.teamtailor_catalogue import tenant

        if teamtailor:
            key = teamtailor[1]
            provider = "teamtailor"
            allowed = re.fullmatch(
                r"/?(?:jobs(?:\.rss|/[0-9]+(?:-[^/]+)?)?)?/?", parsed.path
            )
            canonical = f"https://{key}.teamtailor.com"
        else:
            parts = parsed.path.strip("/").split("/")
            key = tenant(parts[0])
            provider = "workable"
            allowed = len(parts) == 1 or (
                len(parts) == 3
                and parts[1] == "j"
                and re.fullmatch(r"[A-Za-z0-9]{1,40}", parts[2])
            )
            canonical = f"https://apply.workable.com/{key}"
        if not allowed:
            raise CatalogueImportError("expected_board_url")
        return {
            "provider": provider,
            "instance": "global",
            "board_key": key,
            "canonical": canonical,
        }
    if personio or recruitee:
        match = personio or recruitee
        key = match.group(1)
        if personio:
            provider, instance = "personio", match.group(2)
            allowed = re.fullmatch(r"/?(?:xml|job/[0-9]+)?/?", parsed.path)
        else:
            provider, instance = "recruitee", "global"
            allowed = re.fullmatch(
                r"/?(?:api/offers/?|api/feeds/offers.xml|(?:l/[a-z]{2}/)?o/[^/]+)?/?",
                parsed.path,
            )
        if not allowed:
            raise CatalogueImportError("expected_board_url")
        canonical = f"https://{parsed.hostname}"
    else:
        if parsed.hostname not in hosts:
            raise CatalogueImportError("unsupported_source_url")
        parts = parsed.path.strip("/").split("/")
        if len(parts) != 1 and not (
            parsed.hostname == "jobs.smartrecruiters.com"
            and len(parts) == 2
            and re.fullmatch(r"[0-9]+(?:-[^/]+)?", parts[1])
        ):
            raise CatalogueImportError("expected_board_url")
        key = board_key(parts[0])
        provider, instance = hosts[parsed.hostname]
        host = (
            "careers.smartrecruiters.com"
            if provider == "smartrecruiters"
            else parsed.hostname
        )
        canonical = f"https://{host}/{key}"
    return {
        "provider": provider,
        "instance": instance,
        "board_key": key,
        "canonical": canonical,
    }


def register_source(url, company_name, enable=False):
    parsed = parse_source_url(url)
    provider, instance, key, canonical = (
        parsed[name] for name in ("provider", "instance", "board_key", "canonical")
    )
    if len(key) > 240 or len(canonical) > 2048:
        raise CatalogueImportError("invalid_board_key")
    if not company_name.strip() or len(company_name) > 240:
        raise CatalogueImportError("invalid_company_name")
    with transaction.atomic():
        candidate, _ = SourceCandidate.objects.get_or_create(
            url=canonical,
            defaults={
                "provider": provider,
                "instance": instance,
                "board_key": key,
                "company_name": company_name.strip(),
            },
        )
        if enable:
            # Operator confirms company identity; successful pilot import validates source.
            board = SourceBoard.objects.filter(
                provider=provider, instance=instance, board_key=key
            ).first()
            if not board:
                company = Company.objects.create(name=company_name.strip())
                board = SourceBoard.objects.create(
                    provider=provider,
                    instance=instance,
                    board_key=key,
                    company=company,
                    base_url=canonical,
                    enabled=True,
                )
            if not board.enabled:
                board.enabled = True
                board.save(update_fields=["enabled"])
            candidate.board = board
            candidate.save(update_fields=["board"])
            BoardSchedule.objects.update_or_create(
                board=board, defaults={"paused": False}
            )
    if enable:
        try:
            import_board(board.pk)
        except Exception:
            # The candidate is retained for diagnosis; no recurring broken import enabled.
            BoardSchedule.objects.filter(board=board).update(paused=True)
            raise
        SourceCandidate.objects.filter(pk=candidate.pk).update(status="validated")
        candidate.refresh_from_db()
    return candidate


def schedule_due(limit=100):
    now = timezone.now()
    # Bootstrap existing configured boards additively.
    for board_id in SourceBoard.objects.filter(
        enabled=True,
        provider__in=[
            "greenhouse",
            "ashby",
            "lever",
            "smartrecruiters",
            "personio",
            "recruitee",
            "teamtailor",
            "workable",
            "workday",
            "successfactors",
            "icims",
            "taleo",
            "eightfold",
        ],
        company__isnull=False,
        engine_schedule__isnull=True,
    ).values_list("pk", flat=True)[:limit]:
        BoardSchedule.objects.get_or_create(board_id=board_id)
    queued = 0
    with transaction.atomic():
        schedules = (
            BoardSchedule.objects.select_for_update(skip_locked=True)
            .filter(paused=False, board__enabled=True, next_run_at__lte=now)
            .exclude(board__provider__in=["jobspy", "eures", "wttj", "jobtech", "bundesagentur", "nav"])
            .filter(Q(lease_expires_at__isnull=True) | Q(lease_expires_at__lte=now))
            .order_by("next_run_at")[:limit]
        )
        for schedule in schedules:
            _, created = OutboxMessage.objects.get_or_create(
                dedupe_key=f"board.sync:{schedule.board_id}:{schedule.next_run_at.isoformat()}",
                defaults={
                    "topic": "board.sync",
                    "payload": {"board_id": schedule.board_id},
                },
            )
            queued += int(created)
    return queued


def process_one():
    now = timezone.now()
    with transaction.atomic():
        message = (
            OutboxMessage.objects.select_for_update(skip_locked=True)
            .filter(
                topic="board.sync", processed_at__isnull=True, available_at__lte=now
            )
            .filter(Q(lease_expires_at__isnull=True) | Q(lease_expires_at__lte=now))
            .order_by("available_at", "pk")
            .first()
        )
        if not message:
            return False
        token = uuid.uuid4()
        message.lease_token, message.lease_expires_at = (
            token,
            now + timedelta(minutes=20),
        )
        message.attempts += 1
        message.save(update_fields=["lease_token", "lease_expires_at", "attempts"])
    error = ""
    try:
        import_board(message.payload["board_id"])
    except Exception as exc:  # noqa: BLE001 - failed events are durable, scheduler owns retries
        error = exc.code if isinstance(exc, CatalogueImportError) else "import_failed"
    with transaction.atomic():
        message = OutboxMessage.objects.select_for_update().get(pk=message.pk)
        if message.lease_token == token:
            # Each attempt terminates its event. The schedule owns retries/backoff.
            message.processed_at = timezone.now()
            message.last_error_code = error or None
            message.lease_token = message.lease_expires_at = None
            message.save(
                update_fields=[
                    "processed_at",
                    "last_error_code",
                    "lease_token",
                    "lease_expires_at",
                ]
            )
    return True
