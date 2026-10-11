from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db import transaction
from django.urls import path
from rest_framework.decorators import api_view
from rest_framework.response import Response

from jobboard import models as m
from jobboard.api import read_serializers as r
from jobboard.api import serializers as s
from jobboard.api.core import APIError, apply_fields, integer, lock_user
from jobboard.api.drf import paginate
from jobboard.services import applications as service

TASK_FIELDS = ["title", "due_at", "completed_at"]
INTERVIEW_FIELDS = [
    "title",
    "starts_at",
    "ends_at",
    "display_timezone",
    "meeting_url",
    "location_text",
    "status",
    "notes",
]


def revision_data(revision):
    return r.RevisionSerializer(revision).data


def run_data(run):
    return r.RunSerializer(run).data


@api_view(["GET", "POST"])
def applications(request):
    if request.method == "POST":
        data = s.validated(request, s.CreateApplicationSerializer)
        return Response(
            r.ApplicationSerializer(
                service.create_application(
                    request.user, integer(data["offer_id"]), integer(data["source_id"])
                )
            ).data
        )
    qs = m.Application.objects.filter(user=request.user).order_by("-updated_at", "-pk")
    status = request.GET.get("status")
    if status:
        if status not in m.Application.Status.values:
            raise APIError("invalid_status", "Unknown status.")
        qs = qs.filter(status=status)
    return paginate(qs, request, lambda app: r.ApplicationSerializer(app).data)


@api_view(["GET"])
def application_detail(request, pk):
    app = service.private_application(request.user, pk)
    # Bounded history pages independently of the main tracker page.
    return Response(
        {
            **r.ApplicationSerializer(app).data,
            "latest_revision": revision_data(
                app.revisions.order_by("-revision_no").first()
            )
            if app.revisions.exists()
            else None,
            "latest_run": run_data(app.runs.order_by("-pk").first())
            if app.runs.exists()
            else None,
        }
    )


@api_view(["POST"])
def prepare(request, pk):
    s.validated(request, s.EmptySerializer)
    return Response(revision_data(service.prepare(request.user, pk)))


@api_view(["GET", "POST"])
def revise(request, pk):
    if request.method == "GET":
        app = service.private_application(request.user, pk)
        return paginate(app.revisions.order_by("-revision_no"), request, revision_data)
    data = s.validated(request, s.RevisionSerializer)
    return Response(
        revision_data(
            service.revise(request.user, pk, data["answers"], data["document_ids"])
        )
    )


@api_view(["POST"])
def approve(request, pk):
    data = s.validated(request, s.ApprovalSerializer)
    return Response(
        run_data(
            service.approve(
                request.user,
                pk,
                integer(data["revision_id"]),
                data["content_hash"],
                data["idempotency_key"],
            )
        )
    )


@api_view(["POST"])
def revoke(request, pk):
    s.validated(request, s.EmptySerializer)
    return Response(r.ApplicationSerializer(service.revoke(request.user, pk)).data)


@api_view(["POST"])
def status(request, pk):
    data = s.validated(request, s.StatusSerializer)
    return Response(
        r.ApplicationSerializer(
            service.update_status(request.user, pk, data["status"], data["reason"])
        ).data
    )


@api_view(["POST"])
def resolve(request, pk):
    data = s.validated(request, s.ResolutionSerializer)
    return Response(
        run_data(service.resolve(request.user, pk, data["outcome"], data["evidence"]))
    )


def related_config(kind):
    return (
        (m.ApplicationTask, TASK_FIELDS)
        if kind == "tasks"
        else (m.Interview, INTERVIEW_FIELDS)
    )


def validate_related(kind, data):
    if kind == "interviews" and "display_timezone" in data:
        try:
            ZoneInfo(data["display_timezone"])
        except (ZoneInfoNotFoundError, TypeError, ValueError):
            raise APIError("invalid_timezone", "Provide an IANA time zone.") from None


@api_view(["GET", "POST"])
def related_list(request, pk, kind):
    app = service.private_application(request.user, pk)
    model, fields = related_config(kind)
    if request.method == "GET":
        return paginate(
            model.objects.filter(application=app).order_by("pk"),
            request,
            lambda row: (
                (r.TaskSerializer if kind == "tasks" else r.InterviewSerializer)(
                    row
                ).data
            ),
        )
    data = s.validated(
        request, s.TaskSerializer if kind == "tasks" else s.InterviewSerializer
    )
    validate_related(kind, data)
    with transaction.atomic():
        lock_user(request.user)
        app = service.private_application(request.user, pk, lock=True)
        item = apply_fields(model(application=app), data, fields)
        service.event(app, kind + "_created", payload={"id": item.pk})
    return Response(
        (r.TaskSerializer if kind == "tasks" else r.InterviewSerializer)(item).data
    )


@api_view(["PATCH", "DELETE"])
def related_detail(request, pk, kind, item_id):
    model, fields = related_config(kind)
    data = s.validated(
        request,
        (s.TaskSerializer if kind == "tasks" else s.InterviewSerializer)
        if request.method == "PATCH"
        else s.EmptySerializer,
    )
    validate_related(kind, data)
    with transaction.atomic():
        lock_user(request.user)
        app = service.private_application(request.user, pk, lock=True)
        item = model.objects.get(pk=item_id, application=app)
        if request.method == "DELETE":
            item.delete()
            service.event(app, kind + "_deleted", payload={"id": item_id})
            return Response({"ok": True})
        apply_fields(item, data, fields)
        service.event(app, kind + "_updated", payload={"id": item.pk})
        return Response(
            (r.TaskSerializer if kind == "tasks" else r.InterviewSerializer)(item).data
        )


urlpatterns = [
    path("applications/", applications),
    path("applications/<int:pk>/", application_detail),
]
urlpatterns += [
    path("applications/<int:pk>/" + name + "/", view)
    for name, view in [
        ("prepare", prepare),
        ("revisions", revise),
        ("approve", approve),
        ("revoke", revoke),
        ("status", status),
        ("resolve", resolve),
    ]
]
for kind in ("tasks", "interviews"):
    urlpatterns += [
        path("applications/<int:pk>/" + kind + "/", related_list, {"kind": kind}),
        path(
            "applications/<int:pk>/" + kind + "/<int:item_id>/",
            related_detail,
            {"kind": kind},
        ),
    ]


@api_view(["GET"])
def history(request, pk, kind):
    app = service.private_application(request.user, pk)
    if kind == "runs":
        return paginate(app.runs.order_by("-pk"), request, run_data)
    return paginate(
        app.events.order_by("-happened_at", "-pk"),
        request,
        lambda item: r.EventSerializer(item).data,
    )


urlpatterns += [
    path("applications/<int:pk>/" + kind + "/", history, {"kind": kind})
    for kind in ["runs", "events"]
]
