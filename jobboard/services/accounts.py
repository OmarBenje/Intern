"""Private account export and resumable deletion, with storage I/O outside locks."""

import tempfile
import zipfile
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from jobboard import models as m
from jobboard.api.core import APIError, lock_user

MAX_EXPORT_BYTES = 100 * 1024 * 1024
SAFE_PHASES = ("preparing", "filling", "awaiting_user")


def _rows(queryset, budget, excluded=()):
    fields = [
        f.attname
        for f in queryset.model._meta.concrete_fields
        if f.name not in excluded
    ]
    rows = []
    for row in queryset.order_by("pk").values(*fields).iterator(chunk_size=100):
        # Stop collecting large histories before allocating an unbounded export.
        budget[0] += len(DjangoJSONEncoder().encode(row).encode("utf-8"))
        if budget[0] > MAX_EXPORT_BYTES:
            raise APIError(
                "export_too_large", "Account export exceeds 100 MiB.", status=413
            )
        rows.append(row)
    return rows


def export_account(user):
    # The account lock provides a coherent DB snapshot against all candidate writes.
    with transaction.atomic():
        user = lock_user(user)
        profiles = m.CandidateProfile.objects.filter(user=user)
        applications = m.Application.objects.filter(user=user)
        preferences = m.SearchPreference.objects.filter(profile__user=user)
        document_query = m.Document.objects.filter(owner=user)
        byte_size = document_query.aggregate(total=Sum("byte_size"))["total"] or 0
        if byte_size > MAX_EXPORT_BYTES or document_query.count() > 10000:
            raise APIError(
                "export_too_large", "Account export exceeds 100 MiB.", status=413
            )
        budget = [byte_size]

        def rows(queryset, excluded=()):
            return _rows(queryset, budget, excluded)

        documents = list(document_query.order_by("pk"))
        if any(d.status != "ready" for d in documents):
            raise APIError(
                "export_not_ready", "Documents are still being processed.", status=409
            )
        if sum(d.byte_size for d in documents) > MAX_EXPORT_BYTES:
            raise APIError(
                "export_too_large", "Account export exceeds 100 MiB.", status=413
            )
        data = {
            "recruiter_profile": rows(m.RecruiterProfile.objects.filter(user=user), ("email_code_hash", "email_code_expires_at")),
            "recruiter_jobs": rows(m.RecruiterJob.objects.filter(owner__user=user)),
            "recruiter_integrations": rows(m.RecruiterIntegration.objects.filter(owner__user=user)),
            "recruiter_applications": rows(m.RecruiterApplicant.objects.filter(application__user=user)),
            "schema_version": 1,
            "exported_at": timezone.now(),
            "account": {
                k: getattr(user, k)
                for k in (
                    "id",
                    "username",
                    "email",
                    "first_name",
                    "last_name",
                    "date_joined",
                )
            },
            "profiles": rows(profiles),
            "preferences": rows(preferences),
            "documents": rows(
                m.Document.objects.filter(owner=user), ("bucket", "object_key")
            ),
            "applications": rows(applications),
            "revisions": rows(m.ApplicationRevision.objects.filter(user=user)),
            "revision_documents": rows(m.RevisionDocument.objects.filter(user=user)),
            "authorizations": rows(m.SubmissionAuthorization.objects.filter(user=user)),
            "runs": rows(
                m.AgentRun.objects.filter(user=user),
                ("worker_token", "idempotency_key"),
            ),
            "events": rows(m.ApplicationEvent.objects.filter(application__user=user)),
            "tasks": rows(m.ApplicationTask.objects.filter(application__user=user)),
            "interviews": rows(m.Interview.objects.filter(application__user=user)),
            "saved_offers": rows(m.SavedOffer.objects.filter(user=user)),
        }
        for name, model in (
            ("saved_searches", m.SavedSearch),
            ("offer_feedback", m.OfferFeedback),
            ("company_preferences", m.CompanyPreference),
            ("offer_reports", m.OfferReport),
            ("alerts", m.AlertEvent),
            ("external_opportunities", m.ExternalOpportunity),
        ):
            data[name] = rows(model.objects.filter(user=user))
        for name, model in (
            ("experiences", m.Experience),
            ("education", m.Education),
            ("projects", m.Project),
            ("skills", m.CandidateSkill),
            ("work_authorizations", m.WorkAuthorization),
        ):
            data[name] = rows(model.objects.filter(profile__user=user))
        for name, model in (
            ("preference_roles", m.PreferenceRole),
            ("preference_locations", m.PreferenceLocation),
            ("preference_contracts", m.PreferenceContract),
            ("preference_work_modes", m.PreferenceWorkMode),
        ):
            data[name] = rows(model.objects.filter(preference__profile__user=user))
    from jobboard.services.documents import read_document

    archive = tempfile.SpooledTemporaryFile(max_size=1024 * 1024)
    total = 0
    try:
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as output:
            with output.open("data.json", "w") as metadata:
                for chunk in DjangoJSONEncoder(ensure_ascii=False).iterencode(data):
                    encoded = chunk.encode("utf-8")
                    total += len(encoded)
                    if total > MAX_EXPORT_BYTES:
                        raise APIError(
                            "export_too_large",
                            "Account export exceeds 100 MiB.",
                            status=413,
                        )
                    metadata.write(encoded)
            for document in documents:
                content = read_document(document)
                total += len(content)
                if total > MAX_EXPORT_BYTES:
                    raise APIError(
                        "export_too_large",
                        "Account export exceeds 100 MiB.",
                        status=413,
                    )
                output.writestr(f"documents/{document.pk}.pdf", content)
        if archive.tell() > MAX_EXPORT_BYTES:
            raise APIError(
                "export_too_large", "Account export exceeds 100 MiB.", status=413
            )
        if not get_user_model().objects.filter(pk=user.pk, is_active=True).exists():
            raise APIError(
                "account_inactive", "Account is no longer active.", status=401
            )
        archive.seek(0)
        return archive
    except Exception:
        archive.close()
        raise


