"""PostgreSQL outbox consumer with leases, fencing and conservative recovery."""

import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from jobboard import models as m
from jobboard.api.core import APIError
from jobboard.integrations.submission import SubmissionResult, get_adapter
from jobboard.services.applications import (
    document_bytes,
    event,
    verify_destination,
    verify_revision,
)


def lock_run(run_id, *, skip_locked=False):
    candidate = m.AgentRun.objects.filter(pk=run_id).first()
    if candidate is None:
        return None, None, None
    user = (
        get_user_model()
        .objects.select_for_update(skip_locked=skip_locked)
        .filter(pk=candidate.user_id)
        .first()
    )
    if user is None:
        return None, None, None
    app = m.Application.objects.select_for_update().get(pk=candidate.application_id)
    run = m.AgentRun.objects.select_for_update().get(pk=run_id)
    return user, app, run


def check_authorization(user, run):
    now = timezone.now()
    auth = m.SubmissionAuthorization.objects.get(pk=run.authorization_id)
    if (
        not user.is_active
        or auth.revoked_at
        or auth.expires_at <= now
        or auth.approved_hash != run.revision.content_hash
    ):
        raise APIError(
            "authorization_invalid",
            "The submission authorization is no longer valid.",
            409,
        )
    if (
        auth.user_id != run.user_id
        or auth.revision_id != run.revision_id
        or auth.application_id != run.application_id
    ):
        raise APIError(
            "authorization_invalid", "The submission authorization does not match.", 409
        )
    verify_revision(run.revision)


def close_outbox(run):
    m.OutboxMessage.objects.filter(
        dedupe_key=f"submit:{run.pk}", processed_at__isnull=True
    ).update(processed_at=timezone.now(), lease_token=None, lease_expires_at=None)


def fail_locked(app, run, code, uncertain=False):
    run.status = "uncertain" if uncertain else "failed"
    run.error_code, run.finished_at = code, timezone.now()
    run.phase = "verifying" if uncertain else "done"
    run.worker_token = None
    run.save()
    close_outbox(run)
    event(
        app,
        "submission_uncertain" if uncertain else "submission_failed",
        "system",
        run,
        {"reason_code": code},
    )


def recover_expired(limit=100):
    ids = list(
        m.AgentRun.objects.filter(status="running")
        .filter(
            Q(lease_expires_at__lte=timezone.now()) | Q(lease_expires_at__isnull=True)
        )
        .values_list("pk", flat=True)[:limit]
    )
    for pk in ids:
        with transaction.atomic():
            user, app, run = lock_run(pk, skip_locked=True)
            if (
                user is None
                or run.status != "running"
                or (run.lease_expires_at and run.lease_expires_at > timezone.now())
            ):
                continue
            fail_locked(
                app,
                run,
                "worker_lease_expired",
                uncertain=run.phase in {"submitting", "verifying"},
            )
    return len(ids)


def claim():
    ids = list(
        m.AgentRun.objects.filter(status="queued")
        .order_by("created_at", "pk")
        .values_list("pk", flat=True)[:100]
    )
    for pk in ids:
        with transaction.atomic():
            user, app, run = lock_run(pk, skip_locked=True)
            if user is None or run.status != "queued":
                continue
            message = (
                m.OutboxMessage.objects.select_for_update(skip_locked=True)
                .filter(
                    dedupe_key=f"submit:{run.pk}",
                    topic="application.submit",
                    processed_at__isnull=True,
                    available_at__lte=timezone.now(),
                )
                .first()
            )
            if not message:
                continue
            try:
                check_authorization(user, run)
            except APIError as exc:
                fail_locked(app, run, exc.code)
                continue
            now, token = timezone.now(), uuid.uuid4()
            run.status, run.phase = "running", "filling"
            run.worker_token, run.started_at, run.heartbeat_at = token, now, now
            run.lease_expires_at = now + timedelta(seconds=settings.AGENT_LEASE_SECONDS)
            run.save()
            message.attempts += 1
            message.lease_token, message.lease_expires_at = token, run.lease_expires_at
            message.save(update_fields=["attempts", "lease_token", "lease_expires_at"])
            event(app, "submission_started", "system", run)
            return run.pk, token
    return None


