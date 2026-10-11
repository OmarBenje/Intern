"""Read-only overview of the signed-in candidate's applications."""

from django.db.models import Exists, OuterRef, Q, Subquery
from django.urls import path
from rest_framework.decorators import api_view
from rest_framework.response import Response

from jobboard import models as m
from jobboard.api.catalogue import open_offers, serialize_offer
from jobboard.api.core import APIError
from jobboard.api.drf import paginate
from jobboard.api.read_serializers import CompanySerializer


def application_rows(user):
    latest_revision = m.ApplicationRevision.objects.filter(
        application_id=OuterRef("pk")
    ).order_by("-revision_no")
    latest_run = m.AgentRun.objects.filter(application_id=OuterRef("pk")).order_by(
        "-pk"
    )
    documents = m.RevisionDocument.objects.filter(
        revision_id=OuterRef("latest_revision_id"), document__status="ready"
    )
    return (
        m.Application.objects.filter(user=user)
        .select_related("offer__company")
        .annotate(
            latest_revision_id=Subquery(latest_revision.values("id")[:1]),
            workflow_status=Subquery(latest_run.values("status")[:1]),
        )
        .annotate(
            resume_ready=Exists(documents.filter(purpose="resume")),
            cover_letter_ready=Exists(documents.filter(purpose="cover_letter")),
        )
        .order_by("-updated_at", "-pk")
    )


def row_data(app):
    return {
        "id": app.pk,
        "offer": {
            "id": app.offer_id,
            "title": app.offer.title,
            "company": CompanySerializer(app.offer.company).data,
        },
        "status": app.status,
        "workflow_status": app.workflow_status,
        "resume_ready": app.resume_ready,
        "cover_letter_ready": app.cover_letter_ready,
        "submitted_at": app.submitted_at,
        "updated_at": app.updated_at,
    }


@api_view(["GET"])
def dashboard(request):
    query = request.GET.get("q", "").strip()
    if len(query) > 300:
        raise APIError("invalid_filter", "Search is limited to 300 characters.")
    group = request.GET.get("filter", "all")
    needs_input = Q(status="draft") & (
        Q(workflow_status__in=["needs_input", "uncertain"])
        | Q(workflow_status__isnull=True)
        | Q(workflow_status="succeeded")
    )
    filters = {
        "all": Q(),
        "active": Q(
            status__in=[
                "submitted",
                "screening",
                "interview",
                "offer_received",
                "accepted",
            ]
        )
        | Q(status="draft", workflow_status__in=["queued", "running"]),
        "needs_input": needs_input,
        "failed": Q(status="draft", workflow_status="failed") | Q(status="rejected"),
        "skipped": Q(status="withdrawn")
        | Q(status="draft", workflow_status="cancelled"),
    }
    if group not in filters:
        raise APIError("invalid_filter", "Unknown application filter.")
    applications = application_rows(request.user)
    counts = {
        "applications": applications.count(),
        "needs_input": applications.filter(needs_input).count(),
    }
    applications = applications.filter(filters[group])
    offers = open_offers()
    if query:
        search = Q(offer__title__icontains=query) | Q(
            offer__company__name__icontains=query
        )
        applications = applications.filter(search)
        offers = offers.filter(
            Q(title__icontains=query) | Q(company__name__icontains=query)
        )
    page = paginate(applications, request, row_data).data
    profile = (
        m.CandidateProfile.objects.filter(user=request.user).values("full_name").first()
    )
    return Response(
        {
            "offers": [serialize_offer(offer) for offer in offers[:4]],
            "applications": page,
            "counts": counts,
            "full_name": profile["full_name"] if profile else "",
        }
    )


urlpatterns = [path("dashboard/", dashboard)]
