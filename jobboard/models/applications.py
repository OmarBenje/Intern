import uuid

from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from .choices import ACTIVE_RUN_STATUSES, ApplicationStatus, RunStatus
from .constraints import allowed, json_type


class Application(models.Model):
    Status = ApplicationStatus
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="applications"
    )
    offer = models.ForeignKey(
        "Offer", on_delete=models.PROTECT, related_name="applications"
    )
    source = models.ForeignKey(
        "OfferSource", on_delete=models.PROTECT, related_name="applications"
    )
    status = models.CharField(
        max_length=16, choices=ApplicationStatus, default=ApplicationStatus.DRAFT
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    external_reference = models.CharField(max_length=300, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "offer"], name="application_user_offer_unique"
            ),
            models.UniqueConstraint(
                fields=["id", "user"], name="application_user_identity"
            ),
            models.UniqueConstraint(
                fields=["id", "user", "offer"], name="application_owner_offer_identity"
            ),
            allowed("status", ApplicationStatus.values, "application_status_valid"),
        ]
        indexes = [
            models.Index(
                fields=["user", "status", "-updated_at", "-id"],
                name="application_tracker_idx",
            )
        ]

    def __str__(self):
        return f"Application #{self.pk}"


class ApplicationRevision(models.Model):
    application = models.ForeignKey(
        Application, on_delete=models.PROTECT, related_name="revisions"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    revision_no = models.PositiveIntegerField()
    schema_version = models.PositiveIntegerField(default=1)
    profile_snapshot = models.JSONField()
    offer_snapshot = models.JSONField()
    form_snapshot = models.JSONField()
    answers = models.JSONField(default=list, blank=True)
    generator_version = models.CharField(max_length=120, null=True, blank=True)
    prompt_version = models.CharField(max_length=120, null=True, blank=True)
    content_hash = models.CharField(max_length=64, null=True, blank=True)
    sealed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    documents = models.ManyToManyField(
        "Document", through="RevisionDocument", related_name="revisions"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["application", "revision_no"], name="revision_number_unique"
            ),
            models.UniqueConstraint(
                fields=["id", "user"], name="revision_user_identity"
            ),
            models.UniqueConstraint(
                fields=["id", "application", "user"],
                name="revision_application_identity",
            ),
            models.CheckConstraint(
                condition=Q(revision_no__gt=0), name="revision_number_positive"
            ),
            models.CheckConstraint(
                condition=Q(schema_version__gt=0), name="revision_schema_positive"
            ),
            models.CheckConstraint(
                condition=Q(content_hash__isnull=True)
                | Q(content_hash__regex=r"^[0-9a-f]{64}$"),
                name="revision_hash_valid",
            ),
            models.CheckConstraint(
                condition=Q(sealed_at__isnull=True) | Q(content_hash__isnull=False),
                name="sealed_revision_has_hash",
            ),
            json_type("profile_snapshot", "object", "revision_profile_object"),
            json_type("offer_snapshot", "object", "revision_offer_object"),
            json_type("form_snapshot", "object", "revision_form_object"),
            json_type("answers", "array", "revision_answers_array"),
        ]


class RevisionDocument(models.Model):
    revision = models.ForeignKey(
        ApplicationRevision, on_delete=models.CASCADE, related_name="document_links"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    document = models.ForeignKey(
        "Document", on_delete=models.PROTECT, related_name="revision_links"
    )
    purpose = models.CharField(
        max_length=16, choices=[("resume", "Resume"), ("cover_letter", "Cover letter")]
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["revision", "purpose"], name="revision_document_purpose_unique"
            ),
            allowed(
                "purpose", ("resume", "cover_letter"), "revision_document_purpose_valid"
            ),
        ]


class SubmissionAuthorization(models.Model):
    revision = models.ForeignKey(
        ApplicationRevision, on_delete=models.PROTECT, related_name="authorizations"
    )
    application = models.ForeignKey(
        Application, on_delete=models.PROTECT, related_name="authorizations"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    approved_hash = models.CharField(max_length=64)
    mode = models.CharField(max_length=16, default="per_application", editable=False)
    granted_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["id", "revision", "application", "user"],
                name="authorization_revision_identity",
            ),
            models.UniqueConstraint(
                fields=["revision"],
                condition=Q(revoked_at__isnull=True),
                name="one_unrevoked_authorization",
            ),
            models.CheckConstraint(
                condition=Q(approved_hash__regex=r"^[0-9a-f]{64}$"),
                name="authorization_hash_valid",
            ),
            models.CheckConstraint(
                condition=Q(mode="per_application"), name="authorization_mode_valid"
            ),
            models.CheckConstraint(
                condition=Q(expires_at__gt=F("granted_at")),
                name="authorization_expiration_valid",
            ),
            models.CheckConstraint(
                condition=Q(revoked_at__isnull=True)
                | Q(revoked_at__gte=F("granted_at")),
                name="authorization_revocation_valid",
            ),
        ]


