"""Create a small, entirely fictitious DEV dataset without network calls."""

import hashlib
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from donnees.jeu_fictif import ADMIN_LOGIN, CANDIDATS, MOT_DE_PASSE_DEMO, RECRUTEURS
from jobboard import models as m
from jobboard.integrations.storage import storage_bucket, write_object


class Command(BaseCommand):
    help = "Populate an empty demonstration database (never overwrites existing accounts)."

    @transaction.atomic
    def handle(self, *args, **options):
        User = get_user_model()
        if User.objects.exists() or m.Company.objects.exists():
            raise CommandError(
                "Use an empty dedicated database: existing accounts or companies found."
            )
        if settings.PRIVATE_STORAGE_BACKEND != "local":
            raise CommandError(
                "This fictitious dataset requires local private storage."
            )
        password = MOT_DE_PASSE_DEMO
        pdf = (Path(settings.PROJECT_ROOT) / "donnees/cv_fictif.pdf").read_bytes()
        users = []
        for username, name in CANDIDATS:
            user = User.objects.create_user(
                username=username,
                email=f"{username}@example.test",
                password=password,
                is_active=username != "attente",
            )
            profile = m.CandidateProfile.objects.create(
                user=user,
                full_name=name,
                street_address="1 rue de la Démonstration",
                city="Paris",
                country_code="FR",
                onboarding_completed_at=timezone.now(),
            )
            if username != "attente":
                key = f"dev/{username}/cv.pdf"
                write_object(storage_bucket(), key, pdf)
                document = m.Document.objects.create(
                    owner=user,
                    kind="resume",
                    origin="upload",
                    bucket=storage_bucket(),
                    object_key=key,
                    original_name="cv_fictif.pdf",
                    mime_type="application/pdf",
                    byte_size=len(pdf),
                    sha256=hashlib.sha256(pdf).hexdigest(),
                    status="ready",
                )
                profile.current_resume = document
                profile.save(update_fields=["current_resume"])
            users.append(user)
        User.objects.create_superuser(
            username=ADMIN_LOGIN, email=f"{ADMIN_LOGIN}@example.test", password=password
        )
        companies = [
            m.Company.objects.create(
                name=name,
                description="Entreprise fictive du jeu d'essai DEV.",
                logo_next_attempt_at=None,
            )
            for name in ["Atelier Démo", "Laboratoire Exemple", "Entreprise Sans Offre"]
        ]
        recruiters = []
        for username, name, verified in RECRUTEURS:
            user = User.objects.create_user(
                username=username, email=f"{username}@example.test", password=password
            )
            recruiters.append(
                m.RecruiterProfile.objects.create(
                    user=user,
                    full_name=name,
                    company=companies[0],
                    company_name=companies[0].name,
                    email_verified=verified,
                    verification_status="verified" if verified else "unverified",
                )
            )
        location = m.Location.objects.create(
            name="Paris", canonical_key="dev-paris-fr", city="Paris", country_code="FR"
        )
        sources = []
        for number, title in enumerate(
            [
                "Stage développement Python",
                "Stage interfaces React",
                "Stage analyse de données",
                "Stage administration systèmes",
            ],
            1,
        ):
            company = companies[0] if number <= 2 else companies[1]
            offer = m.Offer.objects.create(
                company=company,
                title=title,
                description="Stage fictif de six mois en France. Travail accompagné, documentation et tests. Aucune candidature réelle ne sera envoyée.",
                contract_type="internship",
                status="open",
                published_at=timezone.now(),
            )
            offer.locations.add(location)
            board, _ = m.SourceBoard.objects.get_or_create(
                provider="intern" if number <= 2 else "demo",
                instance="local",
                board_key=str(recruiters[number - 1].pk)
                if number <= 2
                else f"dev-{company.pk}",
                defaults={
                    "company": company,
                    "base_url": "https://example.test",
                    "enabled": True,
                    "submission_mode": "unsupported",
                },
            )
            source = m.OfferSource.objects.create(
                offer=offer,
                board=board,
                external_id=str(number),
                origin_url=f"https://example.test/stages/{number}",
                apply_url=f"https://example.test/stages/{number}",
                content_hash=hashlib.sha256(title.encode()).hexdigest(),
                last_checked_at=timezone.now(),
            )
            m.OfferEnrichment.objects.create(
                offer=offer,
                classification="confirmed",
                europe_status="in_scope",
                country_codes=["FR"],
                facts={"demo": True},
                extractor_version="dev-fixture",
            )
            if number <= 2:
                m.RecruiterJob.objects.create(
                    owner=recruiters[number - 1],
                    offer=offer,
                    title=title,
                    description=offer.description,
                    location="Paris",
                    status="active",
                    published_at=timezone.now(),
                )
            sources.append(source)
        for user, source in zip(users[:2], sources[:2]):
            application = m.Application.objects.create(
                user=user,
                offer=source.offer,
                source=source,
                status="submitted",
                submitted_at=timezone.now(),
            )
            m.RecruiterApplicant.objects.create(
                application=application,
                job=source.offer.recruiter_job,
                resume=user.candidate_profile.current_resume,
                profile_snapshot={
                    "full_name": user.candidate_profile.full_name,
                    "email": user.email,
                    "demo": True,
                },
            )
            m.SavedOffer.objects.create(user=user, offer=source.offer)
        self.stdout.write(
            self.style.SUCCESS(
                "DEV: 8 accounts, 3 recruiters, 3 companies, 4 offers, 2 applications. Password: see donnees/README.md."
            )
        )
