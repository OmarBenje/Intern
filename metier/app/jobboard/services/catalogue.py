"""Mutualized catalogue reconciliation with fenced leases and confirmed absence."""

import hashlib
import uuid
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from jobboard.integrations.greenhouse_catalogue import (
    CatalogueImportError,
    fetch_snapshot,
    normalize_snapshot,
)
from jobboard.integrations.public_catalogue import digest, fetch_normalized
from jobboard.models import (
    BoardSchedule,
    ImportRun,
    Location,
    Offer,
    OfferSource,
    SourceBoard,
    SourceObservation,
    SourceRevision,
)


def _claim(board_id):
    with transaction.atomic():
        board = SourceBoard.objects.select_for_update().get(pk=board_id)
        if (
            not board.enabled
            or not board.company_id
            or board.provider
            not in (
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
                "jobspy",
                "eures",
                "wttj",
                "jobtech",
                "bundesagentur", "nav",
            )
            or board.instance
            not in (
                ("global", "eu")
                if board.provider == "lever"
                else ("de", "com")
                if board.provider == "personio"
                else ("global",)
            )
        ):
            raise CatalogueImportError("board_not_configured")
        schedule, _ = BoardSchedule.objects.get_or_create(board=board)
        now = timezone.now()
        if schedule.paused:
            raise CatalogueImportError("board_paused")
        if schedule.lease_expires_at and schedule.lease_expires_at > now:
            raise CatalogueImportError("board_busy")
        schedule.lease_token = uuid.uuid4()
        schedule.lease_expires_at = now + timedelta(minutes=15)
        schedule.save(update_fields=["lease_token", "lease_expires_at"])
        board.collection_checkpoint = schedule.collection_checkpoint
        return board, schedule.lease_token, ImportRun.objects.create(board=board)


def _reconcile_absence(board, schedule, seen, now):
    missing = board.sources.exclude(pk__in=seen).exclude(source_status="closed")
    affected = []
    for source in missing:
        observation, _ = SourceObservation.objects.get_or_create(source=source)
        observation.missing_since = observation.missing_since or now
        observation.missing_count += 1
        observation.save()
        confirmed = (
            observation.missing_count >= 2
            and now - observation.missing_since
            >= timedelta(hours=schedule.missing_confirmation_hours)
        )
        source.source_status = "closed" if confirmed else "missing"
        source.last_checked_at = now
        source.save(update_fields=["source_status", "last_checked_at"])
        affected.append(source.offer_id)
    # Missing and unknown publications are not proof of closure.
    Offer.objects.filter(pk__in=affected, status="open").exclude(
        sources__source_status__in=["active", "missing", "unknown"]
    ).update(status="closed", updated_at=now)


