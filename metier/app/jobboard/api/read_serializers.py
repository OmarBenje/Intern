"""Public response schemas; no inferred fields or writable model serializers."""

from django.db import models
from rest_framework import serializers

from jobboard import models as m
from jobboard.services import profiles as ps


class ReadModelSerializer(serializers.ModelSerializer):
    def build_standard_field(self, field_name, model_field):
        if isinstance(model_field, models.DecimalField):
            # Preserve the original Decimal exponent; DjangoJSONEncoder emits a string.
            return serializers.ReadOnlyField, {}
        return super().build_standard_field(field_name, model_field)

    def get_fields(self):
        fields = super().get_fields()
        for field in fields.values():
            field.read_only = True
        return fields


def projection(name, model, fields):
    """Declare bounded schemas for the small vocabulary/child resources."""
    return type(
        name,
        (ReadModelSerializer,),
        {
            "Meta": type("Meta", (), {"model": model, "fields": tuple(fields)}),
        },
    )


class CompanySerializer(ReadModelSerializer):
    logo_url = serializers.SerializerMethodField()
    domain = serializers.SerializerMethodField()

    class Meta:
        model = m.Company
        fields = ("id", "name", "website_url", "domain", "logo_url")

    def get_logo_url(self, company):
        if not company.logo_object_key:
            return None
        version = company.logo_object_key.rsplit("/", 1)[-1].removesuffix(".png")
        from jobboard.services.company_logos import REJECTED_LOGO_DIGESTS

        if version in REJECTED_LOGO_DIGESTS:
            return None
        return f"/api/v1/companies/{company.pk}/logo/?v={version}"

    def get_domain(self, company):
        from jobboard.services.company_logos import employer_domain

        return employer_domain(company.domain)


RoleSerializer = projection("RoleSerializer", m.Role, ("id", "name", "slug"))
SkillSerializer = projection("SkillSerializer", m.Skill, ("id", "name", "slug"))
LocationSerializer = projection(
    "LocationSerializer", m.Location, ("id", "name", "country_code", "region", "city")
)
CompensationSerializer = projection(
    "CompensationSerializer",
    m.CompensationBand,
    ("id", "minimum", "maximum", "currency", "period", "gross_net", "location_id"),
)


class SourceSerializer(ReadModelSerializer):
    provider = serializers.ReadOnlyField(source="board.provider")
    submission_mode = serializers.ReadOnlyField(source="board.submission_mode")

    class Meta:
        model = m.OfferSource
        fields = ("id", "provider", "apply_url", "submission_mode")


class OfferSerializer(ReadModelSerializer):
    company = CompanySerializer()
    role = RoleSerializer(allow_null=True)
    locations = LocationSerializer(many=True)
    skills = SkillSerializer(many=True)
    compensation_bands = CompensationSerializer(many=True)
    sources = SourceSerializer(many=True)

    class Meta:
        model = m.Offer
        fields = (
            "id",
            "title",
            "contract_type",
            "employment_schedule",
            "work_mode",
            "seniority",
            "remote_scope",
            "language_code",
            "status",
            "published_at",
            "expires_at",
            "company",
            "role",
            "locations",
            "skills",
            "compensation_bands",
            "sources",
        )


class OfferDetailSerializer(OfferSerializer):
    class Meta(OfferSerializer.Meta):
        fields = (*OfferSerializer.Meta.fields, "description")


class ProfileSerializer(ReadModelSerializer):
    skill_ids = serializers.SerializerMethodField()

    def get_skill_ids(self, profile):
        return list(profile.skills.order_by("id").values_list("id", flat=True))

    class Meta:
        model = m.CandidateProfile
        fields = (
            "id",
            *ps.PROFILE_FIELDS,
            "profile_version",
            "current_resume_id",
            "updated_at",
            "skill_ids",
        )


class PreferenceSerializer(ReadModelSerializer):
    domains = serializers.SlugRelatedField(many=True, read_only=True, slug_field="slug", source="job_domains")
    subdomains = serializers.SlugRelatedField(many=True, read_only=True, slug_field="slug", source="job_subdomains")
    excluded_subdomains = serializers.SlugRelatedField(many=True, read_only=True, slug_field="slug", source="excluded_job_subdomains")
    role_ids = serializers.SerializerMethodField()
    location_ids = serializers.SerializerMethodField()
    contracts = serializers.SerializerMethodField()
    work_modes = serializers.SerializerMethodField()

    def get_role_ids(self, preference):
        return list(preference.roles.order_by("id").values_list("id", flat=True))

    def get_location_ids(self, preference):
        return list(preference.locations.order_by("id").values_list("id", flat=True))

    def get_contracts(self, preference):
        return list(
            preference.contracts.order_by("value").values_list("value", flat=True)
        )

    def get_work_modes(self, preference):
        return list(
            preference.work_modes.order_by("value").values_list("value", flat=True)
        )

    class Meta:
        model = m.SearchPreference
        fields = (*ps.PREFERENCE_FIELDS, *ps.PREFERENCE_RELATIONS)


DocumentSerializer = projection(
    "DocumentSerializer",
    m.Document,
    (
        "id",
        "kind",
        "original_name",
        "mime_type",
        "byte_size",
        "sha256",
        "status",
        "created_at",
    ),
)
ApplicationSerializer = projection(
    "ApplicationSerializer",
    m.Application,
    (
        "id",
        "offer_id",
        "source_id",
        "status",
        "submitted_at",
        "external_reference",
        "created_at",
        "updated_at",
    ),
)
RunSerializer = projection(
    "RunSerializer",
    m.AgentRun,
    (
        "id",
        "revision_id",
        "purpose",
        "status",
        "phase",
        "attempt_no",
        "error_code",
        "external_receipt",
        "started_at",
        "finished_at",
        "created_at",
    ),
)


class RevisionSerializer(ReadModelSerializer):
    document_ids = serializers.SerializerMethodField()
    missing_fields = serializers.SerializerMethodField()

    def get_document_ids(self, revision):
        return list(revision.document_links.values_list("document_id", flat=True))

    def get_missing_fields(self, revision):
        from jobboard.services.applications import missing_fields

        return missing_fields(revision)

    class Meta:
        model = m.ApplicationRevision
        fields = (
            "id",
            "revision_no",
            "schema_version",
            "profile_snapshot",
            "offer_snapshot",
            "form_snapshot",
            "answers",
            "content_hash",
            "sealed_at",
            "created_at",
            "document_ids",
            "missing_fields",
        )


CHILD_SERIALIZERS = {
    key: projection(model.__name__ + "ReadSerializer", model, ("id", *fields))
    for key, (model, fields) in ps.CHILDREN.items()
}
TaskSerializer = projection(
    "TaskSerializer", m.ApplicationTask, ("id", "title", "due_at", "completed_at")
)
InterviewSerializer = projection(
    "InterviewSerializer",
    m.Interview,
    (
        "id",
        "title",
        "starts_at",
        "ends_at",
        "display_timezone",
        "meeting_url",
        "location_text",
        "status",
        "notes",
    ),
)
EventSerializer = projection(
    "EventSerializer",
    m.ApplicationEvent,
    ("id", "run_id", "kind", "origin", "status_after", "happened_at", "payload"),
)
