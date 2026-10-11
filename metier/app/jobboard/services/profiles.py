"""Owner-scoped, versioned confirmed profile mutations."""

import json

from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.utils import timezone

from jobboard.api.core import APIError, apply_fields, lock_user, model_data
from jobboard.models import (
    CandidateProfile,
    Education,
    Experience,
    JobDomain,
    JobSubdomain,
    Location,
    PreferenceContract,
    PreferenceWorkMode,
    Project,
    Role,
    SearchPreference,
    Skill,
    WorkAuthorization,
)

PROFILE_FIELDS = (
    "full_name",
    "first_name",
    "last_name",
    "phone",
    "headline",
    "presentation",
    "location_text",
    "location_id",
    "available_from",
    "linkedin_url",
    "github_url",
    "portfolio_url",
)
CHILDREN = {
    "experiences": (
        Experience,
        (
            "company_name",
            "title",
            "start_date",
            "end_date",
            "is_current",
            "date_precision",
            "description",
            "position",
        ),
    ),
    "education": (
        Education,
        (
            "institution",
            "degree",
            "field_of_study",
            "start_date",
            "end_date",
            "is_current",
            "date_precision",
            "description",
            "position",
        ),
    ),
    "projects": (Project, ("title", "description", "url", "position")),
    "work-authorizations": (
        WorkAuthorization,
        ("country_code", "authorized", "needs_sponsorship"),
    ),
}
PREFERENCE_FIELDS = (
    "minimum_salary",
    "salary_currency",
    "salary_period",
    "salary_gross_net",
    "willing_to_relocate",
)
PREFERENCE_RELATIONS = (
    "role_ids",
    "location_ids",
    "contracts",
    "work_modes",
    "domains",
    "subdomains",
    "excluded_subdomains",
)


def locked_profile(user):
    lock_user(user)
    profile, _ = CandidateProfile.objects.get_or_create(
        user=user, defaults={"full_name": user.get_full_name() or user.username}
    )
    return CandidateProfile.objects.select_for_update().get(pk=profile.pk)


def bump(profile):
    profile.profile_version += 1
    profile.save(update_fields=["profile_version", "updated_at"])


def id_list(data, model):
    if (
        not isinstance(data, list)
        or len(data) > 200
        or any(type(v) is not int or v <= 0 for v in data)
    ):
        raise APIError("invalid_ids", "Expected up to 200 positive integer IDs.")
    if len(set(data)) != len(data) or model.objects.filter(pk__in=data).count() != len(
        data
    ):
        raise APIError("invalid_ids", "IDs must be unique and exist in the catalogue.")
    return data


def profile_data(profile):
    data = model_data(
        profile,
        ("id", *PROFILE_FIELDS, "profile_version", "current_resume_id", "updated_at"),
    )
    data["skill_ids"] = list(profile.skills.order_by("id").values_list("id", flat=True))
    return data


def snapshot_profile(user):
    profile = CandidateProfile.objects.filter(user=user).first()
    if not profile:
        raise APIError(
            "profile_required",
            "Complete your profile before preparing a dossier.",
            status=409,
        )
    data = profile_data(profile)
    for name, (model, fields) in CHILDREN.items():
        rows = model.objects.filter(profile=profile).order_by("id")
        if model is WorkAuthorization:
            rows = rows.filter(confirmed_at__isnull=False)
        data[name.replace("-", "_")] = [
            model_data(row, ("id", *fields)) for row in rows
        ]
    return json.loads(json.dumps(data, cls=DjangoJSONEncoder))


@transaction.atomic
def update_profile(user, data):
    profile = locked_profile(user)
    fields = dict(data)
    skills = fields.pop("skill_ids", None)
    if "skill_ids" in data:
        skills = id_list(skills, Skill)
    apply_fields(profile, fields, PROFILE_FIELDS)
    if skills is not None:
        profile.skills.set(skills)
    bump(profile)
    return profile


@transaction.atomic
def mutate_child(user, name, data=None, pk=None, delete=False):
    profile = locked_profile(user)
    model, fields = CHILDREN[name]
    instance = (
        model(profile=profile)
        if pk is None
        else model.objects.filter(profile=profile, pk=pk).first()
    )
    if instance is None:
        raise APIError("not_found", "Resource not found.", status=404)
    if delete:
        instance.delete()
    else:
        if model is WorkAuthorization:
            instance.confirmed_at = timezone.now()
        apply_fields(instance, data, fields)
    bump(profile)
    return instance


def preference_data(preference):
    result = model_data(preference, PREFERENCE_FIELDS)
    result.update(
        role_ids=list(preference.roles.order_by("id").values_list("id", flat=True)),
        location_ids=list(
            preference.locations.order_by("id").values_list("id", flat=True)
        ),
        contracts=list(
            preference.contracts.order_by("value").values_list("value", flat=True)
        ),
        work_modes=list(
            preference.work_modes.order_by("value").values_list("value", flat=True)
        ),
        domains=list(
            preference.job_domains.order_by("position", "slug").values_list(
                "slug", flat=True
            )
        ),
        subdomains=list(
            preference.job_subdomains.order_by(
                "domain__position", "position", "slug"
            ).values_list("slug", flat=True)
        ),
        excluded_subdomains=list(
            preference.excluded_job_subdomains.order_by(
                "domain__position", "position", "slug"
            ).values_list("slug", flat=True)
        ),
    )
    return result


@transaction.atomic
def update_preferences(user, data):
    profile = locked_profile(user)
    preference, _ = SearchPreference.objects.get_or_create(profile=profile)
    fields = {k: v for k, v in data.items() if k not in PREFERENCE_RELATIONS}
    apply_fields(preference, fields, PREFERENCE_FIELDS)
    for key, model, relation in [
        ("role_ids", Role, "roles"),
        ("location_ids", Location, "locations"),
    ]:
        if key in data:
            getattr(preference, relation).set(id_list(data[key], model))
    for key, model in [
        ("contracts", PreferenceContract),
        ("work_modes", PreferenceWorkMode),
    ]:
        if key in data:
            values = data[key]
            if (
                not isinstance(values, list)
                or len(values) > 10
                or any(not isinstance(v, str) for v in values)
                or len(set(values)) != len(values)
            ):
                raise APIError("invalid_choices", "Expected a list of unique choices.")
            rows = [model(preference=preference, value=value) for value in values]
            # Validate field choices before replacing existing values (uniqueness checked by DB).
            for row in rows:
                row.full_clean(validate_unique=False, validate_constraints=False)
            getattr(preference, key).all().delete()
            model.objects.bulk_create(rows)
    for key, model, relation in [
        ("domains", JobDomain, "job_domains"),
        ("subdomains", JobSubdomain, "job_subdomains"),
        ("excluded_subdomains", JobSubdomain, "excluded_job_subdomains"),
    ]:
        if key in data:
            values = data[key]
            if (
                not isinstance(values, list)
                or len(values) > 250
                or any(not isinstance(v, str) for v in values)
                or len(set(values)) != len(values)
            ):
                raise APIError("invalid_choices", "Expected unique taxonomy slugs.")
            rows = list(model.objects.filter(slug__in=values))
            if len(rows) != len(values):
                raise APIError("invalid_choices", "Unknown taxonomy choice.")
            getattr(preference, relation).set(rows)
    bump(profile)
    return preference
