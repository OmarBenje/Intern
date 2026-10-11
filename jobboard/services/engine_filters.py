"""SQL-only date/duration/language/freshness filters with explicit unknowns."""

from datetime import timedelta

from django.db.models import (
    DateTimeField,
    DurationField,
    Exists,
    ExpressionWrapper,
    F,
    OuterRef,
    Q,
    Value,
)
from django.db.models.functions import Coalesce, Least
from django.utils import timezone
from rest_framework import serializers

from jobboard.api.serializers import StrictSerializer
from jobboard.models import OfferSource


class CatalogueFilters(StrictSerializer):
    sort = serializers.ChoiceField(choices=["relevance", "newest"], required=False)
    published_within = serializers.ChoiceField(choices=["1", "7", "30"], required=False)
    country = serializers.RegexField(r"^[A-Z]{2}$", required=False)
    start_from = serializers.DateField(required=False)
    start_to = serializers.DateField(required=False)
    duration_min = serializers.IntegerField(min_value=1, max_value=3650, required=False)
    duration_max = serializers.IntegerField(min_value=1, max_value=3650, required=False)
    duration_unit = serializers.ChoiceField(
        choices=["days", "weeks", "months"], required=False
    )
    required_language = serializers.RegexField(r"^[a-z]{2}$", required=False)
    include_unknown = serializers.ChoiceField(choices=["true", "false"], required=False)
    freshness = serializers.ChoiceField(
        choices=["fresh", "stale", "all"], required=False
    )

    def validate(self, attrs):
        if (attrs.get("duration_min") or attrs.get("duration_max")) and not attrs.get(
            "duration_unit"
        ):
            raise serializers.ValidationError(
                "duration_unit is required with a duration bound."
            )
        if attrs.get("duration_min", 0) > attrs.get("duration_max", 3650):
            raise serializers.ValidationError("Duration bounds are reversed.")
        if (
            attrs.get("start_from")
            and attrs.get("start_to")
            and attrs["start_from"] > attrs["start_to"]
        ):
            raise serializers.ValidationError("Start date bounds are reversed.")
        return attrs


def fresh_sources(now=None):
    from jobboard.services.recruiters import publication_conditions

    now = now or timezone.now()
    interval = ExpressionWrapper(
        Coalesce(F("board__engine_schedule__interval_minutes"), Value(120))
        * Value(timedelta(minutes=2)),
        output_field=DurationField(),
    )
    cadence_cutoff = ExpressionWrapper(
        Value(now) - interval, output_field=DateTimeField()
    )
    return (
        OfferSource.objects.filter(source_status="active", board__enabled=True)
        .annotate(fresh_cutoff=Least(Value(now - timedelta(hours=24)), cadence_cutoff))
        .filter(
            (~Q(board__provider="intern") & Q(last_checked_at__gte=F("fresh_cutoff")))
            | Q(
                board__provider="intern",
                **publication_conditions("offer__recruiter_job__"),
            )
        )
    )


def filter_catalogue(queryset, criteria):
    include_unknown = (
        criteria.get(
            "include_unknown",
            "true"
            if criteria.get("unknown_policy", "include") == "include"
            else "false",
        )
        == "true"
    )
    if criteria.get("published_within"):
        # Publication date, never import time; unknown dates do not mean recent.
        now = timezone.now()
        queryset = queryset.filter(
            published_at__gte=now - timedelta(days=int(criteria["published_within"])),
            published_at__lte=now,
        )
    missing_enrichment = Q(enrichment__isnull=True)
    if criteria.get("country"):
        selected = Q(enrichment__country_codes__contains=[criteria["country"]])
        if include_unknown:
            selected |= missing_enrichment | Q(enrichment__country_codes=[])
        queryset = queryset.filter(selected)
    if criteria.get("start_from") or criteria.get("start_to"):
        selected = (
            Q(enrichment__facts__has_key="start_date")
            & ~Q(enrichment__facts__start_date__value=None)
            & (
                Q(enrichment__facts__start_date__status__isnull=True)
                | ~Q(enrichment__facts__start_date__status="conflict")
            )
        )
        if criteria.get("start_from"):
            selected &= Q(
                enrichment__facts__start_date__value__gte=str(criteria["start_from"])
            )
        if criteria.get("start_to"):
            selected &= Q(
                enrichment__facts__start_date__value__lte=str(criteria["start_to"])
            )
        if include_unknown:
            selected |= (
                missing_enrichment
                | ~Q(enrichment__facts__has_key="start_date")
                | Q(enrichment__facts__start_date__value=None)
                | Q(enrichment__facts__start_date__status="conflict")
            )
        queryset = queryset.filter(selected)
    if criteria.get("duration_min") or criteria.get("duration_max"):
        requested_unit = criteria["duration_unit"]
        units = [requested_unit] if requested_unit == "months" else ["days", "weeks"]
        selected = Q(pk__in=[])
        for unit in units:
            # Interval overlap. Days/weeks convert exactly; no month approximation.
            numerator, denominator = (
                (1, 1)
                if unit == requested_unit
                else ((7, 1) if requested_unit == "weeks" else (1, 7))
            )
            branch = Q(enrichment__facts__duration__value__unit=unit)
            if criteria.get("duration_min"):
                branch &= Q(
                    enrichment__facts__duration__value__maximum__gte=(
                        criteria["duration_min"] * numerator + denominator - 1
                    )
                    // denominator
                ) | Q(enrichment__facts__duration__value__maximum=None)
            if criteria.get("duration_max"):
                branch &= Q(
                    enrichment__facts__duration__value__minimum__lte=(
                        criteria["duration_max"] * numerator
                    )
                    // denominator
                ) | Q(enrichment__facts__duration__value__minimum=None)
            selected |= branch
        if include_unknown:
            selected |= (
                missing_enrichment
                | ~Q(enrichment__facts__has_key="duration")
                | ~Q(enrichment__facts__duration__value__unit__in=units)
                | Q(enrichment__facts__duration__status="conflict")
            )
        queryset = queryset.filter(selected)
    if criteria.get("required_language"):
        selected = Q(
            enrichment__facts__required_languages__value__contains=[
                {"code": criteria["required_language"]}
            ]
        ) | Q(
            enrichment__facts__language_alternatives__value__contains=[
                {"codes": [criteria["required_language"]]}
            ]
        )
        if include_unknown:
            selected |= missing_enrichment | (
                ~Q(enrichment__facts__has_key="required_languages")
                & ~Q(enrichment__facts__has_key="language_alternatives")
            )
            selected |= Q(
                enrichment__facts__language_conflicts__value__contains=[
                    criteria["required_language"]
                ]
            ) | Q(
                enrichment__facts__language_requirements__value__contains=[
                    {"codes": [criteria["required_language"]], "modality": "unknown"}
                ]
            )
        queryset = queryset.filter(selected)
    if criteria.get("freshness") in ("fresh", "stale"):
        queryset = queryset.annotate(
            engine_is_fresh=Exists(fresh_sources().filter(offer_id=OuterRef("pk")))
        ).filter(engine_is_fresh=criteria["freshness"] == "fresh")
    return queryset
