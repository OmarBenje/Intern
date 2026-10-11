from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from .choices import ContractType, SalaryPeriod, WorkMode
from .constraints import allowed


class CandidateProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="candidate_profile",
    )
    full_name = models.CharField(max_length=240)
    first_name = models.CharField(max_length=160, null=True, blank=True)
    last_name = models.CharField(max_length=160, null=True, blank=True)
    phone = models.CharField(max_length=40, blank=True)
    headline = models.CharField(max_length=300, null=True, blank=True)
    # Preserve the user's existing field; corresponds to summary in the blueprint.
    presentation = models.TextField(blank=True, default="")
    location_text = models.CharField(max_length=240, blank=True)
    location = models.ForeignKey(
        "Location", on_delete=models.PROTECT, null=True, blank=True
    )
    street_address = models.CharField(max_length=240, blank=True)
    city = models.CharField(max_length=160, blank=True)
    postal_code = models.CharField(max_length=32, blank=True)
    district = models.CharField(max_length=160, blank=True)
    region = models.CharField(max_length=160, blank=True)
    country_code = models.CharField(max_length=2, blank=True)
    citizenships = models.JSONField(default=list, blank=True)
    onboarding_completed_at = models.DateTimeField(null=True, blank=True)
    available_from = models.DateField(null=True, blank=True)
    linkedin_url = models.URLField(max_length=2048, null=True, blank=True)
    github_url = models.URLField(max_length=2048, null=True, blank=True)
    portfolio_url = models.URLField(max_length=2048, null=True, blank=True)
    # Unverified old URLs are retained without fabricating Document metadata.
    resume_url = models.URLField(
        max_length=2048,
        blank=True,
        help_text="Legacy URL; current_resume is the verified stored CV.",
    )
    current_resume = models.ForeignKey(
        "Document",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="current_for_profiles",
    )
    current_resume_kind = models.CharField(
        max_length=16, default="resume", editable=False
    )
    profile_version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)
    skills = models.ManyToManyField("Skill", through="CandidateSkill", blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(current_resume_kind="resume"),
                name="profile_resume_kind_valid",
            ),
            models.CheckConstraint(
                condition=Q(profile_version__gt=0), name="profile_version_positive"
            ),
        ]

    def __str__(self):
        return self.full_name


class Experience(models.Model):
    profile = models.ForeignKey(
        CandidateProfile, on_delete=models.CASCADE, related_name="experiences"
    )
    company_name = models.CharField(max_length=240)
    title = models.CharField(max_length=240)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    is_current = models.BooleanField(default=False)
    date_precision = models.CharField(
        max_length=8,
        default="month",
        choices=[(v, v.title()) for v in ("day", "month", "year")],
    )
    description = models.TextField(blank=True, default="")
    position = models.IntegerField(default=0)

    class Meta:
        ordering = ["position", "id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(end_date__isnull=True)
                | Q(start_date__isnull=True)
                | Q(end_date__gte=F("start_date")),
                name="experience_dates_valid",
            ),
            models.CheckConstraint(
                condition=Q(is_current=False) | Q(end_date__isnull=True),
                name="experience_current_no_end",
            ),
            allowed(
                "date_precision", ("day", "month", "year"), "experience_precision_valid"
            ),
        ]


class Education(models.Model):
    profile = models.ForeignKey(
        CandidateProfile, on_delete=models.CASCADE, related_name="education"
    )
    institution = models.CharField(max_length=240)
    degree = models.CharField(max_length=240, null=True, blank=True)
    field_of_study = models.CharField(max_length=240, null=True, blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    is_current = models.BooleanField(default=False)
    date_precision = models.CharField(
        max_length=8,
        default="month",
        choices=[(v, v.title()) for v in ("day", "month", "year")],
    )
    description = models.TextField(blank=True, default="")
    position = models.IntegerField(default=0)

    class Meta:
        ordering = ["position", "id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(end_date__isnull=True)
                | Q(start_date__isnull=True)
                | Q(end_date__gte=F("start_date")),
                name="education_dates_valid",
            ),
            models.CheckConstraint(
                condition=Q(is_current=False) | Q(end_date__isnull=True),
                name="education_current_no_end",
            ),
            allowed(
                "date_precision", ("day", "month", "year"), "education_precision_valid"
            ),
        ]


class Project(models.Model):
    profile = models.ForeignKey(
        CandidateProfile, on_delete=models.CASCADE, related_name="projects"
    )
    title = models.CharField(max_length=240)
    description = models.TextField(blank=True, default="")
    url = models.URLField(max_length=2048, null=True, blank=True)
    position = models.IntegerField(default=0)

    class Meta:
        ordering = ["position", "id"]


