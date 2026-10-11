"""Candidate-owned engine resources with explicit input/output projections."""

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db import connection, transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404
from django.urls import path
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from jobboard import models as m
from jobboard.api.core import APIError, lock_user, model_data
from jobboard.api.drf import paginate
from jobboard.api.serializers import EmptySerializer, StrictSerializer, validated
from jobboard.services.engine_filters import CatalogueFilters


def partial_validated(request, serializer_class):
    if request.content_type != "application/json":
        raise APIError("invalid_content_type", "Use application/json.", 415)
    serializer = serializer_class(data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


def empty_validated(request):
    return validated(request, EmptySerializer) if request.body else {}


class Criteria(CatalogueFilters):
    domains = serializers.ListField(child=serializers.SlugField(max_length=80), max_length=24, required=False)
    subdomains = serializers.ListField(child=serializers.SlugField(max_length=100), max_length=250, required=False)
    q = serializers.CharField(max_length=300, required=False, allow_blank=True)
    country_codes = serializers.ListField(
        child=serializers.RegexField(r"^[A-Z]{2}$"), max_length=60, required=False
    )
    domain = serializers.CharField(max_length=80, required=False)
    classification = serializers.ChoiceField(
        choices=["confirmed", "not_internship", "uncertain"], required=False
    )
    europe_scope = serializers.ChoiceField(
        choices=["in_scope", "out_of_scope", "unknown"], required=False
    )
    contract_type = serializers.ChoiceField(
        choices=m.Offer.ContractType.values, required=False
    )
    work_mode = serializers.ChoiceField(choices=m.Offer.WorkMode.values, required=False)
    unknown_policy = serializers.ChoiceField(
        choices=["include", "exclude"], required=False
    )
    duration_max_months = serializers.IntegerField(
        min_value=1, max_value=36, required=False
    )
    available_from = serializers.DateField(required=False)
    available_until = serializers.DateField(required=False)
    languages = serializers.ListField(
        child=serializers.RegexField(r"^[a-z]{2}$"), max_length=30, required=False
    )
    needs_sponsorship = serializers.BooleanField(required=False)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        from jobboard.services.job_taxonomy import validate_selection

        try:
            domains, subdomains = validate_selection(attrs.get("domains", []), attrs.get("subdomains", []))
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc
        if "domains" in attrs:
            attrs["domains"] = domains
        if "subdomains" in attrs:
            attrs["subdomains"] = subdomains
        if attrs.get("domain") and (domains or subdomains):
            raise serializers.ValidationError("Use either legacy domain or domains/subdomains.")
        if "include_unknown" in attrs:
            attrs["unknown_policy"] = (
                "include" if attrs["include_unknown"] == "true" else "exclude"
            )
        if (
            attrs.get("available_from")
            and attrs.get("available_until")
            and attrs["available_from"] > attrs["available_until"]
        ):
            raise serializers.ValidationError("Availability dates are reversed.")
        return {
            key: value.isoformat() if hasattr(value, "isoformat") else value
            for key, value in attrs.items()
        }


class SearchInput(StrictSerializer):
    name = serializers.CharField(max_length=160)
    criteria = Criteria(required=False, default=dict)
    frequency = serializers.ChoiceField(choices=["off", "daily"], default="off")
    timezone = serializers.CharField(max_length=64, default="Europe/Paris")

    def validate_timezone(self, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise serializers.ValidationError("Unknown timezone.") from None
        return value


class FeedbackInput(StrictSerializer):
    reason = serializers.ChoiceField(
        choices=[
            "not_interested",
            "wrong_role",
            "wrong_location",
            "wrong_contract",
            "other",
        ]
    )


class ReportInput(StrictSerializer):
    reason = serializers.ChoiceField(
        choices=[
            "closed",
            "duplicate",
            "wrong_location",
            "wrong_contract",
            "not_internship",
            "other",
        ]
    )
    details = serializers.CharField(max_length=2000, allow_blank=True, default="")


class CompanyInput(StrictSerializer):
    excluded = serializers.BooleanField()


class ExternalInput(StrictSerializer):
    url = serializers.URLField(max_length=2048)
    title = serializers.CharField(max_length=300, required=False, allow_blank=True)
    company_name = serializers.CharField(
        max_length=240, required=False, allow_blank=True
    )
    description = serializers.CharField(
        max_length=20000, required=False, allow_blank=True
    )

    def validate_url(self, value):
        from urllib.parse import urlsplit

        parts = urlsplit(value)
        if (
            parts.scheme != "https"
            or parts.username
            or parts.password
            or "\\" in value
            or any(ord(c) < 32 for c in value)
        ):
            raise serializers.ValidationError("Use an HTTPS URL without credentials.")
        return value


SEARCH_FIELDS = [
    "id",
    "name",
    "criteria",
    "frequency",
    "timezone",
    "version",
    "created_at",
    "updated_at",
    "last_evaluated_at",
]
EXTERNAL_FIELDS = [
    "id",
    "url",
    "title",
    "company_name",
    "description",
    "status",
    "error_code",
    "offer_id",
    "created_at",
    "updated_at",
]


@api_view(["GET", "POST"])
def saved_searches(request):
    if request.method == "GET":
        return paginate(
            m.SavedSearch.objects.filter(user=request.user).order_by("-id"),
            request,
            lambda item: model_data(item, SEARCH_FIELDS),
        )
    data = validated(request, SearchInput)
    with transaction.atomic():
        lock_user(request.user)
        if m.SavedSearch.objects.filter(user=request.user).count() >= 50:
            raise APIError("search_limit", "At most 50 saved searches are supported.")
        item = m.SavedSearch.objects.create(
            user=request.user, last_evaluated_at=timezone.now(), **data
        )
    return Response(model_data(item, SEARCH_FIELDS), status=201)


@api_view(["GET", "PATCH", "DELETE"])
def saved_search(request, pk):
    if request.method == "GET":
        return Response(
            model_data(
                get_object_or_404(m.SavedSearch, user=request.user, pk=pk),
                SEARCH_FIELDS,
            )
        )
    data = (
        partial_validated(request, SearchInput)
        if request.method == "PATCH"
        else empty_validated(request)
    )
    with transaction.atomic():
        lock_user(request.user)
        item = get_object_or_404(
            m.SavedSearch.objects.select_for_update(), user=request.user, pk=pk
        )
        if request.method == "DELETE":
            item.delete()
            return Response(status=204)
        if any(getattr(item, key) != value for key, value in data.items()):
            for key, value in data.items():
                setattr(item, key, value)
            item.version += 1
            item.last_evaluated_at = (
                timezone.now()
            )  # New criteria establish a fresh baseline.
            item.save()
    return Response(model_data(item, SEARCH_FIELDS))


@api_view(["PUT", "DELETE"])
def feedback(request, pk):
    data = (
        validated(request, FeedbackInput)
        if request.method == "PUT"
        else empty_validated(request)
    )
    with transaction.atomic():
        lock_user(request.user)
        offer = get_object_or_404(m.Offer.objects.exclude(status="hidden"), pk=pk)
        if request.method == "PUT":
            m.OfferFeedback.objects.update_or_create(
                user=request.user, offer=offer, defaults=data
            )
        else:
            m.OfferFeedback.objects.filter(user=request.user, offer=offer).delete()
    return Response({"offer_id": pk, "hidden": request.method == "PUT"})


@api_view(["PUT", "DELETE"])
def company_preference(request, pk):
    data = (
        validated(request, CompanyInput)
        if request.method == "PUT"
        else empty_validated(request)
    )
    with transaction.atomic():
        lock_user(request.user)
        company = get_object_or_404(m.Company, pk=pk)
        if request.method == "PUT":
            m.CompanyPreference.objects.update_or_create(
                user=request.user, company=company, defaults=data
            )
        else:
            m.CompanyPreference.objects.filter(
                user=request.user, company=company
            ).delete()
    return Response({"company_id": pk, "excluded": data.get("excluded", False)})


@api_view(["POST"])
def reports(request, pk):
    data = validated(request, ReportInput)
    with transaction.atomic():
        lock_user(request.user)
        offer = get_object_or_404(m.Offer.objects.exclude(status="hidden"), pk=pk)
        item = m.OfferReport.objects.create(user=request.user, offer=offer, **data)
    return Response(
        model_data(
            item, ["id", "offer_id", "reason", "details", "status", "created_at"]
        ),
        status=201,
    )


@api_view(["GET"])
def alerts(request):
    return paginate(
        m.AlertEvent.objects.filter(user=request.user).order_by("-id"),
        request,
        lambda item: model_data(
            item, ["id", "offer_id", "payload", "created_at", "read_at"]
        ),
    )


@api_view(["PUT", "POST"])
def alert_read(request, pk):
    empty_validated(request)
    with transaction.atomic():
        lock_user(request.user)
        item = get_object_or_404(
            m.AlertEvent.objects.select_for_update(), user=request.user, pk=pk
        )
        if not item.read_at:
            item.read_at = timezone.now()
            item.save(update_fields=["read_at"])
    return Response({"id": item.pk, "read_at": item.read_at})


@api_view(["GET", "POST"])
def external_opportunities(request):
    if request.method == "GET":
        return paginate(
            m.ExternalOpportunity.objects.filter(user=request.user).order_by("-id"),
            request,
            lambda item: model_data(item, EXTERNAL_FIELDS),
        )
    data = validated(request, ExternalInput)
    with transaction.atomic():
        lock_user(request.user)
        item = m.ExternalOpportunity.objects.create(user=request.user, **data)
    return Response(model_data(item, EXTERNAL_FIELDS), status=202)


@api_view(["GET", "PATCH", "DELETE"])
def external_opportunity(request, pk):
    if request.method == "GET":
        return Response(
            model_data(
                get_object_or_404(m.ExternalOpportunity, user=request.user, pk=pk),
                EXTERNAL_FIELDS,
            )
        )
    data = (
        partial_validated(request, ExternalInput)
        if request.method == "PATCH"
        else empty_validated(request)
    )
    with transaction.atomic():
        lock_user(request.user)
        item = get_object_or_404(
            m.ExternalOpportunity.objects.select_for_update(), user=request.user, pk=pk
        )
        if request.method == "DELETE":
            item.delete()
            return Response(status=204)
        if "url" in data and data["url"] != item.url:
            item.status, item.error_code, item.offer_id = "pending", "", None
        for key, value in data.items():
            setattr(item, key, value)
        item.save()
    return Response(model_data(item, EXTERNAL_FIELDS))


@api_view(["GET"])
@permission_classes([AllowAny])
def coverage(request):
    from jobboard.api.catalogue import open_offers
    from jobboard.services.engine_coverage import coverage_metrics
    from jobboard.services.engine_quality import EUROPE_COUNTRIES

    # Fixed SQL identifiers; values remain bound. Expand canonical evidence countries,
    # rather than assuming a free-text legacy Location has already been geocoded.
    visible_sql, visible_params = (
        open_offers().order_by().values("pk").query.sql_with_params()
    )
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT country.code, COUNT(DISTINCT o.id)
            FROM jobboard_offer o
            JOIN jobboard_offerenrichment e ON e.offer_id = o.id
            CROSS JOIN LATERAL jsonb_array_elements_text(e.country_codes) AS country(code)
            WHERE o.id IN ({visible_sql}) AND country.code = ANY(%s)
            GROUP BY country.code ORDER BY country.code LIMIT 250
        """,
            (*visible_params, sorted(EUROPE_COUNTRIES)),
        )
        countries = [
            {"locations__country_code": code, "offers": count}
            for code, count in cursor.fetchall()
        ]
    return Response(
        {
            **coverage_metrics(open_offers()),
            "scope": "confirmed_europe_internships",
            "countries": countries,
            "domains": list(
                open_offers()
                .filter(
                    enrichment__classification="confirmed",
                    enrichment__europe_status="in_scope",
                )
                .order_by()
                .values("enrichment__domain")
                .annotate(offers=Count("id"))
                .order_by("enrichment__domain")
            ),
            "active_sources": m.SourceBoard.objects.filter(enabled=True).count(),
            "verified_sources": m.SourceBoard.objects.filter(
                enabled=True, last_success_at__isnull=False
            ).count(),
            "latest_verification": m.SourceBoard.objects.filter(
                enabled=True, last_success_at__isnull=False
            )
            .order_by("-last_success_at")
            .values_list("last_success_at", flat=True)
            .first(),
            "limitations": [
                "Coverage is not exhaustive.",
                "Counts describe monitored sources, not all internships in Europe.",
            ],
        }
    )


urlpatterns = [
    path("saved-searches/", saved_searches),
    path("saved-searches/<int:pk>/", saved_search),
    path("offers/<int:pk>/feedback/", feedback),
    path("companies/<int:pk>/preference/", company_preference),
    path("company-preferences/<int:pk>/", company_preference),
    path("offers/<int:pk>/reports/", reports),
    path("alerts/", alerts),
    path("alerts/<int:pk>/read/", alert_read),
    path("external-opportunities/", external_opportunities),
    path("external-opportunities/<int:pk>/", external_opportunity),
    path("coverage/", coverage),
]
