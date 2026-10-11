from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVector, SearchVectorField
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from .choices import ContractType, OfferStatus, SalaryPeriod, WorkMode
from .constraints import allowed, json_type


class Skill(models.Model):
    name = models.CharField(max_length=160)
    slug = models.SlugField(max_length=140, unique=True)

    def __str__(self):
        return self.name


class Role(models.Model):
    name = models.CharField(max_length=160)
    slug = models.SlugField(max_length=140, unique=True)

    def __str__(self):
        return self.name


class Company(models.Model):
    name = models.CharField(max_length=240)
    website_url = models.URLField(max_length=2048, null=True, blank=True)
    domain = models.CharField(max_length=253, null=True, blank=True, db_index=True)
    description = models.TextField(blank=True, default="")
    logo_object_key = models.TextField(null=True, blank=True)
    logo_attempts = models.PositiveIntegerField(default=0)
    logo_next_attempt_at = models.DateTimeField(
        default=timezone.now, null=True, blank=True, db_index=True
    )
    logo_last_error = models.CharField(max_length=240, blank=True, default="")
    logo_source_url = models.URLField(max_length=2048, blank=True, default="")
    logo_source_kind = models.CharField(max_length=32, blank=True, default="")
    logo_fetched_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class Location(models.Model):
    # Keep the existing Python name; it is the blueprint's display label.
    name = models.CharField(max_length=240)
    canonical_key = models.CharField(max_length=240, unique=True)
    country_code = models.CharField(max_length=2, null=True, blank=True)
    region = models.CharField(max_length=160, null=True, blank=True)
    city = models.CharField(max_length=160, null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(country_code__isnull=True)
                | Q(country_code__regex=r"^[A-Z]{2}$"),
                name="location_country_format",
            )
        ]

    def __str__(self):
        return self.name


class Offer(models.Model):
    ContractType = ContractType
    WorkMode = WorkMode
    Status = OfferStatus

    job_subdomain = models.ForeignKey(
        "JobSubdomain", on_delete=models.PROTECT, null=True, blank=True,
        related_name="offers",
    )
    secondary_subdomains = models.ManyToManyField(
        "JobSubdomain", blank=True, related_name="secondary_offers",
    )
    taxonomy_status = models.CharField(
        max_length=20, default="unclassified",
        choices=[(v, v) for v in ("classified", "broad", "needs_review", "unclassified")],
    )
    taxonomy_version = models.CharField(max_length=80, blank=True)
    taxonomy_input_hash = models.CharField(max_length=64, blank=True)
    taxonomy_evidence = models.JSONField(default=dict)
    taxonomy_manual = models.BooleanField(default=False)

    title = models.CharField(max_length=300)
    company = models.ForeignKey(
        Company, on_delete=models.PROTECT, related_name="offers"
    )
    description = models.TextField()
    # Kept during the transition, never used as the authoritative submission target.
    application_url = models.URLField(
        max_length=2048, blank=True, help_text="Legacy URL; use OfferSource.apply_url."
    )
    locations = models.ManyToManyField(
        Location, through="OfferLocation", related_name="offers", blank=True
    )
    role = models.ForeignKey(
        Role, on_delete=models.PROTECT, related_name="offers", null=True, blank=True
    )
    skills = models.ManyToManyField(
        Skill, through="OfferSkill", related_name="offers", blank=True
    )
    contract_type = models.CharField(
        max_length=24, choices=ContractType, default=ContractType.UNKNOWN
    )
    employment_schedule = models.CharField(
        max_length=12,
        choices=[
            ("full_time", "Full time"),
            ("part_time", "Part time"),
            ("unknown", "Unknown"),
        ],
        default="unknown",
    )
    work_mode = models.CharField(
        max_length=12, choices=WorkMode, default=WorkMode.UNKNOWN
    )
    seniority = models.CharField(
        max_length=16,
        choices=[
            (v, v.title())
            for v in ("entry", "mid", "senior", "lead", "executive", "unknown")
        ],
        default="unknown",
    )
    remote_scope = models.TextField(null=True, blank=True)
    language_code = models.CharField(max_length=16, null=True, blank=True)
    status = models.CharField(
        max_length=12, choices=OfferStatus, default=OfferStatus.OPEN
    )
    published_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    search_vector = models.GeneratedField(
        expression=SearchVector("title", config="simple", weight="A")
        + SearchVector("description", config="simple", weight="B"),
        output_field=SearchVectorField(),
        db_persist=True,
    )
    # Database triggers maintain these for every write path, including imports
    # and company renames. They are never writable through the candidate API.
    search_document = SearchVectorField(null=True, editable=False)
    search_title = models.TextField(default="", editable=False)

    class Meta:
        constraints = [
            allowed("taxonomy_status", ("classified", "broad", "needs_review", "unclassified"), "offer_taxonomy_status_valid"),
            models.CheckConstraint(
                condition=Q(taxonomy_status__in=["classified", "broad"], job_subdomain__isnull=False)
                | Q(taxonomy_status__in=["needs_review", "unclassified"], job_subdomain__isnull=True)
                | Q(taxonomy_status="needs_review", taxonomy_manual=True),
                name="offer_taxonomy_assignment_valid",
            ),
            allowed("contract_type", ContractType.values, "offer_contract_valid"),
            allowed("work_mode", WorkMode.values, "offer_work_mode_valid"),
            allowed("status", OfferStatus.values, "offer_status_valid"),
            allowed(
                "employment_schedule",
                ("full_time", "part_time", "unknown"),
                "offer_schedule_valid",
            ),
            allowed(
                "seniority",
                ("entry", "mid", "senior", "lead", "executive", "unknown"),
                "offer_seniority_valid",
            ),
            models.CheckConstraint(
                condition=Q(expires_at__isnull=True)
                | Q(published_at__isnull=True)
                | Q(expires_at__gte=F("published_at")),
                name="offer_dates_valid",
            ),
        ]
        indexes = [
            models.Index(
                F("published_at").desc(nulls_last=True),
                F("id").desc(),
                condition=Q(status="open"),
                name="offer_feed_idx",
            ),
            models.Index(
                fields=["contract_type", "work_mode", "-published_at"],
                condition=Q(status="open"),
                name="offer_filters_idx",
            ),
            GinIndex(fields=["search_vector"], name="offer_search_idx"),
            GinIndex(fields=["search_document"], name="offer_document_idx"),
            GinIndex(
                fields=["search_title"],
                opclasses=["gin_trgm_ops"],
                name="offer_title_trgm_idx",
            ),
        ]

    def __str__(self):
        return self.title


