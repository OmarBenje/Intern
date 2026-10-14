"""Run with Django shell on a dedicated measurement database; print JMeter CSV."""

import csv
import sys

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from jobboard.models import Application, CandidateProfile, OfferSource


def prepare():
    User = get_user_model()
    source = OfferSource.objects.order_by("pk").first()
    if source is None:
        raise RuntimeError("Import the fictitious SQL dataset first.")
    rows = []
    with transaction.atomic():
        for number in range(1, 21):
            username = f"mesure{number:02d}"
            password = "Mesure-Fictive-2026!"
            user, created = User.objects.get_or_create(
                username=username,
                defaults={"email": f"{username}@example.test", "is_active": True},
            )
            if not created and (
                user.email != f"{username}@example.test"
                or not user.is_active
                or not user.check_password(password)
                or user.is_staff
                or user.is_superuser
            ):
                raise RuntimeError(f"Existing account conflicts with fixture: {username}")
            if created:
                user.set_password(password)
                user.save(update_fields=["password"])
            CandidateProfile.objects.get_or_create(
                user=user,
                defaults={
                    "full_name": f"Candidat fictif {number:02d}",
                    "onboarding_completed_at": timezone.now(),
                },
            )
            application, _ = Application.objects.get_or_create(
                user=user,
                offer=source.offer,
                defaults={"source": source, "status": "draft"},
            )
            rows.append((username, password, application.pk))
    writer = csv.writer(sys.stdout, lineterminator="\n")
    writer.writerow(("username", "password", "application_id"))
    writer.writerows(rows)


prepare()
