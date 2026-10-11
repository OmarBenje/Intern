from io import BytesIO

from django.http import FileResponse
from django.urls import path
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from jobboard.api import read_serializers as r
from jobboard.api import serializers as s
from jobboard.api.core import APIError
from jobboard.api.downloads import DownloadAPIView
from jobboard.api.drf import paginate
from jobboard.models import CandidateProfile, Document, SearchPreference
from jobboard.services import documents as ds
from jobboard.services import profiles as ps


@api_view(["GET", "PATCH"])
def profile(request):
    if request.method == "PATCH":
        return Response(
            r.ProfileSerializer(
                ps.update_profile(
                    request.user, s.validated(request, s.ProfileSerializer)
                )
            ).data
        )
    item = CandidateProfile.objects.filter(user=request.user).first()
    return Response(r.ProfileSerializer(item).data if item else {"profile": None})


@api_view(["GET", "PUT"])
def preferences(request):
    if request.method == "PUT":
        return Response(
            r.PreferenceSerializer(
                ps.update_preferences(
                    request.user,
                    s.validated(request, s.PreferenceSerializer),
                )
            ).data
        )
    item = SearchPreference.objects.filter(profile__user=request.user).first()
    return Response(
        r.PreferenceSerializer(item).data if item else {"preferences": None}
    )


def children_view(name):
    model, _fields = ps.CHILDREN[name]

    @api_view(["GET", "POST"])
    def collection(request):
        if request.method == "GET":
            return paginate(
                model.objects.filter(profile__user=request.user).order_by("id"),
                request,
                lambda row: r.CHILD_SERIALIZERS[name](row).data,
            )
        row = ps.mutate_child(
            request.user, name, s.validated(request, s.CHILD_SERIALIZERS[name])
        )
        return Response(r.CHILD_SERIALIZERS[name](row).data)

    @api_view(["PATCH", "DELETE"])
    def detail(request, pk):
        if request.method == "DELETE":
            ps.mutate_child(request.user, name, pk=pk, delete=True)
            return Response(status=204)
        row = ps.mutate_child(
            request.user, name, s.validated(request, s.CHILD_SERIALIZERS[name]), pk=pk
        )
        return Response(r.CHILD_SERIALIZERS[name](row).data)

    return collection, detail


@api_view(["GET", "POST"])
@parser_classes([MultiPartParser])
def documents(request):
    if request.method == "GET":
        return paginate(
            Document.objects.filter(owner=request.user).order_by("-created_at", "-id"),
            request,
            lambda row: r.DocumentSerializer(row).data,
        )
    if (
        set(request.POST) - {"kind"}
        or set(request.FILES) != {"file"}
        or len(request.FILES.getlist("file")) != 1
        or len(request.POST.getlist("kind")) != 1
    ):
        raise APIError("invalid_upload", "Supply exactly one file and one kind field.")
    serializer = s.UploadSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    row = ds.upload_document(
        request.user,
        serializer.validated_data["file"],
        serializer.validated_data["kind"],
    )
    return Response(r.DocumentSerializer(row).data)


class DocumentDownloadView(DownloadAPIView):
    def get(self, request, pk):
        document = Document.objects.filter(pk=pk, owner=request.user).first()
        if document is None:
            raise APIError("not_found", "Resource not found.", status=404)
        response = FileResponse(
            BytesIO(ds.read_document(document)),
            as_attachment=True,
            filename=document.original_name or "document.pdf",
            content_type="application/pdf",
        )
        response["X-Content-Type-Options"] = "nosniff"
        response["Content-Security-Policy"] = "sandbox; default-src 'none'"
        return response


download = DocumentDownloadView.as_view()


@api_view(["DELETE"])
def delete_document(request, pk):
    ds.delete_document(request.user, pk)
    return Response(status=204)


@api_view(["PUT"])
def resume(request):
    data = s.validated(request, s.ResumeSerializer)
    if type(data["document_id"]) is not int:
        raise APIError("invalid_id", "document_id must be an integer.")
    return Response(
        r.ProfileSerializer(ds.set_resume(request.user, data["document_id"])).data
    )


urlpatterns = [
    path("profile/", profile),
    path("preferences/", preferences),
    path("profile/resume/", resume),
    path("documents/", documents),
    path("documents/<int:pk>/download/", download),
    path("documents/<int:pk>/", delete_document),
]
for name in ps.CHILDREN:
    collection, detail = children_view(name)
    urlpatterns += [
        path(f"profile/{name}/", collection),
        path(f"profile/{name}/<int:pk>/", detail),
    ]
