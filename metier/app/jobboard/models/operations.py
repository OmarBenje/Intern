from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from .constraints import allowed, json_type


class OutboxMessage(models.Model):
    topic = models.CharField(max_length=80)
    dedupe_key = models.CharField(max_length=300, unique=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="outbox_messages",
    )
    payload = models.JSONField()
    available_at = models.DateTimeField(default=timezone.now)
    processed_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    lease_token = models.UUIDField(null=True, blank=True)
    lease_expires_at = models.DateTimeField(null=True, blank=True)
    last_error_code = models.CharField(max_length=80, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [json_type("payload", "object", "outbox_payload_object")]
        indexes = [
            models.Index(
                fields=["available_at", "id"],
                condition=Q(processed_at__isnull=True),
                name="outbox_pending_idx",
            )
        ]


class DeletionRequest(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="deletion_request",
    )
    status = models.CharField(
        max_length=16,
        default="requested",
        choices=[
            (v, v.title()) for v in ("requested", "running", "completed", "failed")
        ],
    )
    requested_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)
    last_error_code = models.CharField(max_length=80, null=True, blank=True)

    class Meta:
        constraints = [
            allowed(
                "status",
                ("requested", "running", "completed", "failed"),
                "deletion_status_valid",
            ),
            models.CheckConstraint(
                condition=Q(completed_at__isnull=True)
                | Q(completed_at__gte=F("requested_at")),
                name="deletion_dates_valid",
            ),
        ]


class RequestThrottle(models.Model):
    """Shared, hashed counters; no IP or account identifier retained in clear text."""

    key = models.CharField(max_length=64, unique=True)
    count = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField(db_index=True)
