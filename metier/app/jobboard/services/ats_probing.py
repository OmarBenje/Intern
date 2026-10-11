"""Durable, bounded screening of explicitly enrolled public ATS candidates."""

import uuid
from datetime import timedelta
from types import SimpleNamespace

from django.db import transaction
from django.db.models import Count, Min, Q
from django.utils import timezone

from jobboard.api.catalogue import open_offers
from jobboard.integrations.greenhouse_catalogue import (
    CatalogueImportError,
    fetch_snapshot,
    normalize_snapshot,
)
from jobboard.integrations.public_catalogue import fetch_normalized
from jobboard.models import AtsProbe, BoardSchedule, SourceBoard, SourceCandidate
from jobboard.services.ats_registry import PROVIDERS
from jobboard.services.engine_collection import register_source
from jobboard.services.engine_quality import extract_facts, structured_country_code


def enroll(limit=100, providers=("greenhouse", "lever", "ashby")):
    if (
        not 1 <= limit <= 100
        or not providers
        or any(p not in PROVIDERS for p in providers)
    ):
        raise ValueError("limit must be between 1 and 100")
    added = []
    for candidate in (
        SourceCandidate.objects.filter(
            status="candidate",
            board__isnull=True,
            provider__in=providers,
            probe__isnull=True,
        )
        .order_by("pk")
        .iterator()
    ):
        if SourceBoard.objects.filter(
            provider=candidate.provider,
            instance=candidate.instance,
            board_key=candidate.board_key,
        ).exists():
            continue
        probe, created = AtsProbe.objects.get_or_create(candidate=candidate)
        if created:
            added.append(probe.pk)
        if len(added) >= limit:
            break
    return added


def qualifies(row):
    details = row.get("location_details") or [
        {"name": name} for name in row.get("locations", [])
    ]
    locations = [
        {
            "name": d["name"],
            "country_code": structured_country_code(d.get("country") or ""),
        }
        for d in details
    ]
    facts = extract_facts(
        row["title"],
        row["description"],
        locations=locations,
        contract_type=row.get("contract_type", "unknown"),
        work_mode=row.get("work_mode", "unknown"),
    )
    return (
        facts["classification"] == "confirmed" and facts["europe_status"] == "in_scope"
    )


def run_one(probe_ids=None):
    now = timezone.now()
    with transaction.atomic():
        candidates = AtsProbe.objects.all()
        if probe_ids is not None:
            candidates = candidates.filter(pk__in=probe_ids)
        probe = (
            candidates.select_for_update(skip_locked=True)
            .filter(enabled=True, next_attempt_at__lte=now)
            .exclude(state="active")
            .filter(Q(lease_expires_at__isnull=True) | Q(lease_expires_at__lte=now))
            .order_by("next_attempt_at", "pk")
            .first()
        )
        if not probe:
            return None
        token = uuid.uuid4()
        probe.lease_token, probe.lease_expires_at = token, now + timedelta(minutes=30)
        probe.state, probe.last_attempt_at = "running", now
        probe.attempts += 1
        probe.save()
    candidate = probe.candidate
    result = {
        "candidate_id": candidate.pk,
        "company": candidate.company_name,
        "url": candidate.url,
    }
    state, error = "waiting", ""
    delay = timedelta(days=7)
    try:
        # Existing configured sources are never automatically enrolled. A disabled
        # board after enrollment is an operator stop, not permission to resume.
        if candidate.board_id and not candidate.board.enabled:
            state = "stopped"
            probe.enabled = False
        else:
            board = SimpleNamespace(
                provider=candidate.provider,
                instance=candidate.instance,
                board_key=candidate.board_key,
                base_url=candidate.url,
            )
            snapshot = (
                normalize_snapshot(fetch_snapshot(candidate.board_key))
                if candidate.provider == "greenhouse"
                else fetch_normalized(board)
            )
            qualified = sum(qualifies(row) for row in snapshot)
            result.update(
                scanned=len(snapshot),
                qualified=qualified,
                complete=getattr(snapshot, "complete", True),
                diagnostics=getattr(snapshot, "errors", []),
            )
            if qualified:
                if not AtsProbe.objects.filter(
                    pk=probe.pk,
                    enabled=True,
                    lease_token=token,
                    lease_expires_at__gt=timezone.now(),
                ).exists():
                    raise CatalogueImportError("probe_stopped")
                before = set(open_offers().values_list("pk", flat=True))
                candidate = register_source(
                    candidate.url, candidate.company_name, enable=True
                )
                ids = set(
                    open_offers()
                    .filter(sources__board_id=candidate.board_id)
                    .values_list("pk", flat=True)
                )
                result.update(
                    board_id=candidate.board_id,
                    visible_offer_ids=sorted(ids),
                    new_visible_offer_ids=sorted(ids - before),
                )
                state = "active" if ids else "waiting"
                if not ids:
                    BoardSchedule.objects.filter(board_id=candidate.board_id).update(
                        paused=True
                    )
            # A successful empty or partial screen is always revisited.
    except CatalogueImportError as exc:
        state, error = "error", exc.code
        delay = max(
            timedelta(hours=min(168, 2 ** min(probe.attempts - 1, 8))),
            timedelta(seconds=getattr(exc, "retry_after", None) or 0),
        )
    except Exception:  # noqa: BLE001 - isolate one candidate failure in the worker
        # Do not serialize exception messages (URLs or credentials). The lease
        # still protects recovery on process death, which is not caught here.
        state, error = "error", "probe_unexpected_error"
        delay = timedelta(hours=1)
    with transaction.atomic():
        locked = AtsProbe.objects.select_for_update().get(pk=probe.pk)
        if locked.lease_token != token:
            return {"candidate_id": candidate.pk, "state": "lease_lost"}
        locked.state, locked.error_code, locked.result = state, error, result
        locked.enabled = locked.enabled and probe.enabled
        if not locked.enabled:
            locked.state = "stopped"
            if result.get("board_id"):
                BoardSchedule.objects.filter(board_id=result["board_id"]).update(
                    paused=True
                )
        locked.next_attempt_at = timezone.now() + delay
        locked.lease_token = locked.lease_expires_at = None
        locked.save()
    return dict(result, state=locked.state, error_code=locked.error_code)


def metrics():
    rows = AtsProbe.objects.all()
    states = dict(rows.values_list("state").annotate(n=Count("pk")))
    due = rows.filter(enabled=True).exclude(state__in=["active", "stopped"])
    return {
        "enrolled": rows.count(),
        "tested": rows.filter(attempts__gt=0).count(),
        "states": states,
        "next_attempt_at": due.aggregate(value=Min("next_attempt_at"))["value"],
        "visible_offers": open_offers()
        .filter(sources__board__sourcecandidate__probe__state="active")
        .distinct()
        .count(),
    }
