"""Serve cached, rasterized company logos. Never fetch remote URLs on requests."""

import re

from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.urls import path
from rest_framework.decorators import api_view

from jobboard.integrations.storage import read_object, storage_bucket
from jobboard.models import Company
from jobboard.services.company_logos import REJECTED_LOGO_DIGESTS


@api_view(["GET"])
def company_logo(request, company_id):
    company = get_object_or_404(Company, pk=company_id)
    key = company.logo_object_key or ""
    if not re.fullmatch(rf"company-logos/{company_id}/[a-f0-9]{{64}}\.png", key):
        raise Http404
    if key.rsplit("/", 1)[-1].removesuffix(".png") in REJECTED_LOGO_DIGESTS:
        raise Http404
    try:
        data = read_object(storage_bucket(), key)
    except FileNotFoundError:
        raise Http404 from None
    response = HttpResponse(data, content_type="image/png")
    response["Cache-Control"] = "private, max-age=86400"
    response["X-Content-Type-Options"] = "nosniff"
    return response


urlpatterns = [path("companies/<int:company_id>/logo/", company_logo)]