def _cancel_safe_runs(user, now):
    safe = m.AgentRun.objects.filter(user=user, phase__in=SAFE_PHASES).filter(
        Q(status__in=("queued", "needs_input"))
        | Q(status="running", lease_expires_at__lte=now)
    )
    safe.update(
        status="cancelled",
        phase="done",
        finished_at=now,
        worker_token=None,
        lease_expires_at=None,
        error_code="account_deleted",
    )


def request_deletion(user, password):
    with transaction.atomic():
        user = lock_user(user)
        if not isinstance(password, str) or not user.check_password(password):
            raise APIError("invalid_password", "The password is incorrect.", status=400)
        recruiter_offers = m.RecruiterJob.objects.filter(owner__user=user).values("offer_id")
        m.Offer.objects.filter(pk__in=recruiter_offers).update(status="hidden")
        m.OfferSource.objects.filter(offer_id__in=recruiter_offers).update(source_status="closed")
        user.is_active = False
        user.save(update_fields=["is_active"])
        now = timezone.now()
        m.SubmissionAuthorization.objects.filter(
            user=user, revoked_at__isnull=True
        ).update(revoked_at=now)
        _cancel_safe_runs(user, now)
        request, _ = m.DeletionRequest.objects.get_or_create(user=user)
        return request


def _ensure_quiescent(user):
    if m.Document.objects.filter(owner=user, status="pending").exists():
        raise APIError(
            "uploads_pending",
            "An upload must finish or be recovered before account deletion.",
            status=409,
        )
    _cancel_safe_runs(user, timezone.now())
    if m.AgentRun.objects.filter(
        user=user, status__in=("queued", "running", "needs_input", "uncertain")
    ).exists():
        raise APIError(
            "runs_pending",
            "A submission still needs to finish or be resolved.",
            status=409,
        )


def _delete_rows(user):
    # Explicit order also satisfies immediate composite ownership foreign keys.
    m.ApplicationEvent.objects.filter(application__user=user).delete()
    m.AgentRun.objects.filter(user=user).delete()
    m.SubmissionAuthorization.objects.filter(user=user).delete()
    m.RevisionDocument.objects.filter(user=user).delete()
    m.ApplicationRevision.objects.filter(user=user).delete()
    m.Application.objects.filter(user=user).delete()
    m.CandidateProfile.objects.filter(user=user).delete()
    m.Document.objects.filter(owner=user).update(derived_from=None)
    m.Document.objects.filter(owner=user).delete()
    m.SavedOffer.objects.filter(user=user).delete()
    m.OutboxMessage.objects.filter(owner=user).delete()
    user.delete()