class OfferLocation(models.Model):
    offer = models.ForeignKey(Offer, on_delete=models.CASCADE)
    location = models.ForeignKey(Location, on_delete=models.PROTECT)

    class Meta:
        # Adopt the existing M2M table, including its IDs and links.
        db_table = "jobboard_offer_locations"
        unique_together = [("offer", "location")]
        indexes = [
            models.Index(
                fields=["location", "offer"], name="offer_location_reverse_idx"
            )
        ]


class OfferSkill(models.Model):
    offer = models.ForeignKey(Offer, on_delete=models.CASCADE)
    skill = models.ForeignKey(Skill, on_delete=models.PROTECT)
    importance = models.CharField(
        max_length=12,
        choices=[(v, v.title()) for v in ("required", "preferred", "unspecified")],
        default="unspecified",
    )

    class Meta:
        db_table = "jobboard_offer_skills"
        unique_together = [("offer", "skill")]
        constraints = [
            allowed(
                "importance",
                ("required", "preferred", "unspecified"),
                "offer_skill_importance_valid",
            ),
        ]
        indexes = [
            models.Index(fields=["skill", "offer"], name="offer_skill_reverse_idx")
        ]


class SourceBoard(models.Model):
    provider = models.CharField(max_length=40)
    instance = models.CharField(max_length=40, default="global")
    board_key = models.CharField(max_length=240)
    company = models.ForeignKey(
        Company,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="source_boards",
    )
    base_url = models.URLField(max_length=2048)
    enabled = models.BooleanField(default=True)
    submission_mode = models.CharField(
        max_length=16,
        default="unsupported",
        choices=[
            (v, v.replace("_", " ").title())
            for v in ("browser", "partner_api", "unsupported")
        ],
    )
    adapter_version = models.CharField(max_length=80, null=True, blank=True)
    last_success_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "instance", "board_key"],
                name="source_board_identity_unique",
            ),
            allowed(
                "submission_mode",
                ("browser", "partner_api", "unsupported"),
                "board_submission_mode_valid",
            ),
        ]

    def __str__(self):
        return f"{self.provider}/{self.instance}/{self.board_key}"