class CandidateSkill(models.Model):
    profile = models.ForeignKey(
        CandidateProfile, on_delete=models.CASCADE, db_column="candidateprofile_id"
    )
    skill = models.ForeignKey("Skill", on_delete=models.PROTECT)

    class Meta:
        db_table = "jobboard_candidateprofile_skills"
        unique_together = [("profile", "skill")]


class WorkAuthorization(models.Model):
    profile = models.ForeignKey(
        CandidateProfile, on_delete=models.CASCADE, related_name="work_authorizations"
    )
    country_code = models.CharField(max_length=2)
    authorized = models.BooleanField(null=True, blank=True)
    needs_sponsorship = models.BooleanField(null=True, blank=True)
    authorization_basis = models.CharField(max_length=32, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["profile", "country_code"], name="work_auth_country_unique"
            ),
            models.CheckConstraint(
                condition=Q(country_code__regex=r"^[A-Z]{2}$"),
                name="work_auth_country_valid",
            ),
        ]


class SearchPreference(models.Model):
    job_domains = models.ManyToManyField("JobDomain", blank=True)
    job_subdomains = models.ManyToManyField("JobSubdomain", blank=True)
    excluded_job_subdomains = models.ManyToManyField(
        "JobSubdomain", blank=True, related_name="excluded_preferences",
    )
    profile = models.OneToOneField(
        CandidateProfile, on_delete=models.CASCADE, related_name="search_preference"
    )
    roles = models.ManyToManyField("Role", through="PreferenceRole", blank=True)
    locations = models.ManyToManyField(
        "Location", through="PreferenceLocation", blank=True
    )
    minimum_salary = models.DecimalField(
        max_digits=16, decimal_places=2, null=True, blank=True
    )
    salary_currency = models.CharField(max_length=3, null=True, blank=True)
    salary_period = models.CharField(
        max_length=10, choices=SalaryPeriod, null=True, blank=True
    )
    salary_gross_net = models.CharField(
        max_length=5, default="gross", choices=[("gross", "Gross"), ("net", "Net")]
    )
    willing_to_relocate = models.BooleanField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            allowed(
                "salary_gross_net", ("gross", "net"), "preference_salary_basis_valid"
            ),
            models.CheckConstraint(
                condition=Q(
                    minimum_salary__isnull=True,
                    salary_currency__isnull=True,
                    salary_period__isnull=True,
                )
                | Q(
                    minimum_salary__isnull=False,
                    minimum_salary__gte=0,
                    salary_currency__isnull=False,
                    salary_currency__regex=r"^[A-Z]{3}$",
                    salary_period__isnull=False,
                    salary_period__in=SalaryPeriod.values,
                ),
                name="preference_salary_complete",
            ),
        ]


class PreferenceRole(models.Model):
    preference = models.ForeignKey(
        SearchPreference, on_delete=models.CASCADE, db_column="searchpreference_id"
    )
    role = models.ForeignKey("Role", on_delete=models.PROTECT)

    class Meta:
        db_table = "jobboard_searchpreference_roles"
        unique_together = [("preference", "role")]


class PreferenceLocation(models.Model):
    preference = models.ForeignKey(
        SearchPreference, on_delete=models.CASCADE, db_column="searchpreference_id"
    )
    location = models.ForeignKey("Location", on_delete=models.PROTECT)

    class Meta:
        db_table = "jobboard_searchpreference_locations"
        unique_together = [("preference", "location")]


class PreferenceContract(models.Model):
    preference = models.ForeignKey(
        SearchPreference, on_delete=models.CASCADE, related_name="contracts"
    )
    value = models.CharField(
        max_length=24, choices=[c for c in ContractType.choices if c[0] != "unknown"]
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["preference", "value"], name="preference_contract_unique"
            ),
            allowed(
                "value",
                [v for v in ContractType.values if v != "unknown"],
                "preference_contract_valid",
            ),
        ]


class PreferenceWorkMode(models.Model):
    preference = models.ForeignKey(
        SearchPreference, on_delete=models.CASCADE, related_name="work_modes"
    )
    value = models.CharField(
        max_length=12, choices=[c for c in WorkMode.choices if c[0] != "unknown"]
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["preference", "value"], name="preference_work_mode_unique"
            ),
            allowed(
                "value",
                [v for v in WorkMode.values if v != "unknown"],
                "preference_work_mode_valid",
            ),
        ]
