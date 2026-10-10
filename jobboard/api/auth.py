from hashlib import sha256
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.auth import (
    authenticate,
    get_user_model,
    login,
    logout,
    update_session_auth_hash,
)
from django.contrib.auth.forms import (
    PasswordChangeForm,
    PasswordResetForm,
    SetPasswordForm,
    UserCreationForm,
)
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.middleware.csrf import get_token
from django.urls import path
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from jobboard.api import serializers as s
from jobboard.api.core import APIError, lock_user
from jobboard.models import CandidateProfile, RecruiterProfile
from jobboard.services.auth import throttle


def identity(user):
    from jobboard.api.onboarding import next_step

    recruiter = RecruiterProfile.objects.filter(user=user).first()
    if recruiter:
        return {
            "id": user.pk,
            "username": user.username,
            "email": user.email,
            "full_name": recruiter.full_name,
            "role": "recruiter",
            "onboarding_step": "verify"
            if recruiter.verification_status == "unverified"
            else "complete",
        }
    profile = CandidateProfile.objects.filter(user=user).first()
    return {
        "id": user.pk,
        "username": user.username,
        "email": user.email,
        "onboarding_step": next_step(profile),
        "role": "candidate",
    }


def text(data, key, maximum=254):
    value = data.get(key)
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise APIError("invalid_field", f"{key} is required and must be text.")
    return value


def rate(request, action, username=""):
    # REMOTE_ADDR only: trusting arbitrary X-Forwarded-For permits bypass.
    throttle(action + ":ip", request.META.get("REMOTE_ADDR", "unknown"), limit=30)
    if username:
        throttle(action + ":identity", username.casefold())


@api_view(["GET"])
@permission_classes([AllowAny])
def csrf(request):
    return Response({"csrf_token": get_token(request)})


@api_view(["POST"])
@permission_classes([AllowAny])
def email_availability(request):
    # A deliberate registration UX: disclose availability only, never account data.
    rate(request, "email-availability")
    data = s.validated(request, s.EmailAvailabilitySerializer)
    email = data["email"].strip().casefold()
    throttle("email-availability:identity", email)
    if data["role"] == "recruiter":
        from jobboard.services.recruiters import validate_professional_email

        validate_professional_email(email)
    return Response(
        {"available": not get_user_model().objects.filter(email__iexact=email).exists()}
    )


@api_view(["POST"])
@permission_classes([AllowAny])
def register(request):
    data = s.validated(request, s.RegisterSerializer)
    email = text(data, "email").strip().casefold()
    validate_email(email)
    role = data["role"]
    if role == "recruiter":
        from jobboard.services.recruiters import validate_professional_email

        validate_professional_email(email)
    username = (
        data.get("username") or role + "_" + sha256(email.encode()).hexdigest()[:40]
    )
    rate(request, "register", email)
    if get_user_model().objects.filter(email__iexact=email).exists():
        raise APIError(
            "validation_error",
            "Check your registration details.",
            details={"email": [{"code": "unavailable"}]},
        )
    name = text(data, "full_name", 240)
    password = text(data, "password", 4096)
    form = UserCreationForm(
        {"username": username, "password1": password, "password2": password}
    )
    if not form.is_valid():
        raise APIError(
            "validation_error",
            "Check your registration details.",
            details=form.errors.get_json_data(),
        )
    with transaction.atomic():
        user = form.save(commit=False)
        user.email = email
        user.save()
        if role == "recruiter":
            RecruiterProfile.objects.create(user=user, full_name=name)
        else:
            CandidateProfile.objects.create(user=user, full_name=name)
    login(request, user)
    return Response({"user": identity(user), "csrf_token": get_token(request)})


@api_view(["POST"])
@permission_classes([AllowAny])
def sign_in(request):
    data = s.validated(request, s.LoginSerializer)
    username, password = text(data, "username", 254), text(data, "password", 4096)
    rate(request, "login", username)
    # Keep legacy username access; email lookup must resolve exactly one account.
    matches = list(
        get_user_model()
        .objects.filter(email__iexact=username.strip())
        .values_list("username", flat=True)[:2]
    )
    if len(matches) > 1:
        raise APIError("invalid_credentials", "Invalid credentials.", 401)
    user = authenticate(
        request, username=matches[0] if matches else username, password=password
    )
    if user is None:
        raise APIError("invalid_credentials", "Invalid credentials.", 401)
    login(request, user)
    return Response({"user": identity(user), "csrf_token": get_token(request)})


@api_view(["POST"])
def sign_out(request):
    s.validated(request, s.EmptySerializer)
    logout(request)
    return Response({"ok": True})


@api_view(["GET"])
def me(request):
    return Response({"user": identity(request.user)})


@api_view(["POST"])
def password_change(request):
    data = s.validated(request, s.PasswordChangeSerializer)
    rate(request, "password", request.user.username)
    with transaction.atomic():
        user = lock_user(request.user)
        form = PasswordChangeForm(
            user,
            {
                "old_password": text(data, "old_password", 4096),
                "new_password1": text(data, "new_password", 4096),
                "new_password2": data["new_password"],
            },
        )
        if not form.is_valid():
            raise APIError(
                "validation_error",
                "Invalid password.",
                details=form.errors.get_json_data(),
            )
        form.save()
    update_session_auth_hash(request, user)
    return Response({"ok": True})


@api_view(["POST"])
@permission_classes([AllowAny])
def password_reset(request):
    data = s.validated(request, s.PasswordResetSerializer)
    email = text(data, "email")
    rate(request, "reset", email)
    form = PasswordResetForm({"email": email})
    if not form.is_valid():
        raise APIError("validation_error", "Invalid email.")
    origin = urlsplit(settings.PUBLIC_BASE_URL)
    form.save(
        domain_override=origin.netloc,
        use_https=origin.scheme == "https",
        email_template_name="registration/password_reset_email.txt",
        subject_template_name="registration/password_reset_subject.txt",
        from_email=settings.DEFAULT_FROM_EMAIL,
    )
    return Response({"ok": True})


@api_view(["POST"])
@permission_classes([AllowAny])
def password_reset_confirm(request):
    data = s.validated(request, s.PasswordResetConfirmSerializer)
    rate(request, "reset-confirm")
    try:
        pk = force_str(urlsafe_base64_decode(text(data, "uid")))
        user = get_user_model().objects.get(pk=pk, is_active=True)
    except (
        ValueError,
        TypeError,
        OverflowError,
        ValidationError,
        get_user_model().DoesNotExist,
    ):
        raise APIError("invalid_token", "Invalid or expired reset token.") from None
    with transaction.atomic():
        user = lock_user(user)
        if not default_token_generator.check_token(user, text(data, "token")):
            raise APIError("invalid_token", "Invalid or expired reset token.")
        password = text(data, "new_password", 4096)
        form = SetPasswordForm(
            user, {"new_password1": password, "new_password2": password}
        )
        if not form.is_valid():
            raise APIError(
                "validation_error",
                "Invalid password.",
                details=form.errors.get_json_data(),
            )
        form.save()
    return Response({"ok": True})


urlpatterns = [
    path("auth/" + route + "/", view)
    for route, view in [
        ("csrf", csrf),
        ("register", register),
        ("email-availability", email_availability),
        ("login", sign_in),
        ("logout", sign_out),
        ("me", me),
        ("password", password_change),
        ("password-reset", password_reset),
        ("password-reset-confirm", password_reset_confirm),
    ]
]