def import_board(board_id, *, supplied_snapshot=None):
    board, token, run = _claim(board_id)
    try:
        if supplied_snapshot is not None and board.provider not in ("jobspy", "eures", "wttj", "jobtech", "bundesagentur", "nav"):
            raise CatalogueImportError("unexpected_supplied_snapshot")
        if board.provider in ("jobspy", "eures", "wttj", "jobtech", "bundesagentur", "nav") and (
            supplied_snapshot is None or supplied_snapshot.complete
        ):
            raise CatalogueImportError("jobspy_query_required")
        snapshot = (
            supplied_snapshot
            if supplied_snapshot is not None
            else (
                normalize_snapshot(fetch_snapshot(board.board_key))
                if board.provider == "greenhouse"
                else fetch_normalized(board)
            )
        )
        complete = getattr(snapshot, "complete", True)
        diagnostics = getattr(snapshot, "errors", [])
        with transaction.atomic():
            locked = SourceBoard.objects.select_for_update().get(pk=board.pk)
            schedule = BoardSchedule.objects.select_for_update().get(board=locked)
            now = timezone.now()
            if (
                schedule.lease_token != token
                or not schedule.lease_expires_at
                or schedule.lease_expires_at <= now
            ):
                raise CatalogueImportError("lease_lost")
            if (
                not locked.enabled
                or schedule.paused
                or (
                    locked.board_key,
                    locked.provider,
                    locked.company_id,
                    locked.instance,
                )
                != (board.board_key, board.provider, board.company_id, board.instance)
            ):
                raise CatalogueImportError("board_changed")
            if locked.last_success_at and locked.last_success_at >= run.started_at:
                raise CatalogueImportError("superseded_snapshot")
            previous_count = locked.sources.exclude(source_status="closed").count()
            suspicious = previous_count > 0 and (
                not snapshot
                or previous_count >= 20
                and len(snapshot) < previous_count / 2
            )
            signature = digest(sorted(job["external_id"] for job in snapshot))
            quarantine = False
            if suspicious:
                if schedule.quarantine_hash != signature:
                    schedule.quarantine_hash, schedule.quarantine_since = signature, now
                quarantine = now - schedule.quarantine_since < timedelta(
                    hours=schedule.missing_confirmation_hours
                )
            else:
                schedule.quarantine_hash, schedule.quarantine_since = "", None
            seen = []
            for job in snapshot:
                source = OfferSource.objects.filter(
                    board=locked, external_id=job["external_id"]
                ).first()
                reopening = bool(source and source.source_status == "closed")
                preferred = False
                if source:
                    offer = Offer.objects.select_for_update().get(pk=source.offer_id)
                    # A verified merge retains the employer board as content authority.
                    from jobboard.services.engine_merges import preferred_content_board
                    shared = offer.sources.exclude(board=locked).exists()
                    preferred = shared and preferred_content_board(offer, locked)
                    if preferred or not shared:
                        offer.title, offer.description = (
                            job["title"],
                            job["description"],
                        )
                        offer.contract_type = job.get("contract_type", "unknown")
                        offer.work_mode = job.get("work_mode", "unknown")
                        if "expires_at" in job:
                            offer.expires_at = job["expires_at"]
                    if offer.status != "hidden":
                        offer.status = "open"
                    offer.save(
                        update_fields=[
                            "title",
                            "description",
                            "contract_type",
                            "work_mode",
                            "status",
                            "updated_at",
                            "expires_at",
                        ]
                    )
                else:
                    offer = Offer.objects.create(
                        company=locked.company,
                        title=job["title"],
                        description=job["description"],
                        contract_type=job.get("contract_type", "unknown"),
                        work_mode=job.get("work_mode", "unknown"),
                        expires_at=job.get("expires_at"),
                    )
                from jobboard.services.engine_quality import structured_country_code

                locations = []
                details = job.get("location_details")
                if details is None:
                    details = [
                        {"name": label, "country": ""}
                        for label in job.get(
                            "locations", [job["location"]] if job["location"] else []
                        )
                    ]
                for detail in details:
                    label = detail["name"]
                    code = structured_country_code(detail.get("country", ""))
                    identity = label.casefold() + (":" + code if code else "")
                    key = "source:" + hashlib.sha256(identity.encode()).hexdigest()
                    location, _ = Location.objects.get_or_create(
                        canonical_key=key,
                        defaults={"name": label, "country_code": code},
                    )
                    locations.append(location)
                if source and not preferred and offer.sources.exclude(board=locked).exists():
                    offer.locations.add(*locations)
                else:
                    offer.locations.set(locations)
                source, _ = OfferSource.objects.update_or_create(
                    board=locked,
                    external_id=job["external_id"],
                    defaults={
                        "offer": offer,
                        "origin_url": job["url"],
                        "apply_url": job.get("apply_url", job["url"]),
                        "source_status": "active",
                        "first_seen_at": source.first_seen_at if source else now,
                        "last_seen_at": now,
                        "last_checked_at": now,
                        "last_seen_run": run,
                        "content_hash": job["hash"],
                        "raw_payload": job["raw"],
                        "raw_expires_at": now + timedelta(days=30),
                    },
                )
                semantic_hash = digest(
                    {
                        field: job.get(field)
                        for field in (
                            "title",
                            "description",
                            "location",
                            "locations",
                            "location_details",
                            "contract_type",
                            "work_mode",
                        )
                    }
                )
                SourceRevision.objects.get_or_create(
                    source=source,
                    raw_hash=job["hash"],
                    defaults={"semantic_hash": semantic_hash, "payload": job["raw"]},
                )
                SourceObservation.objects.update_or_create(
                    source=source, defaults={"missing_since": None, "missing_count": 0}
                )
                from jobboard.models import OfferEnrichment
                from jobboard.services.engine_quality import enrich_offer

                previous_version = (
                    OfferEnrichment.objects.filter(offer=offer)
                    .values_list("content_version", flat=True)
                    .first()
                )
                enrich_offer(offer)
                if reopening and previous_version is not None:
                    OfferEnrichment.objects.filter(
                        offer=offer, content_version=previous_version
                    ).update(content_version=previous_version + 1, event_at=now)
                seen.append(source.pk)
            if complete and not quarantine:
                _reconcile_absence(locked, schedule, seen, now)
            locked.last_success_at = now
            locked.save(update_fields=["last_success_at"])
            schedule.failure_count = 0
            schedule.last_error_code = (
                "partial_snapshot"
                if not complete
                else "snapshot_quarantined"
                if quarantine
                else ""
            )
            schedule.next_run_at = now + timedelta(
                minutes=schedule.interval_minutes, seconds=locked.pk % 61
            )
            if board.provider == "eightfold" and hasattr(snapshot, "checkpoint"):
                # Commit progress with the imported rows, behind the same lease fence.
                schedule.collection_checkpoint = snapshot.checkpoint
                schedule.next_run_at = max(
                    schedule.next_run_at,
                    now + timedelta(seconds=getattr(snapshot, "retry_after", 0)),
                )
            schedule.lease_token = schedule.lease_expires_at = None
            schedule.save()
            run.status, run.finished_at, run.is_full_snapshot, run.seen_count = (
                "succeeded",
                now,
                complete,
                len(snapshot),
            )
            run.diagnostics = diagnostics
            run.error_code = schedule.last_error_code or None
            run.save(
                update_fields=[
                    "status",
                    "finished_at",
                    "is_full_snapshot",
                    "diagnostics",
                    "seen_count",
                    "error_code",
                ]
            )
        return run
    except Exception as exc:
        error = exc.code if isinstance(exc, CatalogueImportError) else "import_failed"
        ImportRun.objects.filter(pk=run.pk).update(
            status="failed", finished_at=timezone.now(), error_code=error
        )
        with transaction.atomic():
            schedule = BoardSchedule.objects.select_for_update().get(board=board)
            if schedule.lease_token == token:
                schedule.failure_count += 1
                seconds = min(86400, max(60, 60 * 2 ** min(schedule.failure_count, 10)))
                if schedule.failure_count >= 5:
                    seconds = max(seconds, 21600)
                seconds = max(seconds, getattr(exc, "retry_after", None) or 0)
                schedule.next_run_at = timezone.now() + timedelta(
                    seconds=seconds + board.pk % 61
                )
                schedule.last_error_code = error
                schedule.lease_token = schedule.lease_expires_at = None
                schedule.save()
        raise
