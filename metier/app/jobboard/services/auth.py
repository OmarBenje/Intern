from datetime import timedelta

from django.conf import settings
from django.contrib.auth.forms import UserCreationForm
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import salted_hmac

from jobboard.api.core import APIError
from jobboard.models import CandidateProfile, RecruiterProfile, RequestThrottle


def register_account(*, username, email, full_name, password, role):
    form = UserCreationForm(
        {"username": username, "password1": password, "password2": password}
    )
    if not form.is_valid():
        raise APIError(
            "validation_error",
            "Vérifiez les informations d'inscription.",
            details=form.errors.get_json_data(),
        )

    with transaction.atomic():
        user = form.save(commit=False)
        user.email = email
        user.is_active = False
        user.save()
        if role == "recruiter":
            RecruiterProfile.objects.create(user=user, full_name=full_name)
        else:
            CandidateProfile.objects.create(user=user, full_name=full_name)
    return user


def throttle(scope, identity, limit=None, seconds=900):
    key = salted_hmac("intern-throttle", f"{scope}:{identity}").hexdigest()
    now = timezone.now()
    with transaction.atomic():
        # get_or_create resolves a racing first insertion through its unique key.
        RequestThrottle.objects.get_or_create(
            key=key, defaults={"expires_at": now + timedelta(seconds=seconds)}
        )
        counter = RequestThrottle.objects.select_for_update().get(key=key)
        if counter.expires_at <= now:
            counter.count = 0
            counter.expires_at = now + timedelta(seconds=seconds)
        counter.count += 1
        counter.save(update_fields=["count", "expires_at"])
        exceeded = counter.count > (limit or settings.AUTH_RATE_LIMIT)
    if exceeded:
        raise APIError("rate_limited", "Too many attempts. Try again later.", 429)
