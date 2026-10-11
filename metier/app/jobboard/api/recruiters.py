"""Session-authenticated recruiter API. All resource lookups are owner-scoped."""

import secrets
from datetime import timedelta
from io import BytesIO
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Avg, F, Sum
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.urls import path
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import api_view
from rest_framework.response import Response

from jobboard import models as m
from jobboard.api.core import APIError, lock_user
from jobboard.api.downloads import DownloadAPIView
from jobboard.api.drf import paginate
from jobboard.api.serializers import StrictSerializer, validated
from jobboard.services.auth import throttle
from jobboard.services.recruiters import apply_direct, save_job, workspace

PROFILE_FIELDS = (
    "full_name",
    "company_name",
    "siren",
    "website_url",
    "linkedin_url",
    "verification_status",
    "email_verified",
)
JOB_FIELDS = (
    "id",
    "title",
    "department",
    "contract_type",
    "location",
    "country_code",
    "work_mode",
    "salary",
    "description",
    "skills",
    "education",
    "languages",
    "status",
    "origin",
    "published_at",
    "offer_id",
)


def fields(obj, names):
    return {name: getattr(obj, name) for name in names}


class VerificationInput(StrictSerializer):
    company_name = serializers.CharField(max_length=240)
    siren = serializers.RegexField(r"^\d{9}$")
    website_url = serializers.URLField(max_length=2048)
    linkedin_url = serializers.URLField(
        max_length=2048, allow_blank=True, required=False, default=""
    )

    def validate_siren(self, value):
        digits = [int(c) * (2 if i % 2 else 1) for i, c in enumerate(value)]
        if value == "000000000" or sum(n // 10 + n % 10 for n in digits) % 10:
            raise serializers.ValidationError("Le numéro SIREN est invalide.")
        return value

    def validate_website_url(self, value):
        if urlsplit(value).scheme != "https":
            raise serializers.ValidationError("Utilisez une URL HTTPS.")
        return value


class CodeInput(StrictSerializer):
    code = serializers.RegexField(r"^\d{6}$")


class JobInput(StrictSerializer):
    title = serializers.CharField(max_length=300)
    department = serializers.CharField(max_length=160, allow_blank=True, required=False)
    contract_type = serializers.ChoiceField(
        choices=["internship", "apprenticeship", "employment"], required=False
    )
    location = serializers.CharField(max_length=240, allow_blank=True, required=False)
    country_code = serializers.RegexField(r"^[A-Z]{2}$", required=False)
    work_mode = serializers.ChoiceField(
        choices=["onsite", "hybrid", "remote"], required=False
    )
    salary = serializers.CharField(max_length=160, allow_blank=True, required=False)
    description = serializers.CharField(
        max_length=50000, allow_blank=True, required=False
    )
    skills = serializers.CharField(max_length=5000, allow_blank=True, required=False)
    education = serializers.CharField(max_length=160, allow_blank=True, required=False)
    languages = serializers.CharField(max_length=240, allow_blank=True, required=False)
    status = serializers.ChoiceField(
        choices=["draft", "active", "paused", "archived"], required=False
    )


class ApplicantInput(StrictSerializer):
    stage = serializers.ChoiceField(
        choices=["new", "recommended", "review", "interview", "accepted", "rejected"],
        required=False,
    )
    rejection_reason = serializers.CharField(
        max_length=5000, allow_blank=True, required=False
    )
    interview_at = serializers.DateTimeField(allow_null=True, required=False)


class IntegrationInput(StrictSerializer):
    provider = serializers.ChoiceField(
        choices=[
            "greenhouse",
            "lever",
            "workday",
            "ashby",
            "smartrecruiters",
            "wttj",
            "feed",
        ]
    )
    url = serializers.URLField(max_length=2048)

    def validate_url(self, value):
        if urlsplit(value).scheme != "https":
            raise serializers.ValidationError("Utilisez une URL HTTPS.")
        return value


def job_data(job):
    return {
        **fields(job, JOB_FIELDS),
        "applicant_count": job.applicants.filter(application__user__is_active=True)
        .exclude(application__status="withdrawn")
        .count(),
    }


def applicant_data(applicant):
    return {
        **fields(
            applicant,
            (
                "id",
                "job_id",
                "stage",
                "match_score",
                "ai_summary",
                "rejection_reason",
                "interview_at",
                "updated_at",
            ),
        ),
        "profile": applicant.profile_snapshot,
        "job_title": applicant.job.title,
        "resume_url": f"/api/v1/recruiter/candidates/{applicant.pk}/resume/"
        if applicant.resume_id
        else None,
    }


@api_view(["GET", "POST"])
def verification(request):
    owner = workspace(request.user)
    if request.method == "POST":
        data = validated(request, VerificationInput)
        with transaction.atomic():
            lock_user(request.user)
            owner = workspace(request.user)
            if not owner.email_verified:
                raise APIError(
                    "email_unverified",
                    "Validez votre adresse e-mail avant de continuer.",
                    409,
                )
            if owner.verification_status == "verified":
                raise APIError(
                    "already_verified",
                    "Contactez l’équipe pour modifier une entreprise vérifiée.",
                    409,
                )
            for key, value in data.items():
                setattr(owner, key, value)
            owner.verification_status = "pending"
            owner.save()
    return Response(fields(owner, PROFILE_FIELDS))


@api_view(["POST"])
def send_code(request):
    workspace(request.user)
    validated(request, StrictSerializer)
    throttle("recruiter-email", str(request.user.pk), limit=5)
    code = f"{secrets.randbelow(1000000):06d}"
    with transaction.atomic():
        lock_user(request.user)
        owner = workspace(request.user)
        if owner.email_verified:
            return Response({"ok": True})
        owner.email_code_hash = make_password(code)
        owner.email_code_expires_at = timezone.now() + timedelta(minutes=10)
        owner.save()
        try:
            send_mail(
                "Votre code Intern",
                f"Votre code de vérification : {code}. Valable 10 minutes.",
                settings.DEFAULT_FROM_EMAIL,
                [request.user.email],
            )
        except Exception as exc:
            raise APIError(
                "email_unavailable", "L’envoi a échoué. Réessayez.", 503
            ) from exc
    return Response({"ok": True})


@api_view(["POST"])
def verify_code(request):
    workspace(request.user)
    data = validated(request, CodeInput)
    throttle("recruiter-code", str(request.user.pk), limit=10)
    with transaction.atomic():
        lock_user(request.user)
        owner = workspace(request.user)
        if (
            not owner.email_code_expires_at
            or owner.email_code_expires_at <= timezone.now()
            or not check_password(data["code"], owner.email_code_hash)
        ):
            raise APIError("invalid_code", "Code invalide ou expiré.")
        owner.email_verified = True
        owner.email_code_hash = ""
        owner.email_code_expires_at = None
        owner.save()
    return Response(fields(owner, PROFILE_FIELDS))


@api_view(["GET"])
def dashboard(request):
    owner = workspace(request.user)
    applicants = candidates_query(request.user)
    return Response(
        {
            "company": fields(owner, PROFILE_FIELDS),
            "counts": {
                "active_jobs": owner.jobs.filter(status="active").count(),
                "applications": applicants.count(),
                "average_match": applicants.aggregate(value=Avg("match_score"))[
                    "value"
                ],
                "views": owner.jobs.aggregate(value=Sum("views"))["value"] or 0,
            },
            "activity": [
                applicant_data(a)
                for a in applicants.select_related("job").order_by("-updated_at")[:8]
            ],
        }
    )


@api_view(["GET", "POST"])
def jobs(request):
    owner = workspace(request.user)
    if request.method == "POST":
        return Response(
            job_data(save_job(request.user, validated(request, JobInput))), status=201
        )
    query = owner.jobs.order_by("-updated_at", "-id")
    if request.query_params.get("q"):
        query = query.filter(title__icontains=request.query_params["q"][:300])
    for name in ("status", "contract_type", "origin"):
        if request.query_params.get(name):
            query = query.filter(**{name: request.query_params[name]})
    if request.query_params.get("location"):
        query = query.filter(location__icontains=request.query_params["location"][:240])
    return paginate(query, request, job_data)


@api_view(["GET", "PATCH"])
def job_detail(request, pk):
    owner = workspace(request.user)
    job = get_object_or_404(owner.jobs, pk=pk)
    if request.method == "PATCH":
        schema = JobInput(data=request.data, partial=True)
        schema.is_valid(raise_exception=True)
        job = save_job(request.user, schema.validated_data, pk)
    return Response(job_data(job))


@api_view(["POST"])
def duplicate(request, pk):
    owner = workspace(request.user)
    validated(request, StrictSerializer)
    job = get_object_or_404(owner.jobs, pk=pk)
    data = fields(job, tuple(JobInput().fields))
    data.update(title=job.title[:290] + " (copie)", status="draft")
    return Response(job_data(save_job(request.user, data)), status=201)


def candidates_query(user):
    return (
        m.RecruiterApplicant.objects.filter(
            job__owner=workspace(user), application__user__is_active=True
        )
        .exclude(application__status="withdrawn")
        .select_related("job", "resume", "application")
    )


@api_view(["GET"])
def candidates(request, pk=None):
    query = candidates_query(request.user)
    if pk is not None:
        get_object_or_404(workspace(request.user).jobs, pk=pk)
        query = query.filter(job_id=pk)
    score = request.query_params.get("min_score")
    if score:
        try:
            score = int(score)
        except ValueError:
            raise APIError("invalid_score", "Score invalide.") from None
        if not 0 <= score <= 100:
            raise APIError(
                "invalid_score", "Le score doit être compris entre 0 et 100."
            )
        query = query.filter(match_score__gte=score)
    return paginate(
        query.order_by(F("match_score").desc(nulls_last=True), "-id"),
        request,
        applicant_data,
    )


@api_view(["GET", "PATCH"])
def candidate_detail(request, pk):
    applicant = get_object_or_404(candidates_query(request.user), pk=pk)
    if request.method == "PATCH":
        data = validated(request, ApplicantInput)
        with transaction.atomic():
            lock_user(request.user)
            lock_user(applicant.application.user)
            applicant = get_object_or_404(
                candidates_query(request.user).select_for_update(of=("self",)), pk=pk
            )
            for key, value in data.items():
                setattr(applicant, key, value)
            if applicant.stage == "rejected" and not applicant.rejection_reason.strip():
                raise APIError("reason_required", "Indiquez le motif du refus.")
            applicant.save()
            status = {
                "new": "submitted",
                "recommended": "screening",
                "review": "screening",
                "interview": "interview",
                "accepted": "accepted",
                "rejected": "rejected",
            }[applicant.stage]
            application = applicant.application
            if application.status != status:
                application.status = status
                application.save(update_fields=["status", "updated_at"])
                from jobboard.services.applications import event

                event(
                    application,
                    "recruiter_status_changed",
                    origin="system",
                    payload={"stage": applicant.stage},
                )
    return Response(applicant_data(applicant))


class ResumeView(DownloadAPIView):
    def get(self, request, pk):
        applicant = get_object_or_404(
            candidates_query(request.user), pk=pk, resume__isnull=False
        )
        from jobboard.services.documents import read_document

        response = FileResponse(
            BytesIO(read_document(applicant.resume)),
            content_type="application/pdf",
            filename="cv.pdf",
            as_attachment=request.query_params.get("download") == "1",
        )
        response["X-Content-Type-Options"] = "nosniff"
        response["Content-Security-Policy"] = "sandbox; default-src 'none'"
        response["X-Frame-Options"] = "SAMEORIGIN"
        return response


@api_view(["GET", "POST"])
def integrations(request):
    owner = workspace(request.user)
    if request.method == "POST":
        data = validated(request, IntegrationInput)
        with transaction.atomic():
            lock_user(request.user)
            m.RecruiterIntegration.objects.update_or_create(
                owner=owner,
                provider=data["provider"],
                defaults={"url": data["url"], "status": "pending"},
            )
    return Response(
        {
            "results": [
                fields(item, ("id", "provider", "url", "status"))
                for item in owner.integrations.order_by("provider")
            ]
        }
    )


@api_view(["POST"])
def direct_application(request, pk):
    validated(request, StrictSerializer)
    applicant = apply_direct(request.user, pk)
    return Response({"application_id": applicant.application_id}, status=201)


urlpatterns = [
    path("verify/", verification),
    path("verify/send-code/", send_code),
    path("verify/code/", verify_code),
    path("dashboard/", dashboard),
    path("jobs/", jobs),
    path("jobs/<int:pk>/", job_detail),
    path("jobs/<int:pk>/duplicate/", duplicate),
    path("jobs/<int:pk>/applicants/", candidates),
    path("jobs/<int:pk>/apply/", direct_application),
    path("candidates/", candidates),
    path("candidates/<int:pk>/", candidate_detail),
    path("candidates/<int:pk>/resume/", ResumeView.as_view()),
    path("integrations/", integrations),
]
