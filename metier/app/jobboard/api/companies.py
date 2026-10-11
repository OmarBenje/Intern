"""Company pages use the same mandatory publication boundary as the catalogue."""

from django.shortcuts import get_object_or_404
from django.urls import path
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from jobboard.api.catalogue import (
    filtered_offers,
    list_offers,
    open_offers,
    serialize_offer,
)
from jobboard.api.drf import paginate
from jobboard.api.read_serializers import CompanySerializer, OfferSerializer
from jobboard.models import Company, CompanyProfile
from jobboard.services.company_profiles_schema import (
    FACT_LABELS,
    SECTION_LABELS,
    public_url,
    publish_entries,
)


@api_view(["GET"])
@permission_classes([AllowAny])
def company_detail(request, pk):
    company = get_object_or_404(Company, pk=pk)
    data = CompanySerializer(company).data
    data["website_url"] = public_url(company.website_url)
    profile = CompanyProfile.objects.filter(company=company).first()
    facts = publish_entries(profile.facts, FACT_LABELS) if profile else []
    sections = publish_entries(profile.sections, SECTION_LABELS) if profile else []
    # Legacy descriptions remain explicit, without pretending to have source provenance.
    data["description"] = next(
        (entry["value"] for entry in sections if entry["key"] == "presentation"),
        company.description,
    )
    data["profile"] = {
        "facts": facts,
        "sections": sections,
        "updated_at": profile.updated_at if profile else None,
        "missing_sections": [
            {"key": key, "label": label}
            for key, label in SECTION_LABELS.items()
            if key not in {entry["key"] for entry in sections}
        ],
    }
    offers = open_offers().filter(company=company)
    data["offers_count"] = offers.count()
    data["hiring_locations"] = list(
        offers.order_by()
        .values("locations__name", "locations__city", "locations__country_code")
        .exclude(locations__id=None)
        .distinct()
    )
    return Response(data)


@api_view(["GET"])
@permission_classes([AllowAny])
def company_offers(request, pk):
    get_object_or_404(Company, pk=pk)
    serializer = OfferSerializer()
    return paginate(
        list_offers(filtered_offers(request).filter(company_id=pk)),
        request,
        lambda offer: serialize_offer(offer, serializer=serializer),
    )


urlpatterns = [
    path("companies/<int:pk>/", company_detail),
    path("companies/<int:pk>/offers/", company_offers),
]
