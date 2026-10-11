"""Application invariants. All private writes lock user, then application."""

import hashlib
import json
import uuid
from datetime import timedelta

from django.core.serializers.json import DjangoJSONEncoder
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from jobboard import models as m
from jobboard.api.core import APIError, integer, lock_user
from jobboard.integrations.submission import fetch_form, get_adapter
from jobboard.models.choices import ACTIVE_RUN_STATUSES, ApplicationStatus


def canonical(value):
    return json.dumps(
        value,
        cls=DjangoJSONEncoder,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def private_application(user, pk, lock=False):
    qs = m.Application.objects.filter(user=user)
    if lock:
        qs = qs.select_for_update()
    return qs.get(pk=pk)


def event(application, kind, origin="user", run=None, payload=None, dedupe_key=None):
    return m.ApplicationEvent.objects.create(
        application=application,
        run=run,
        kind=kind,
        origin=origin,
        happened_at=timezone.now(),
        status_after=application.status,
        payload=payload or {},
        dedupe_key=dedupe_key,
    )


def available(source):
    offer = source.offer
    if (
        not source.board.enabled
        or source.source_status != "active"
        or offer.status != "open"
        or (offer.expires_at and offer.expires_at <= timezone.now())
    ):
        raise APIError("offer_unavailable", "This offer is no longer available.", 409)


def idle(application):
    if application.status != "draft" or application.submitted_at:
        raise APIError(
            "already_submitted",
            "The application has already progressed beyond its draft.",
            409,
        )
    if application.runs.filter(status__in=ACTIVE_RUN_STATUSES).exists():
        raise APIError("run_active", "Resolve or cancel the current run first.", 409)


@transaction.atomic
def create_application(user, offer_id, source_id):
    lock_user(user)
    existing = m.Application.objects.filter(user=user, offer_id=offer_id).first()
    if existing:
        return existing
    source = m.OfferSource.objects.select_related("offer", "board").get(
        pk=source_id, offer_id=offer_id
    )
    available(source)
    app = m.Application.objects.create(user=user, offer=source.offer, source=source)
    event(app, "application_created")
    return app


def offer_snapshot(source):
    offer = source.offer
    return {
        "offer_id": offer.pk,
        "title": offer.title,
        "company_name": offer.company.name,
        "description_text": offer.description,
        "locations": list(offer.locations.values("id", "name", "country_code")),
        "compensation": list(offer.compensation_bands.values()),
        "source": {
            "provider": source.board.provider,
            "instance": source.board.instance,
            "board_key": source.board.board_key,
            "external_id": source.external_id,
            "apply_url": source.apply_url,
        },
        "captured_at": timezone.now().isoformat(),
    }


def content_hash(revision):
    links = list(
        revision.document_links.select_related("document").order_by(
            "document_id", "purpose"
        )
    )
    value = {
        "schema_version": revision.schema_version,
        "profile": revision.profile_snapshot,
        "offer": revision.offer_snapshot,
        "form": revision.form_snapshot,
        "answers": revision.answers,
        "documents": [
            {
                "id": link.document_id,
                "sha256": link.document.sha256,
                "purpose": link.purpose,
            }
            for link in links
        ],
    }
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def checked_documents(user, ids):
    if not isinstance(ids, list) or len(ids) > 2:
        raise APIError("invalid_documents", "Provide up to two document IDs.")
    ids = [integer(pk, "document_id") for pk in ids]
    if len(set(ids)) != len(ids):
        raise APIError("invalid_documents", "Duplicate document IDs.")
    docs = list(
        m.Document.objects.filter(
            owner=user, pk__in=ids, status="ready", kind__in=["resume", "cover_letter"]
        )
    )
    if len(docs) != len(ids):
        raise APIError("not_found", "Document not found.", 404)
    if len({d.kind for d in docs}) != len(docs):
        raise APIError(
            "invalid_documents", "Only one document of each kind is allowed."
        )
    return docs


def checked_answers(answers, form, *, user_input=False):
    if (
        not isinstance(answers, list)
        or len(answers) > 200
        or len(canonical(answers)) > 200000
    ):
        raise APIError("invalid_answers", "Answers must be a bounded list.")
    fields = {field["key"]: field for field in form["fields"]}
    seen, result = set(), []
    for answer in answers:
        if (
            not isinstance(answer, dict)
            or set(answer)
            - {"field_key", "value", "origin", "source_refs", "confirmed_at"}
            or not {"field_key", "value"} <= set(answer)
        ):
            raise APIError("invalid_answers", "Each answer needs field_key and value.")
        key, value = answer["field_key"], answer["value"]
        if (
            not isinstance(key, str)
            or key not in fields
            or key in seen
            or fields[key]["type"] == "file"
        ):
            raise APIError("invalid_answers", "Unknown, duplicate or file answer key.")
        field = fields[key]
        seen.add(key)
        if value is not None:
            if field["type"] == "text" and (
                not isinstance(value, str) or len(value) > 10000
            ):
                raise APIError(
                    "invalid_answers",
                    "Text answers must contain at most 10000 characters.",
                )
            options = [option["value"] for option in field.get("options", [])]
            if field["type"] == "select" and (
                type(value) not in (str, int) or value not in options
            ):
                raise APIError("invalid_answers", "Unknown answer option.")
            if field["type"] == "multi_select" and (
                not isinstance(value, list)
                or any(type(v) not in (str, int) or v not in options for v in value)
                or len(set(value)) != len(value)
            ):
                raise APIError(
                    "invalid_answers", "Unknown or duplicate answer options."
                )
            if key == "email" and value:
                validate_email(value)
            if (
                key in {"first_name", "last_name", "email", "phone"}
                and len(value) > 255
            ):
                raise APIError(
                    "invalid_answers", "Identity answers are limited to 255 characters."
                )
        result.append(
            {
                "field_key": key,
                "value": value,
                "origin": "user" if user_input else answer.get("origin", "profile"),
                "source_refs": [] if user_input else answer.get("source_refs", []),
                "confirmed_at": timezone.now().isoformat() if user_input else None,
            }
        )
    return sorted(result, key=lambda answer: answer["field_key"])


def missing_fields(revision):
    answers = {a["field_key"]: a["value"] for a in revision.answers}
    kinds = set(revision.document_links.values_list("purpose", flat=True))
    return [
        f["key"]
        for f in revision.form_snapshot["fields"]
        if f["required"]
        and (
            (f["type"] == "file" and f["key"] not in kinds)
            or (
                f["type"] != "file"
                and (
                    answers.get(f["key"]) is None
                    or answers.get(f["key"]) == ""
                    or answers.get(f["key"]) == []
                )
            )
        )
    ]


def new_revision(application, profile, offer, form, answers, documents):
    file_keys = {f["key"] for f in form["fields"] if f["type"] == "file"}
    if any(d.kind not in file_keys for d in documents):
        raise APIError(
            "unexpected_document", "This form does not request that document."
        )
    if (
        len(
            canonical(
                {"profile": profile, "offer": offer, "form": form, "answers": answers}
            )
        )
        > 1024 * 1024
    ):
        raise APIError("dossier_too_large", "The dossier exceeds the 1 MiB limit.", 413)
    no = (application.revisions.aggregate(n=Max("revision_no"))["n"] or 0) + 1
    revision = m.ApplicationRevision.objects.create(
        application=application,
        user=application.user,
        revision_no=no,
        profile_snapshot=json.loads(canonical(profile)),
        offer_snapshot=json.loads(canonical(offer)),
        form_snapshot=form,
        answers=answers,
        generator_version="confirmed-profile-v1",
    )
    for document in documents:
        m.RevisionDocument.objects.create(
            revision=revision,
            user=application.user,
            document=document,
            purpose=document.kind,
        )
    revision.content_hash = content_hash(revision)
    revision.sealed_at = timezone.now()
    revision.save(update_fields=["content_hash", "sealed_at"])
    application.authorizations.filter(revoked_at__isnull=True).update(
        revoked_at=timezone.now()
    )
    event(
        application,
        "revision_prepared",
        payload={"revision_id": revision.pk, "revision_no": no},
    )
    return revision


def prepare(user, application_id):
    from jobboard.services.profiles import snapshot_profile

    app = private_application(user, application_id)
    source = m.OfferSource.objects.select_related("board", "offer__company").get(
        pk=app.source_id
    )
    available(source)
    form = fetch_form(source)  # External I/O before locks.
    with transaction.atomic():
        lock_user(user)
        app = private_application(user, application_id, lock=True)
        idle(app)
        fresh = m.OfferSource.objects.select_related("board", "offer__company").get(
            pk=app.source_id
        )
        if offer_snapshot(fresh)["source"] != offer_snapshot(source)["source"]:
            raise APIError(
                "source_changed", "The offer source changed; prepare again.", 409
            )
        available(fresh)
        profile = snapshot_profile(user)
        candidate = m.CandidateProfile.objects.get(user=user)
        file_keys = {f["key"] for f in form["fields"] if f["type"] == "file"}
        documents = checked_documents(
            user,
            [candidate.current_resume_id]
            if candidate.current_resume_id and "resume" in file_keys
            else [],
        )
        profile["identity"] = {
            "first_name": candidate.first_name,
            "last_name": candidate.last_name,
            "email": user.email,
            "phone": candidate.phone,
        }
        profile["captured_at"] = timezone.now().isoformat()
        # Only explicit identity facts are reused; full_name is never guessed into first/last.
        facts = {
            "first_name": candidate.first_name,
            "last_name": candidate.last_name,
            "email": user.email,
            "phone": candidate.phone,
        }
        answers = [
            {
                "field_key": key,
                "value": value,
                "origin": "profile",
                "source_refs": ["profile:" + str(candidate.pk)],
            }
            for key, value in facts.items()
            if value
            and key in {f["key"] for f in form["fields"] if f["type"] == "text"}
        ]
        return new_revision(
            app,
            profile,
            offer_snapshot(fresh),
            form,
            checked_answers(answers, form),
            documents,
        )


@transaction.atomic
def revise(user, application_id, answers, document_ids):
    lock_user(user)
    app = private_application(user, application_id, lock=True)
    idle(app)
    prior = app.revisions.order_by("-revision_no").first()
    if not prior:
        raise APIError("not_prepared", "Prepare a dossier first.", 409)
    return new_revision(
        app,
        prior.profile_snapshot,
        prior.offer_snapshot,
        prior.form_snapshot,
        checked_answers(answers, prior.form_snapshot, user_input=True),
        checked_documents(user, document_ids),
    )


def document_bytes(revision):
    from jobboard.services.documents import read_document

    return {
        link.purpose: (link.document, read_document(link.document))
        for link in revision.document_links.select_related("document")
    }


def verify_revision(revision):
    if not revision.sealed_at or revision.content_hash != content_hash(revision):
        raise APIError("revision_changed", "The dossier integrity check failed.", 409)
    missing = missing_fields(revision)
    if missing:
        raise APIError(
            "missing_answers",
            "Complete required application fields.",
            409,
            {"fields": missing},
        )
    if not revision.form_snapshot.get("supported"):
        raise APIError(
            "unsupported_form",
            "This form needs a compatible submission connector.",
            409,
        )
    if revision.document_links.exclude(document__status="ready").exists():
        raise APIError(
            "document_unavailable", "A document is no longer available.", 409
        )


def verify_destination(application, revision):
    source = m.OfferSource.objects.select_related("board", "offer__company").get(
        pk=application.source_id
    )
    available(source)
    if offer_snapshot(source)["source"] != revision.offer_snapshot["source"]:
        raise APIError(
            "source_changed", "Prepare and approve the updated destination.", 409
        )
    return source


def approve(user, application_id, revision_id, approved_hash, key):
    try:
        key = uuid.UUID(str(key))
    except (ValueError, TypeError, AttributeError):
        raise APIError(
            "invalid_idempotency_key", "Provide a UUID idempotency key."
        ) from None
    preview = m.ApplicationRevision.objects.get(
        pk=revision_id, application_id=application_id, user=user
    )
    document_bytes(preview)
    with transaction.atomic():
        lock_user(user)
        app = private_application(user, application_id, lock=True)
        existing = m.AgentRun.objects.filter(idempotency_key=key).first()
        if existing:
            if (
                existing.user_id != user.pk
                or existing.application_id != app.pk
                or existing.revision_id != preview.pk
                or approved_hash != preview.content_hash
            ):
                raise APIError(
                    "idempotency_conflict", "This key belongs to another request.", 409
                )
            return existing
        idle(app)
        revision = app.revisions.order_by("-revision_no").first()
        if revision.pk != preview.pk or approved_hash != revision.content_hash:
            raise APIError(
                "stale_revision", "Review the latest dossier before approval.", 409
            )
        verify_revision(revision)
        get_adapter(verify_destination(app, revision)).ensure_enabled()
        now = timezone.now()
        app.authorizations.filter(revoked_at__isnull=True).update(revoked_at=now)
        authorization = m.SubmissionAuthorization.objects.create(
            application=app,
            revision=revision,
            user=user,
            approved_hash=approved_hash,
            expires_at=now + timedelta(hours=24),
        )
        attempt = (app.runs.aggregate(n=Max("attempt_no"))["n"] or 0) + 1
        run = m.AgentRun.objects.create(
            application=app,
            revision=revision,
            user=user,
            authorization=authorization,
            purpose="submit",
            phase="filling",
            attempt_no=attempt,
            idempotency_key=key,
        )
        m.OutboxMessage.objects.create(
            topic="application.submit",
            dedupe_key=f"submit:{run.pk}",
            owner=user,
            payload={"agent_run_id": run.pk},
        )
        event(
            app, "submission_authorized", run=run, payload={"revision_id": revision.pk}
        )
        return run


@transaction.atomic
def revoke(user, application_id):
    lock_user(user)
    app = private_application(user, application_id, lock=True)
    runs = app.runs.filter(status__in=ACTIVE_RUN_STATUSES)
    if (
        runs.filter(phase__in=["submitting", "verifying"]).exists()
        or runs.filter(status="uncertain").exists()
    ):
        raise APIError(
            "submission_started",
            "Submission may already have occurred. Verify the outcome first.",
            409,
        )
    now = timezone.now()
    app.authorizations.filter(revoked_at__isnull=True).update(revoked_at=now)
    ids = list(runs.values_list("id", flat=True))
    runs.update(
        status="cancelled",
        phase="done",
        finished_at=now,
        worker_token=None,
        lease_expires_at=None,
    )
    m.OutboxMessage.objects.filter(
        dedupe_key__in=[f"submit:{pk}" for pk in ids]
    ).update(processed_at=now)
    event(app, "authorization_revoked")
    return app


@transaction.atomic
def update_status(user, application_id, status, reason):
    lock_user(user)
    app = private_application(user, application_id, lock=True)
    if (
        not isinstance(status, str)
        or status not in ApplicationStatus.values
        or not isinstance(reason, str)
        or not 1 <= len(reason.strip()) <= 2000
    ):
        raise APIError("invalid_status", "Provide a valid status and reason.")
    if app.runs.filter(status__in=ACTIVE_RUN_STATUSES).exists():
        raise APIError(
            "run_active",
            "Resolve the current run before changing the recruitment status.",
            409,
        )
    if status == "draft" and app.submitted_at:
        raise APIError(
            "already_submitted",
            "A submitted application cannot become a new draft.",
            409,
        )
    old = app.status
    app.status = status
    if status != "draft" and not app.submitted_at:
        app.submitted_at = timezone.now()
    app.save(update_fields=["status", "submitted_at", "updated_at"])
    event(
        app,
        "status_corrected",
        payload={"from_status": old, "to_status": status, "reason": reason},
    )
    return app


@transaction.atomic
def resolve(user, application_id, outcome, evidence):
    lock_user(user)
    app = private_application(user, application_id, lock=True)
    run = app.runs.select_for_update().filter(status="uncertain").first()
    if not run:
        raise APIError("not_uncertain", "There is no uncertain run to resolve.", 409)
    if run.lease_expires_at and run.lease_expires_at > timezone.now():
        raise APIError(
            "worker_pending", "Wait for the in-flight worker lease to expire.", 409
        )
    if (
        not isinstance(outcome, str)
        or outcome not in {"submitted", "not_submitted"}
        or not isinstance(evidence, str)
        or not 1 <= len(evidence.strip()) <= 300
    ):
        raise APIError(
            "invalid_resolution",
            "Provide the verified outcome and a reference or explanation.",
        )
    now = timezone.now()
    run.status = "succeeded" if outcome == "submitted" else "failed"
    run.phase, run.finished_at, run.worker_token = "done", now, None
    run.external_receipt = evidence if outcome == "submitted" else None
    run.error_code = None if outcome == "submitted" else "user_verified_not_submitted"
    run.save()
    if outcome == "submitted":
        app.status, app.submitted_at, app.external_reference = (
            "submitted",
            now,
            evidence,
        )
        app.save(
            update_fields=["status", "submitted_at", "external_reference", "updated_at"]
        )
    event(
        app,
        "submission_resolved",
        run=run,
        payload={"outcome": outcome, "evidence": evidence},
    )
    return run
