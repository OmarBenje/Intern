"""Recruiter writes share the session API's user-first transaction discipline."""

import hashlib
from urllib.parse import urlsplit

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from jobboard import models as m
from jobboard.api.core import APIError, lock_user

PERSONAL_DOMAINS = {
    "gmail.com",
    "googlemail.com",
    "yahoo.com",
    "yahoo.fr",
    "hotmail.com",
    "hotmail.fr",
    "outlook.com",
    "outlook.fr",
    "live.com",
    "live.fr",
    "icloud.com",
    "aol.com",
    "proton.me",
    "protonmail.com",
    "orange.fr",
    "wanadoo.fr",
    "laposte.net",
    "free.fr",
}


def validate_professional_email(email):
    if email.rsplit("@", 1)[-1].lower() in PERSONAL_DOMAINS:
        raise APIError(
            "professional_email_required",
            "Utilisez votre adresse e-mail professionnelle.",
            details={"email": [{"code": "professional_email_required"}]},
        )


def workspace(user):
    profile = m.RecruiterProfile.objects.filter(user=user).first()
    if profile is None:
        raise APIError(
            "recruiter_required", "Cet espace est réservé aux recruteurs.", 403
        )
    return profile


def publication_conditions(prefix=""):
    """Conditions shared by direct offer visibility, freshness and applications."""
    return {
        prefix + "status": "active",
        prefix + "owner__verification_status": "verified",
        prefix + "owner__email_verified": True,
        prefix + "owner__user__is_active": True,
    }


def publish(job):
    """A verified owner can publish; the existing catalogue scope still applies."""
    owner = job.owner
    if owner.verification_status != "verified" or not owner.email_verified:
        raise APIError(
            "company_unverified",
            "La validation de votre entreprise est nécessaire pour publier.",
            409,
        )
    if not all((job.title.strip(), job.description.strip(), job.location.strip())):
        raise APIError(
            "incomplete_job", "Complétez le titre, les missions et la localisation."
        )
    company = owner.company
    if company is None:
        company = m.Company.objects.create(
            name=owner.company_name,
            website_url=owner.website_url,
            domain=urlsplit(owner.website_url).hostname,
        )
        owner.company = company
        owner.save(update_fields=["company", "updated_at"])
    now = timezone.now()
    description = job.description
    for label, text in (
        ("Compétences", job.skills),
        ("Formation", job.education),
        ("Langues", job.languages),
        ("Gratification / salaire", job.salary),
    ):
        if text:
            description += f"\n\n{label}\n{text}"
    values = dict(
        title=job.title,
        description=description,
        company=company,
        contract_type=job.contract_type,
        work_mode=job.work_mode,
        status="open",
        published_at=job.published_at or now,
    )
    if job.offer_id:
        offer = job.offer
        for key, value in values.items():
            setattr(offer, key, value)
        offer.save()
    else:
        offer = m.Offer.objects.create(**values)
        job.offer = offer
    location, _ = m.Location.objects.get_or_create(
        canonical_key="recruiter:"
        + hashlib.sha256(
            f"{job.country_code}:{job.location.casefold()}".encode()
        ).hexdigest(),
        defaults={"name": job.location, "country_code": job.country_code},
    )
    offer.locations.set([location])
    board, _ = m.SourceBoard.objects.get_or_create(
        provider="intern",
        instance="direct",
        board_key=str(owner.pk),
        defaults={
            "company": company,
            "enabled": True,
            "base_url": settings.PUBLIC_BASE_URL,
            "submission_mode": "unsupported",
        },
    )
    url = f"{settings.PUBLIC_BASE_URL.rstrip('/')}/offers/{offer.pk}"
    m.OfferSource.objects.update_or_create(
        board=board,
        external_id=str(job.pk),
        defaults={
            "offer": offer,
            "origin_url": url,
            "apply_url": url,
            "source_status": "active",
            "first_seen_at": job.published_at or now,
            "last_seen_at": now,
            "last_checked_at": now,
            "content_hash": hashlib.sha256(description.encode()).hexdigest(),
            "raw_payload": {"title": job.title, "description": description},
        },
    )
    from jobboard.services.engine_quality import enrich_offer

    enrich_offer(offer)
    job.published_at = job.published_at or now


@transaction.atomic
def save_job(user, data, pk=None):
    lock_user(user)
    owner = workspace(user)
    job = (
        owner.jobs.select_for_update().get(pk=pk) if pk else m.RecruiterJob(owner=owner)
    )
    for key, value in data.items():
        setattr(job, key, value)
    job.save()
    if job.status == "active":
        publish(job)
        job.save()
    elif job.offer_id:
        m.Offer.objects.filter(pk=job.offer_id).update(status="hidden")
        m.OfferSource.objects.filter(offer_id=job.offer_id).update(
            source_status="closed"
        )
    return job


@transaction.atomic
def apply_direct(user, pk):
    lock_user(user)
    if m.RecruiterProfile.objects.filter(user=user).exists():
        raise APIError("candidate_required", "Un compte candidat est nécessaire.", 403)
    job = m.RecruiterJob.objects.select_for_update(of=("self",)).get(
        pk=pk,
        **publication_conditions(),
    )
    existing = m.RecruiterApplicant.objects.filter(
        job=job, application__user=user
    ).first()
    if existing:
        return existing
    profile = m.CandidateProfile.objects.get(user=user)
    if not profile.current_resume_id:
        raise APIError("resume_required", "Ajoutez un CV avant de candidater.", 409)
    resume = m.Document.objects.get(
        pk=profile.current_resume_id, owner=user, status="ready"
    )
    source = m.OfferSource.objects.get(offer_id=job.offer_id, board__provider="intern")
    from jobboard.services.applications import create_application, event

    app = create_application(user, job.offer_id, source.pk)
    app.status = "submitted"
    app.submitted_at = timezone.now()
    app.save(update_fields=["status", "submitted_at", "updated_at"])
    event(app, "application_submitted", payload={"provider": "intern"})
    return m.RecruiterApplicant.objects.create(
        application=app,
        job=job,
        resume=resume,
        profile_snapshot={
            "full_name": profile.full_name,
            "email": user.email,
            "headline": profile.headline or "",
            "skills": list(profile.skills.values_list("name", flat=True)),
            "experiences": list(
                m.Experience.objects.filter(profile=profile).values(
                    "title", "company_name", "description"
                )
            ),
            "education": list(
                m.Education.objects.filter(profile=profile).values(
                    "institution", "degree", "description"
                )
            ),
            "projects": list(
                m.Project.objects.filter(profile=profile).values("title", "description")
            ),
        },
    )
