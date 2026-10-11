"""Recruiter-owned workspaces; catalogue companies never grant account access."""

from django.conf import settings
from django.db import models


class RecruiterProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="recruiter_profile",
    )
    full_name = models.CharField(max_length=240)
    company = models.ForeignKey(
        "Company",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="recruiter_profiles",
    )
    company_name = models.CharField(max_length=240, blank=True)
    siren = models.CharField(max_length=9, blank=True)
    website_url = models.URLField(max_length=2048, blank=True)
    linkedin_url = models.URLField(max_length=2048, blank=True)
    verification_status = models.CharField(
        max_length=16,
        default="unverified",
        choices=[(x, x) for x in ("unverified", "pending", "verified", "rejected")],
    )
    email_verified = models.BooleanField(default=False)
    email_code_hash = models.CharField(max_length=128, blank=True)
    email_code_expires_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)


class RecruiterJob(models.Model):
    owner = models.ForeignKey(
        RecruiterProfile, on_delete=models.CASCADE, related_name="jobs"
    )
    offer = models.OneToOneField(
        "Offer",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="recruiter_job",
    )
    title = models.CharField(max_length=300)
    department = models.CharField(max_length=160, blank=True)
    contract_type = models.CharField(
        max_length=24,
        default="internship",
        choices=[(x, x) for x in ("internship", "apprenticeship", "employment")],
    )
    location = models.CharField(max_length=240, blank=True)
    country_code = models.CharField(max_length=2, default="FR")
    work_mode = models.CharField(
        max_length=12,
        default="onsite",
        choices=[(x, x) for x in ("onsite", "hybrid", "remote")],
    )
    salary = models.CharField(max_length=160, blank=True)
    description = models.TextField(blank=True)
    skills = models.TextField(blank=True)
    education = models.CharField(max_length=160, blank=True)
    languages = models.CharField(max_length=240, blank=True)
    status = models.CharField(
        max_length=16,
        default="draft",
        choices=[(x, x) for x in ("draft", "active", "paused", "archived")],
    )
    origin = models.CharField(max_length=40, default="direct")
    views = models.PositiveIntegerField(default=0)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["id", "offer"], name="recruiter_job_offer_identity"
            ),
        ]


class RecruiterApplicant(models.Model):
    application = models.OneToOneField(
        "Application", on_delete=models.CASCADE, related_name="recruiter_applicant"
    )
    job = models.ForeignKey(
        RecruiterJob, on_delete=models.CASCADE, related_name="applicants"
    )
    # These mirrors let SQL check the application, job and CV together.
    candidate = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    offer = models.ForeignKey("Offer", on_delete=models.PROTECT)
    resume_kind = models.CharField(max_length=16, default="resume", editable=False)
    # Immutable application snapshot: later private profile edits are never shared.
    profile_snapshot = models.JSONField(default=dict)
    resume = models.ForeignKey(
        "Document", on_delete=models.PROTECT, null=True, blank=True
    )
    stage = models.CharField(
        max_length=16,
        default="new",
        choices=[
            (x, x)
            for x in (
                "new",
                "recommended",
                "review",
                "interview",
                "accepted",
                "rejected",
            )
        ],
    )
    match_score = models.PositiveSmallIntegerField(null=True, blank=True)
    ai_summary = models.TextField(blank=True)
    rejection_reason = models.TextField(blank=True)
    interview_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(resume_kind="resume"),
                name="recruiter_resume_kind_valid",
            ),
        ]

    def save(self, *args, **kwargs):
        self.candidate_id = self.application.user_id
        self.offer_id = self.application.offer_id
        if kwargs.get("update_fields") is not None:
            kwargs["update_fields"] = set(kwargs["update_fields"]) | {
                "candidate",
                "offer",
            }
        return super().save(*args, **kwargs)


class RecruiterIntegration(models.Model):
    owner = models.ForeignKey(
        RecruiterProfile, on_delete=models.CASCADE, related_name="integrations"
    )
    provider = models.CharField(
        max_length=32,
        choices=[
            (x, x)
            for x in (
                "greenhouse",
                "lever",
                "workday",
                "ashby",
                "smartrecruiters",
                "wttj",
                "feed",
            )
        ],
    )
    url = models.URLField(max_length=2048)
    status = models.CharField(max_length=24, default="pending", editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "provider"], name="recruiter_integration_unique"
            )
        ]
