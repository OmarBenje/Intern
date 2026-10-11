from django.contrib.auth import logout
from django.http import FileResponse
from django.urls import path
from rest_framework.decorators import api_view
from rest_framework.response import Response

from jobboard.api import serializers as s
from jobboard.api.downloads import DownloadAPIView
from jobboard.services.accounts import export_account, request_deletion


class AccountExportView(DownloadAPIView):
    def get(self, request):
        response = FileResponse(
            export_account(request.user),
            as_attachment=True,
            filename="intern-account.zip",
            content_type="application/zip",
        )
        response["Cache-Control"] = "no-store"
        return response


export = AccountExportView.as_view()


@api_view(["POST"])
def delete(request):
    data = s.validated(request, s.DeleteAccountSerializer)
    deletion = request_deletion(request.user, data["password"])
    logout(request)
    return Response({"id": deletion.pk, "status": deletion.status}, status=202)


urlpatterns = [
    path("account/export/", export, name="account-export"),
    path("account/delete/", delete, name="account-delete"),
]
