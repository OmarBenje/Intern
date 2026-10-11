"""Domain validation helpers and Django error pages (outside DRF dispatch)."""

from django.contrib.auth import get_user_model
from django.db import models
from django.http import JsonResponse


class APIError(Exception):
    def __init__(self, code, message, status=400, details=None):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status
        self.details = details or {}


def error_response(code, message, status=400, details=None):
    return JsonResponse(
        {"error": {"code": code, "message": message, "details": details or {}}},
        status=status,
    )


def integer(value, name="id", minimum=1, maximum=2147483647):
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise APIError("invalid_integer", f"{name} must be an integer.")
    try:
        result = int(value)
    except (ValueError, TypeError):
        raise APIError("invalid_integer", f"{name} must be an integer.") from None
    if str(result) != str(value) or not minimum <= result <= maximum:
        raise APIError("invalid_integer", f"{name} is out of range.")
    return result


def model_data(instance, fields):
    return {name: getattr(instance, name) for name in fields}


def lock_user(user):
    """First lock in every private write; serializes writes against deletion."""
    account = get_user_model().objects.select_for_update().get(pk=user.pk)
    if not account.is_active:
        raise APIError("account_inactive", "Account is inactive.", 403)
    return account


def apply_fields(instance, data, allowed):
    if set(data) - set(allowed):
        raise APIError("invalid_fields", "Unknown fields.")
    for name, value in data.items():
        field = instance._meta.get_field(
            name.removesuffix("_id") if name.endswith("_id") else name
        )
        if value is not None:
            if isinstance(field, models.BooleanField) and not isinstance(value, bool):
                raise APIError("invalid_field", f"{name} must be a boolean.")
            if isinstance(
                field, (models.CharField, models.TextField, models.DateField)
            ) and not isinstance(value, str):
                raise APIError("invalid_field", f"{name} must be text.")
            if isinstance(field, (models.IntegerField, models.ForeignKey)) and (
                not isinstance(value, int) or isinstance(value, bool)
            ):
                raise APIError("invalid_field", f"{name} must be an integer.")
        setattr(instance, name, value)
    instance.full_clean()
    instance.save()
    return instance


def csrf_failure(request, reason=""):
    return error_response("csrf_failed", "Refresh the CSRF token and retry.", 403)


def not_found(request, exception=None):
    return error_response("not_found", "Resource not found.", 404)


def server_error(request):
    return error_response("server_error", "An unexpected error occurred.", 500)
