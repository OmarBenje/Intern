"""Additive catalogue engine projections and private discovery preferences."""

from django.conf import settings
from django.db import models
from django.utils import timezone

from .constraints import allowed, json_type


class BoardSchedule(models.Model):
    board = models.OneToOneField(
        "SourceBoard", on_delete=models.CASCADE, related_name="engine_schedule"
    )
    interval_minutes = models.PositiveIntegerField(default=120)
    next_run_at = models.DateTimeField(default=timezone.now, db_index=True)
    failure_count = models.PositiveIntegerField(default=0)
    lease_token = models.UUIDField(null=True, blank=True)
    lease_expires_at = models.DateTimeField(null=True, blank=True)
    last_error_code = models.CharField(max_length=80, blank=True, default="")
    missing_confirmation_hours = models.PositiveIntegerField(default=6)
    paused = models.BooleanField(default=False)
    quarantine_hash = models.CharField(max_length=64, blank=True, default="")
    quarantine_since = models.DateTimeField(null=True, blank=True)
    collection_checkpoint = models.JSONField(default=dict)

    class Meta:
        constraints = [  # noqa: RUF012 - Django Meta declarative configuration
            models.CheckConstraint(
                condition=models.Q(interval_minutes__gte=1),
                name="engine_interval_positive",
            )
        ]


