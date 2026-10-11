"""DRF policies preserving the v1 HTTP contract."""

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.db import IntegrityError
from django.http import Http404
from django.http.request import RequestDataTooBig
from rest_framework import exceptions
from rest_framework.authentication import SessionAuthentication
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response

from jobboard.api.core import APIError, integer


class CsrfSessionAuthentication(SessionAuthentication):
    """Enforce CSRF even on anonymous login/reset requests."""

    def authenticate(self, request):
        try:
            self.enforce_csrf(request)
        except exceptions.PermissionDenied:
            raise APIError(
                "csrf_failed", "Refresh the CSRF token and retry.", 403
            ) from None
        user = getattr(request._request, "user", None)
        if user and user.is_active:
            return user, None
        return None

    def authenticate_header(self, request):
        return "Session"


class ContractJSONRenderer(JSONRenderer):
    # In particular, decimals stay strings and datetimes keep millisecond precision.
    encoder_class = DjangoJSONEncoder


class NoStoreMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith("/api/"):
            response["Cache-Control"] = "no-store"
        return response


def exception_handler(exc, context):
    from rest_framework.views import exception_handler as default_exception_handler

    headers = {}
    if isinstance(exc, APIError):
        code, message, status, details = exc.code, exc.message, exc.status, exc.details
    elif isinstance(exc, ValidationError):
        code, message, status = "validation_error", "Invalid input.", 400
        details = (
            exc.message_dict
            if hasattr(exc, "message_dict")
            else {"fields": exc.messages}
        )
    elif isinstance(exc, (ObjectDoesNotExist, Http404)):
        code, message, status, details = "not_found", "Resource not found.", 404, {}
    elif isinstance(exc, RequestDataTooBig):
        code, message, status, details = "too_large", "Request is too large.", 413, {}
    elif isinstance(exc, IntegrityError):
        code, message, status, details = (
            "conflict",
            "This operation conflicts with existing data.",
            409,
            {},
        )
    else:
        response = default_exception_handler(exc, context)
        if response is None:
            return None
        status, headers = response.status_code, dict(response.items())
        codes = {
            400: ("validation_error", "Invalid input."),
            401: ("authentication_required", "Sign in to continue."),
            403: ("permission_denied", "Permission denied."),
            404: ("not_found", "Resource not found."),
            405: ("method_not_allowed", "Method not allowed."),
            406: ("not_acceptable", "Requested response format is unavailable."),
            415: ("invalid_content_type", "Use application/json."),
            429: ("rate_limited", "Too many requests."),
        }
        code, message = codes.get(status, ("request_error", "Request failed."))
        details = response.data if isinstance(exc, exceptions.ValidationError) else {}
        if isinstance(exc, exceptions.ParseError):
            code, message = "invalid_json", "Invalid JSON object."
    if status == 401:
        headers.setdefault("WWW-Authenticate", "Session")
    return Response(
        {"error": {"code": code, "message": message, "details": details}},
        status=status,
        headers=headers,
    )


class ContractPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100

    def get_page_number(self, request, paginator):
        return integer(request.query_params.get("page", "1"), "page")

    def get_page_size(self, request):
        return integer(
            request.query_params.get("page_size", "20"), "page_size", maximum=100
        )

    def get_paginated_response(self, data):
        return Response(
            {
                "results": data,
                "count": self.page.paginator.count,
                "page": self.page.number,
                "page_size": self.page.paginator.per_page,
            }
        )


def paginate(queryset, request, serialize):
    paginator = ContractPagination()
    page = paginator.paginate_queryset(queryset, request)
    return paginator.get_paginated_response([serialize(item) for item in page])


class WorkspacePermission(IsAuthenticated):
    """Recruiter accounts cannot create candidate data through alternate API routes."""

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        if request.path.startswith(("/api/v1/auth/", "/api/v1/account/", "/api/v1/recruiter/")):
            return True
        from jobboard.models import RecruiterProfile
        return not RecruiterProfile.objects.filter(user=request.user).exists()