class AgentRun(models.Model):
    Status = RunStatus
    application = models.ForeignKey(
        Application, on_delete=models.PROTECT, related_name="runs"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    revision = models.ForeignKey(
        ApplicationRevision, on_delete=models.PROTECT, related_name="runs"
    )
    authorization = models.ForeignKey(
        SubmissionAuthorization,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="runs",
    )
    purpose = models.CharField(
        max_length=12, choices=[("prepare", "Prepare"), ("submit", "Submit")]
    )
    status = models.CharField(
        max_length=16, choices=RunStatus, default=RunStatus.QUEUED
    )
    phase = models.CharField(
        max_length=16,
        default="preparing",
        choices=[
            (v, v.replace("_", " ").title())
            for v in (
                "preparing",
                "filling",
                "awaiting_user",
                "submitting",
                "verifying",
                "done",
            )
        ],
    )
    idempotency_key = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    worker_token = models.UUIDField(null=True, blank=True)
    lease_expires_at = models.DateTimeField(null=True, blank=True)
    heartbeat_at = models.DateTimeField(null=True, blank=True)
    attempt_no = models.PositiveIntegerField()
    adapter_version = models.CharField(max_length=120, null=True, blank=True)
    error_code = models.CharField(max_length=80, null=True, blank=True)
    evidence_document = models.ForeignKey(
        "Document",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="evidence_for_runs",
    )
    external_receipt = models.CharField(max_length=300, null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["application", "attempt_no"], name="run_attempt_unique"
            ),
            models.UniqueConstraint(
                fields=["id", "application"], name="run_application_identity"
            ),
            models.UniqueConstraint(
                fields=["application"],
                condition=Q(status__in=ACTIVE_RUN_STATUSES),
                name="one_active_run",
            ),
            allowed("purpose", ("prepare", "submit"), "run_purpose_valid"),
            allowed("status", RunStatus.values, "run_status_valid"),
            allowed(
                "phase",
                (
                    "preparing",
                    "filling",
                    "awaiting_user",
                    "submitting",
                    "verifying",
                    "done",
                ),
                "run_phase_valid",
            ),
            models.CheckConstraint(
                condition=Q(attempt_no__gt=0), name="run_attempt_positive"
            ),
            models.CheckConstraint(
                condition=~Q(purpose="submit") | Q(authorization__isnull=False),
                name="submit_requires_authorization",
            ),
            models.CheckConstraint(
                condition=Q(finished_at__isnull=True)
                | Q(started_at__isnull=True)
                | Q(finished_at__gte=F("started_at")),
                name="run_dates_valid",
            ),
        ]
        indexes = [
            models.Index(
                fields=["created_at", "id"],
                condition=Q(status="queued"),
                name="agent_queue_idx",
            )
        ]


class ApplicationEvent(models.Model):
    application = models.ForeignKey(
        Application, on_delete=models.PROTECT, related_name="events"
    )
    run = models.ForeignKey(
        AgentRun, on_delete=models.PROTECT, null=True, blank=True, related_name="events"
    )
    kind = models.CharField(max_length=80)
    origin = models.CharField(
        max_length=16,
        choices=[(v, v.title()) for v in ("user", "agent", "system", "provider")],
    )
    status_after = models.CharField(
        max_length=16, choices=ApplicationStatus, null=True, blank=True
    )
    happened_at = models.DateTimeField()
    recorded_at = models.DateTimeField(default=timezone.now, editable=False)
    dedupe_key = models.CharField(max_length=300, null=True, blank=True)
    payload = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["application", "origin", "dedupe_key"],
                name="application_event_dedupe",
            ),
            allowed(
                "origin",
                ("user", "agent", "system", "provider"),
                "application_event_origin_valid",
            ),
            allowed(
                "status_after", ApplicationStatus.values, "event_status_after_valid"
            ),
            json_type("payload", "object", "event_payload_object"),
        ]
        indexes = [
            models.Index(
                fields=["application", "happened_at", "id"],
                name="application_events_idx",
            )
        ]


class Interview(models.Model):
    application = models.ForeignKey(
        Application, on_delete=models.CASCADE, related_name="interviews"
    )
    title = models.CharField(max_length=240)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField(null=True, blank=True)
    display_timezone = models.CharField(max_length=80, default="UTC")
    meeting_url = models.URLField(max_length=2048, null=True, blank=True)
    location_text = models.TextField(null=True, blank=True)
    status = models.CharField(
        max_length=12,
        default="scheduled",
        choices=[(v, v.title()) for v in ("scheduled", "completed", "cancelled")],
    )
    notes = models.TextField(blank=True, default="")

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(ends_at__isnull=True) | Q(ends_at__gte=F("starts_at")),
                name="interview_dates_valid",
            ),
            allowed(
                "status",
                ("scheduled", "completed", "cancelled"),
                "interview_status_valid",
            ),
        ]
        indexes = [
            models.Index(
                fields=["application", "starts_at"], name="interview_application_idx"
            )
        ]


class ApplicationTask(models.Model):
    application = models.ForeignKey(
        Application, on_delete=models.CASCADE, related_name="tasks"
    )
    title = models.CharField(max_length=240)
    due_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["application", "due_at"],
                condition=Q(completed_at__isnull=True),
                name="application_task_due_idx",
            )
        ]