def fenced(run, token):
    if (
        run.status != "running"
        or run.worker_token != token
        or not run.lease_expires_at
        or run.lease_expires_at <= timezone.now()
    ):
        raise APIError("stale_worker", "Worker no longer owns this run.", 409)


@transaction.atomic
def begin_submission(run_id, token, form_fingerprint):
    user, app, run = lock_run(run_id)
    if run is None:
        raise APIError("stale_worker", "The run no longer exists.", 409)
    fenced(run, token)
    check_authorization(user, run)
    if app.status != "draft" or app.submitted_at:
        raise APIError("already_submitted", "Application already submitted.", 409)
    source = verify_destination(app, run.revision)
    adapter = get_adapter(source)
    adapter.ensure_enabled()
    if form_fingerprint != run.revision.form_snapshot["form_fingerprint"]:
        raise APIError(
            "form_changed", "The source form changed; prepare and review again.", 409
        )
    run.phase = "submitting"
    run.adapter_version = adapter.version
    run.heartbeat_at = timezone.now()
    run.lease_expires_at = timezone.now() + timedelta(
        seconds=settings.AGENT_LEASE_SECONDS
    )
    run.save(
        update_fields=["phase", "adapter_version", "heartbeat_at", "lease_expires_at"]
    )
    return run, adapter


@transaction.atomic
def finish(run_id, token, result):
    user, app, run = lock_run(run_id)
    if run is None:
        raise APIError("stale_worker", "The run no longer exists.", 409)
    fenced(run, token)
    if result.status not in {"succeeded", "failed", "uncertain"}:
        result = SubmissionResult("uncertain", error_code="invalid_connector_result")
    if result.status == "succeeded" and not result.receipt:
        result = SubmissionResult("uncertain", error_code="missing_receipt")
    if result.status != "succeeded":
        fail_locked(
            app,
            run,
            result.error_code or "connector_error",
            uncertain=result.status == "uncertain",
        )
        return run
    now = timezone.now()
    run.status, run.phase, run.external_receipt = (
        "succeeded",
        "done",
        result.receipt[:300],
    )
    run.finished_at, run.worker_token = now, None
    run.save()
    app.status, app.submitted_at, app.external_reference = (
        "submitted",
        now,
        run.external_receipt,
    )
    app.save(
        update_fields=["status", "submitted_at", "external_reference", "updated_at"]
    )
    event(
        app,
        "submission_confirmed",
        "provider",
        run,
        {"receipt": run.external_receipt},
        f"confirmed:{run.pk}",
    )
    close_outbox(run)
    return run


def process_one():
    recover_expired()
    claimed = claim()
    if claimed is None:
        return False
    run_id, token = claimed
    dangerous = False
    try:
        run = m.AgentRun.objects.select_related(
            "revision", "application__source__board"
        ).get(pk=run_id)
        adapter = get_adapter(run.application.source)
        adapter.ensure_enabled()
        documents = document_bytes(run.revision)
        form = (
            adapter.fetch_form()
        )  # bounded external calls, no database transaction held
        run, adapter = begin_submission(run_id, token, form["form_fingerprint"])
        dangerous = True
        result = adapter.submit(run.revision, documents)
        finish(run_id, token, result)
    except Exception as exc:
        # Codes only: never persist provider bodies, credentials or candidate answers.
        code = exc.code if isinstance(exc, APIError) else "worker_error"
        try:
            finish(
                run_id,
                token,
                SubmissionResult(
                    "uncertain" if dangerous else "failed", error_code=code
                ),
            )
        except APIError:
            # A lost lease belongs to recovery; an old worker cannot overwrite it.
            pass
    return True