class SourceRevision(models.Model):
    source = models.ForeignKey(
        "OfferSource", on_delete=models.CASCADE, related_name="revisions"
    )
    raw_hash = models.CharField(max_length=64)
    semantic_hash = models.CharField(max_length=64)
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        constraints = [  # noqa: RUF012 - Django Meta declarative configuration
            models.UniqueConstraint(
                fields=["source", "raw_hash"], name="engine_revision_unique"
            ),
            json_type("payload", "object", "engine_revision_object"),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("Source revisions are immutable")
        super().save(*args, **kwargs)


class SourceObservation(models.Model):
    source = models.OneToOneField(
        "OfferSource", on_delete=models.CASCADE, related_name="observation"
    )
    missing_since = models.DateTimeField(null=True, blank=True)
    missing_count = models.PositiveIntegerField(default=0)


class OfferEnrichment(models.Model):
    offer = models.OneToOneField(
        "Offer", on_delete=models.CASCADE, related_name="enrichment"
    )
    content_version = models.PositiveIntegerField(default=1)
    event_at = models.DateTimeField(default=timezone.now, db_index=True)
    semantic_hash = models.CharField(max_length=64, blank=True)
    domain = models.SlugField(max_length=80, blank=True, db_index=True)
    facts = models.JSONField(default=dict)
    content = models.JSONField(default=dict)
    classification = models.CharField(max_length=24, default="uncertain", db_index=True)
    country_codes = models.JSONField(default=list)
    europe_status = models.CharField(max_length=20, default="unknown", db_index=True)
    extractor_version = models.CharField(max_length=80, blank=True)

    class Meta:
        constraints = [  # noqa: RUF012 - Django Meta declarative configuration
            allowed(
                "classification",
                ("confirmed", "uncertain", "not_internship"),
                "engine_classification_valid",
            ),
            allowed(
                "europe_status",
                ("in_scope", "unknown", "out_of_scope"),
                "engine_europe_valid",
            ),
            json_type("facts", "object", "engine_facts_object"),
            json_type("content", "object", "engine_content_object"),
            json_type("country_codes", "array", "engine_countries_array"),
        ]


class SavedSearch(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="saved_searches",
    )
    name = models.CharField(max_length=160)
    criteria = models.JSONField(default=dict)
    frequency = models.CharField(
        max_length=12, default="off", choices=[("off", "Off"), ("daily", "Daily")]
    )
    timezone = models.CharField(max_length=80, default="Europe/Paris")
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_evaluated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [  # noqa: RUF012 - Django Meta declarative configuration
            allowed("frequency", ("off", "daily"), "engine_search_frequency"),
            json_type("criteria", "object", "engine_search_criteria"),
        ]


class OfferFeedback(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    offer = models.ForeignKey("Offer", on_delete=models.CASCADE)
    reason = models.CharField(max_length=40)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [  # noqa: RUF012 - Django Meta declarative configuration
            models.UniqueConstraint(
                fields=["user", "offer"], name="engine_feedback_unique"
            )
        ]


class CompanyPreference(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    company = models.ForeignKey("Company", on_delete=models.CASCADE)
    excluded = models.BooleanField(default=True)

    class Meta:
        constraints = [  # noqa: RUF012 - Django Meta declarative configuration
            models.UniqueConstraint(
                fields=["user", "company"], name="engine_company_pref_unique"
            )
        ]


class OfferReport(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    offer = models.ForeignKey("Offer", on_delete=models.CASCADE)
    reason = models.CharField(max_length=40)
    details = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, default="pending")


class AlertEvent(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    offer = models.ForeignKey("Offer", on_delete=models.CASCADE)
    event_key = models.CharField(max_length=200)
    channel = models.CharField(max_length=12, default="in_app")
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [  # noqa: RUF012 - Django Meta declarative configuration
            models.UniqueConstraint(
                fields=["user", "event_key"], name="engine_alert_unique"
            ),
            allowed("channel", ("in_app",), "engine_alert_channel"),
        ]


class ExternalOpportunity(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    url = models.URLField(max_length=2048)
    title = models.CharField(max_length=300, blank=True)
    company_name = models.CharField(max_length=240, blank=True)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=16, default="pending")
    error_code = models.CharField(max_length=80, blank=True)
    offer = models.ForeignKey("Offer", on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class SourceCandidate(models.Model):
    url = models.URLField(max_length=2048, unique=True)
    provider = models.CharField(max_length=40)
    board_key = models.CharField(max_length=240)
    instance = models.CharField(max_length=40, default="global")
    status = models.CharField(max_length=40, default="candidate")
    company_name = models.CharField(max_length=240)
    discovered_at = models.DateTimeField(default=timezone.now)
    board = models.ForeignKey(
        "SourceBoard", on_delete=models.SET_NULL, null=True, blank=True
    )


class OfferMergeDecision(models.Model):
    canonical_offer = models.ForeignKey(
        "Offer", on_delete=models.PROTECT, related_name="merge_targets"
    )
    duplicate_offer = models.ForeignKey(
        "Offer", on_delete=models.PROTECT, related_name="merge_decisions"
    )
    status = models.CharField(max_length=16, default="candidate")
    evidence = models.JSONField(default=dict)
    created_at = models.DateTimeField(default=timezone.now)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [  # noqa: RUF012 - Django Meta declarative configuration
            models.UniqueConstraint(
                fields=["canonical_offer", "duplicate_offer"],
                name="engine_merge_pair_unique",
            ),
            allowed(
                "status",
                ("candidate", "merged", "rejected", "reversed"),
                "engine_merge_status_valid",
            ),
        ]


class SourceDiscoverySeed(models.Model):
    url = models.URLField(max_length=2048, unique=True)
    allowed_host = models.CharField(max_length=253)
    company_name = models.CharField(max_length=240)
    enabled = models.BooleanField(default=True)
    next_run_at = models.DateTimeField(default=timezone.now, db_index=True)
    last_success_at = models.DateTimeField(null=True, blank=True)
    failure_count = models.PositiveIntegerField(default=0)
    last_error_code = models.CharField(max_length=80, blank=True)
    lease_token = models.UUIDField(null=True, blank=True)
    lease_expires_at = models.DateTimeField(null=True, blank=True)


class DiscoveryQuery(models.Model):
    provider = models.CharField(max_length=40)
    country = models.CharField(max_length=2, blank=True)
    language = models.CharField(max_length=8)
    domain = models.CharField(max_length=80, default="all")
    term = models.CharField(max_length=240, blank=True)
    enabled = models.BooleanField(default=True)
    auto_activate = models.BooleanField(default=False)
    cursor = models.CharField(max_length=80, blank=True)
    next_run_at = models.DateTimeField(default=timezone.now, db_index=True)
    last_success_at = models.DateTimeField(null=True, blank=True)
    last_error_code = models.CharField(max_length=80, blank=True)
    failure_count = models.PositiveIntegerField(default=0)
    result_count = models.PositiveIntegerField(default=0)
    total_available = models.PositiveIntegerField(null=True, blank=True)
    truncated = models.BooleanField(default=False)
    lease_token = models.UUIDField(null=True, blank=True)
    lease_expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "country", "language", "domain", "term"],
                name="engine_discovery_query_unique",
            )
        ]


class DiscoveryResult(models.Model):
    query = models.ForeignKey(
        DiscoveryQuery, on_delete=models.CASCADE, related_name="results"
    )
    external_id = models.CharField(max_length=300)
    source_url = models.URLField(max_length=2048, blank=True)
    company_name = models.CharField(max_length=240, blank=True)
    payload = models.JSONField(default=dict)
    attribution = models.URLField(max_length=2048)
    status = models.CharField(max_length=40, default="pending")
    error_code = models.CharField(max_length=80, blank=True)
    candidate = models.ForeignKey(
        SourceCandidate, null=True, blank=True, on_delete=models.SET_NULL
    )
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    first_seen_at = models.DateTimeField(default=timezone.now)
    last_seen_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["query", "external_id"], name="engine_discovery_result_unique"
            )
        ]
