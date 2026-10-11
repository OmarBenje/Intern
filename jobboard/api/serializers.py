"""Explicit command schemas. Services remain responsible for transactional invariants."""

from django.db import models
from rest_framework import serializers

from jobboard import models as m
from jobboard.api.core import APIError, integer
from jobboard.services import profiles as ps


class StrictSerializer(serializers.Serializer):
    def run_validation(self, data=serializers.empty):
        if data is not serializers.empty and not isinstance(data, dict):
            raise APIError("invalid_json", "Expected a JSON object.")
        return super().run_validation(data)

    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise APIError("invalid_json", "Expected a JSON object.")
        writable = {name for name, field in self.fields.items() if not field.read_only}
        unknown = set(data) - writable
        missing = {
            name
            for name, field in self.fields.items()
            if field.required and name not in data and not self.partial
        }
        if unknown or missing:
            raise APIError(
                "invalid_fields",
                "Check the request fields.",
                details={
                    "unknown": sorted(unknown),
                    "missing": sorted(missing),
                },
            )
        return super().to_internal_value(data)


class TextField(serializers.CharField):
    def __init__(self, **kwargs):
        super().__init__(trim_whitespace=False, **kwargs)

    def to_internal_value(self, data):
        if not isinstance(data, str):
            raise APIError("invalid_field", f"{self.field_name} must be text.")
        return super().to_internal_value(data)


class IdentifierField(serializers.Field):
    def to_internal_value(self, data):
        return integer(data, self.field_name)

    def to_representation(self, value):
        return value


class ModelInputField(serializers.Field):
    """Preserve primitive inputs for model.full_clean inside the service transaction.

    Django converts dates/decimals there. Validating the JSON primitive here avoids
    DRF's default coercion of numbers into strings and strings into booleans.
    Cross-field constraints and foreign ownership checks belong to the service.
    """

    def __init__(self, model_field, **kwargs):
        self.model_field = model_field
        super().__init__(required=False, allow_null=True, **kwargs)

    def to_internal_value(self, value):
        field = self.model_field
        expected = None
        if isinstance(field, models.BooleanField):
            expected = bool
        elif isinstance(field, (models.CharField, models.TextField, models.DateField)):
            expected = str
        elif isinstance(field, (models.IntegerField, models.ForeignKey)):
            expected = int
        if expected is not None and type(value) is not expected:
            raise APIError("invalid_field", f"{self.field_name} has an invalid type.")
        return value


def model_input_serializer(name, model, fields, extra=None):
    declared = {
        field: ModelInputField(model._meta.get_field(field.removesuffix("_id")))
        for field in fields
    }
    declared.update(extra or {})
    return type(name, (StrictSerializer,), declared)


class EmptySerializer(StrictSerializer):
    pass


class LoginSerializer(StrictSerializer):
    username = TextField(max_length=254)
    password = TextField(max_length=4096, write_only=True)


class RegisterSerializer(LoginSerializer):
    username = TextField(max_length=150, required=False)
    email = TextField(max_length=254)
    full_name = TextField(max_length=240)


class EmailAvailabilitySerializer(StrictSerializer):
    email = serializers.EmailField(max_length=254)


class PasswordChangeSerializer(StrictSerializer):
    old_password = TextField(max_length=4096, write_only=True)
    new_password = TextField(max_length=4096, write_only=True)


class PasswordResetSerializer(StrictSerializer):
    email = TextField(max_length=254)


class PasswordResetConfirmSerializer(StrictSerializer):
    uid = TextField(max_length=254)
    token = TextField(max_length=254)
    new_password = TextField(max_length=4096, write_only=True)


class DeleteAccountSerializer(StrictSerializer):
    password = TextField(max_length=4096, write_only=True)


class CreateApplicationSerializer(StrictSerializer):
    offer_id = IdentifierField()
    source_id = IdentifierField()


class RevisionSerializer(StrictSerializer):
    # Dynamic ATS answers and document ownership are checked by the domain service.
    answers = serializers.JSONField()
    document_ids = serializers.JSONField()


class ApprovalSerializer(StrictSerializer):
    revision_id = IdentifierField()
    content_hash = TextField()
    idempotency_key = TextField()


class StatusSerializer(StrictSerializer):
    status = TextField()
    reason = TextField(allow_blank=True)


class ResolutionSerializer(StrictSerializer):
    outcome = TextField()
    evidence = TextField(allow_blank=True)


class ResumeSerializer(StrictSerializer):
    document_id = serializers.JSONField()

    def validate_document_id(self, value):
        if type(value) is not int:
            raise APIError("invalid_id", "document_id must be an integer.")
        return value


class UploadSerializer(StrictSerializer):
    file = serializers.FileField()
    kind = TextField()


ProfileSerializer = model_input_serializer(
    "ProfileSerializer",
    m.CandidateProfile,
    ps.PROFILE_FIELDS,
    {"skill_ids": serializers.JSONField(required=False, allow_null=True)},
)
PreferenceSerializer = model_input_serializer(
    "PreferenceSerializer",
    m.SearchPreference,
    ps.PREFERENCE_FIELDS,
    {
        key: serializers.JSONField(required=False, allow_null=True)
        for key in ps.PREFERENCE_RELATIONS
    },
)
CHILD_SERIALIZERS = {
    key: model_input_serializer(model.__name__ + "Serializer", model, fields)
    for key, (model, fields) in ps.CHILDREN.items()
}
TaskSerializer = model_input_serializer(
    "TaskSerializer", m.ApplicationTask, ("title", "due_at", "completed_at")
)
InterviewSerializer = model_input_serializer(
    "InterviewSerializer",
    m.Interview,
    (
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


def validated(request, serializer_class):
    if request.content_type != "application/json":
        raise APIError("invalid_content_type", "Use application/json.", 415)
    # DRF returns {} for a zero-length stream; v1 requires an actual JSON object.
    if request.META.get("CONTENT_LENGTH") == "0" or not request.body:
        raise APIError("invalid_json", "Invalid JSON object.")
    serializer = serializer_class(data=request.data)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data
