"""Streaming endpoints choose their own media type; errors remain JSON."""

from rest_framework.negotiation import DefaultContentNegotiation
from rest_framework.views import APIView


class DownloadNegotiation(DefaultContentNegotiation):
    def select_renderer(self, request, renderers, format_suffix=None):
        # FileResponse sets application/pdf or application/zip after permission checks.
        # Accept: application/pdf must not reject the request before the file is read.
        return renderers[0], renderers[0].media_type


class DownloadAPIView(APIView):
    content_negotiation_class = DownloadNegotiation
    http_method_names = ("get", "options")