class ImportRun(models.Model):
    board = models.ForeignKey(
        SourceBoard, on_delete=models.PROTECT, related_name="imports"
    )
    status = models.CharField(
        max_length=12,
        choices=[(v, v.title()) for v in ("running", "succeeded", "failed")],
        default="running",
    )
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)
    diagnostics = models.JSONField(default=list, blank=True)
    is_full_snapshot = models.BooleanField(default=False)
    seen_count = models.PositiveIntegerField(default=0)
    error_code = models.CharField(max_length=80, null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["id", "board"], name="import_run_board_identity"
            ),
            allowed(
                "status", ("running", "succeeded", "failed"), "import_run_status_valid"
            ),
            models.CheckConstraint(
                condition=Q(finished_at__isnull=True)
                | Q(finished_at__gte=F("started_at")),
                name="import_run_dates_valid",
            ),
        ]
        indexes = [
            models.Index(fields=["board", "-started_at"], name="import_run_board_idx")
        ]


class OfferSource(models.Model):
    offer = models.ForeignKey(Offer, on_delete=models.PROTECT, related_name="sources")
    board = models.ForeignKey(
        SourceBoard, on_delete=models.PROTECT, related_name="sources"
    )
    external_id = models.CharField(max_length=300)
    external_requisition_id = models.CharField(max_length=300, null=True, blank=True)
    origin_url = models.URLField(max_length=2048)
    apply_url = models.URLField(max_length=2048)
    source_status = models.CharField(
        max_length=12,
        default="active",
        choices=[(v, v.title()) for v in ("active", "missing", "closed", "unknown")],
    )
    first_seen_at = models.DateTimeField(default=timezone.now)
    last_seen_at = models.DateTimeField(default=timezone.now)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    last_seen_run = models.ForeignKey(
        ImportRun,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="seen_sources",
    )
    content_hash = models.CharField(max_length=64)
    raw_payload = models.JSONField(default=dict, blank=True)
    raw_expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["board", "external_id"], name="offer_source_external_unique"
            ),
            models.UniqueConstraint(
                fields=["id", "offer"], name="offer_source_offer_identity"
            ),
            allowed(
                "source_status",
                ("active", "missing", "closed", "unknown"),
                "offer_source_status_valid",
            ),
            models.CheckConstraint(
                condition=Q(content_hash__regex=r"^[0-9a-f]{64}$"),
                name="source_hash_valid",
            ),
            models.CheckConstraint(
                condition=Q(last_seen_at__gte=F("first_seen_at")),
                name="source_seen_dates_valid",
            ),
            json_type("raw_payload", "object", "source_payload_object"),
        ]


class CompensationBand(models.Model):
    offer = models.ForeignKey(
        Offer, on_delete=models.CASCADE, related_name="compensation_bands"
    )
    source = models.ForeignKey(
        OfferSource, on_delete=models.PROTECT, related_name="compensation_bands"
    )
    location = models.ForeignKey(
        Location, on_delete=models.PROTECT, null=True, blank=True
    )
    label = models.CharField(max_length=240, null=True, blank=True)
    minimum = models.DecimalField(
        max_digits=16, decimal_places=2, null=True, blank=True
    )
    maximum = models.DecimalField(
        max_digits=16, decimal_places=2, null=True, blank=True
    )
    currency = models.CharField(max_length=3)
    period = models.CharField(max_length=10, choices=SalaryPeriod)
    gross_net = models.CharField(
        max_length=10,
        default="unknown",
        choices=[(v, v.title()) for v in ("gross", "net", "unknown")],
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(minimum__isnull=False) | Q(maximum__isnull=False),
                name="salary_has_bound",
            ),
            models.CheckConstraint(
                condition=Q(minimum__isnull=True) | Q(minimum__gte=0),
                name="salary_min_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(maximum__isnull=True) | Q(maximum__gte=0),
                name="salary_max_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(minimum__isnull=True)
                | Q(maximum__isnull=True)
                | Q(maximum__gte=F("minimum")),
                name="salary_bounds_ordered",
            ),
            models.CheckConstraint(
                condition=Q(currency__regex=r"^[A-Z]{3}$"), name="salary_currency_valid"
            ),
            allowed("period", SalaryPeriod.values, "salary_period_valid"),
            allowed("gross_net", ("gross", "net", "unknown"), "salary_gross_net_valid"),
        ]


class SavedOffer(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="saved_offers"
    )
    offer = models.ForeignKey(Offer, on_delete=models.CASCADE, related_name="saved_by")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "offer"], name="saved_offer_unique")
        ]
        indexes = [
            models.Index(
                fields=["user", "-created_at", "-id"], name="saved_offer_feed_idx"
            )
        ]