def purge_account(request_id):
    """Return completed/pending/failed; safe to retry after any storage failure."""
    preliminary = m.DeletionRequest.objects.get(pk=request_id)
    if preliminary.status == "completed":
        return "completed"
    try:
        with transaction.atomic():
            user = (
                get_user_model()
                .objects.select_for_update()
                .filter(pk=preliminary.user_id)
                .first()
            )
            request = m.DeletionRequest.objects.select_for_update().get(pk=request_id)
            if request.status == "completed":
                return "completed"
            if user is None or user.is_active:
                raise APIError(
                    "invalid_deletion_state",
                    "Deletion requires an inactive account.",
                    status=409,
                )
            _ensure_quiescent(user)
            request.status = "running"
            request.last_error_code = None
            request.save(update_fields=["status", "last_error_code"])
            m.Document.objects.filter(owner=user).update(status="deleting")
            documents = list(m.Document.objects.filter(owner=user).order_by("pk"))
        from jobboard.services.documents import delete_document_blob

        for document in documents:
            delete_document_blob(document)
        with transaction.atomic():
            user = (
                get_user_model()
                .objects.select_for_update()
                .filter(pk=preliminary.user_id)
                .first()
            )
            request = m.DeletionRequest.objects.select_for_update().get(pk=request_id)
            if request.status == "completed":
                return "completed"
            if user is None or user.is_active:
                raise APIError(
                    "invalid_deletion_state",
                    "Deletion requires an inactive account.",
                    status=409,
                )
            _ensure_quiescent(user)
            _delete_rows(user)
            request.user = None
            request.status = "completed"
            request.completed_at = timezone.now()
            request.last_error_code = None
            request.save(
                update_fields=["user", "status", "completed_at", "last_error_code"]
            )
        return "completed"
    except Exception as exc:
        code = exc.code if isinstance(exc, APIError) else "purge_failed"
        # Do not retain exception strings, storage paths, or personal data in receipts.
        m.DeletionRequest.objects.filter(pk=request_id).exclude(
            status="completed"
        ).update(status="failed", last_error_code=code)
        return "pending" if code in {"runs_pending", "uploads_pending"} else "failed"


@transaction.atomic
def recover_stopped_uploads(document_ids):
    """Operator-only recovery after independently confirming writers have stopped.

    Age is an additional safeguard, never proof that a remote writer has stopped.
    Only exact IDs belonging to inactive accounts awaiting deletion are accepted.
    """
    ids = sorted(set(document_ids))
    if not ids or len(ids) > 100 or any(type(pk) is not int or pk <= 0 for pk in ids):
        raise APIError("invalid_recovery_ids", "Supply between 1 and 100 document IDs.")
    owner_ids = list(
        m.Document.objects.filter(pk__in=ids)
        .order_by("owner_id")
        .values_list("owner_id", flat=True)
        .distinct()
    )
    users = list(
        get_user_model()
        .objects.select_for_update()
        .filter(pk__in=owner_ids)
        .order_by("pk")
    )
    documents = list(
        m.Document.objects.select_for_update().filter(pk__in=ids).order_by("pk")
    )
    cutoff = timezone.now() - timedelta(hours=24)
    if len(documents) != len(ids) or any(user.is_active for user in users):
        raise APIError(
            "recovery_unavailable",
            "Recovery requires existing documents on inactive accounts.",
            status=409,
        )
    pending_owner_ids = set(
        m.DeletionRequest.objects.exclude(status="completed")
        .filter(user_id__in=owner_ids)
        .values_list("user_id", flat=True)
    )
    if any(
        d.status != "pending"
        or d.created_at > cutoff
        or d.owner_id not in pending_owner_ids
        for d in documents
    ):
        raise APIError(
            "recovery_unavailable",
            "Only uploads pending for 24 hours on accounts awaiting deletion can be recovered.",
            status=409,
        )
    return m.Document.objects.filter(pk__in=ids).update(status="deleting")
