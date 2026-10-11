from django.db import models
from django.utils import timezone


class AtsProbe(models.Model):
    candidate = models.OneToOneField(
        "SourceCandidate", on_delete=models.CASCADE, related_name="probe"
    )
    enabled = models.BooleanField(default=True)
    state = models.CharField(max_length=24, default="pending")
    attempts = models.PositiveIntegerField(default=0)
    next_attempt_at = models.DateTimeField(default=timezone.now, db_index=True)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    lease_token = models.UUIDField(null=True, blank=True)
    lease_expires_at = models.DateTimeField(null=True, blank=True)
    error_code = models.CharField(max_length=100, blank=True)
    result = models.JSONField(default=dict)
