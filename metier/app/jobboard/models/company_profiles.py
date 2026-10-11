"""Source-backed employer information, separate from private candidate preferences."""

from django.db import models

from jobboard.services.company_profiles_schema import validate_facts, validate_sections


class CompanyProfile(models.Model):
    company = models.OneToOneField(
        "Company", on_delete=models.CASCADE, related_name="public_profile"
    )
    facts = models.JSONField(default=list, blank=True, validators=[validate_facts])
    sections = models.JSONField(
        default=list, blank=True, validators=[validate_sections]
    )
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.company.name
