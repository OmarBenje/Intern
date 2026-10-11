from datetime import timedelta

from django.contrib.postgres.expressions import ArraySubquery
from django.db import transaction
from django.db.models import (
    Case,
    Exists,
    F,
    IntegerField,
    OuterRef,
    Prefetch,
    Q,
    Value,
    When,
)
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from django.urls import path
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from jobboard.api import read_serializers as r
from jobboard.api import serializers as s
from jobboard.api.core import APIError, lock_user
from jobboard.api.drf import paginate
from jobboard.models import (
    CandidateProfile,
    CompanyPreference,
    CompensationBand,
    JobDomain,
    JobSubdomain,
    Location,
    Offer,
    OfferFeedback,
    OfferSource,
    Role,
    SavedOffer,
    SearchPreference,
    Skill,
)
from jobboard.models.choices import ContractType, WorkMode


def offer_queryset():
    return (
        Offer.objects.select_related("company", "role", "enrichment", "job_subdomain__domain")
        .prefetch_related(
            "locations",
            "skills",
            "compensation_bands",
            Prefetch(
                "sources",
                queryset=OfferSource.objects.filter(
                    source_status="active", board__enabled=True
                ).select_related("board", "board__engine_schedule").order_by(
                    Case(When(board__provider__in=["greenhouse", "lever", "ashby", "workday", "smartrecruiters", "personio", "recruitee", "teamtailor", "workable"], then=Value(0)), default=Value(1), output_field=IntegerField()),
                    "id",
                ),
            ),
        )
        .order_by(F("published_at").desc(nulls_last=True), "-id")
    )


def open_offers():
    """The publication boundary is mandatory, regardless of client filters."""
    from jobboard.services.engine_filters import fresh_sources
    from jobboard.services.engine_quality import published_offers

    return (
        published_offers(offer_queryset())
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now()))
        .alias(engine_is_fresh=Exists(fresh_sources().filter(offer_id=OuterRef("pk"))))
        .filter(engine_is_fresh=True)
    )


def serialize_offer(offer, detail=False, serializer=None):
    if serializer is None:
        serializer_class = r.OfferDetailSerializer if detail else r.OfferSerializer
        serializer = serializer_class()
    data = serializer.to_representation(offer)
    subdomain = offer.job_subdomain
    data["taxonomy"] = {
        "status": offer.taxonomy_status,
        "version": offer.taxonomy_version,
        "subdomain": {"slug": subdomain.slug, "name": subdomain.name,
                      "domain": {"slug": subdomain.domain.slug, "name": subdomain.domain.name}} if subdomain else None,
    }
    if detail:
        data["taxonomy"]["evidence"] = offer.taxonomy_evidence
        data["taxonomy"]["secondary_subdomains"] = list(offer.secondary_subdomains.values("slug", "name"))
    verified = [
        source.last_checked_at
        for source in offer.sources.all()
        if source.last_checked_at
    ]
    last_verified = max(verified) if verified else None
    data["last_verified_at"] = last_verified
    now = timezone.now()
    data["stale"] = not any(
        source.last_checked_at
        and source.last_checked_at
        >= now
        - timedelta(
            minutes=max(
                1440,
                2
                * getattr(
                    getattr(source.board, "engine_schedule", None),
                    "interval_minutes",
                    120,
                ),
            )
        )
        for source in offer.sources.all()
    )
    from jobboard.integrations.submission import get_adapter

    for source_data, source in zip(data["sources"], offer.sources.all()):
        available = False
        try:
            get_adapter(source).ensure_enabled()
            available = offer.status == "open"
        except APIError:
            pass
        source_data["capabilities"] = {
            "collect": source.board.enabled,
            "submit": available,
            "manual_external": True,
        }
        if not available:
            source_data["submission_mode"] = "manual_external"
    enrichment = getattr(offer, "enrichment", None)
    if enrichment:
        data["quality"] = {
            "classification": enrichment.classification,
            "europe_status": enrichment.europe_status,
            "country_codes": enrichment.country_codes,
            "domain": enrichment.domain,
            "content_version": enrichment.content_version,
        }
        if detail:
            data["facts"] = enrichment.facts
            data["content"] = enrichment.content
    if detail and not data.get("content"):
        from jobboard.services.offer_content import build_content

        data["content"], _ = build_content(offer.description)
    return data


def filtered_offers(request, *, apply_search=True):
    queryset = open_offers()
    for field, choices in [
        ("contract_type", ContractType.values),
        ("work_mode", WorkMode.values),
    ]:
        value = request.GET.get(field)
        if value:
            if value not in choices:
                raise APIError("invalid_filter", f"Invalid {field}.")
            if field == "contract_type":
                queryset = queryset.filter(**{field: value})
    for param, field in [("role", "role_id"), ("location", "locations__id"), ("company", "company_id")]:
        value = request.GET.get(param)
        if value:
            if not value.isdecimal() or len(value) > 18 or int(value) < 1:
                raise APIError("invalid_filter", f"{param} must be a positive integer.")
            queryset = queryset.filter(**{field: int(value)})
    query = request.GET.get("q", "").strip()
    if len(query) > 300:
        raise APIError("invalid_filter", "Search is limited to 300 characters.")
    from jobboard.services.engine_matching import preselect_offers

    criteria = {"q": query if apply_search else ""}
    from jobboard.api.engine import Criteria

    for key in (
        "domain",
        "classification",
        "europe_scope",
        "unknown_policy",
        "work_mode",
    ):
        if key in request.GET:
            criteria[key] = request.GET[key]
    if request.GET.get("country_codes"):
        criteria["country_codes"] = request.GET["country_codes"].split(",")
    for key in ("domains", "subdomains"):
        if request.GET.get(key):
            criteria[key] = request.GET[key].split(",")
    schema = Criteria(data=criteria)
    schema.is_valid(raise_exception=True)
    from jobboard.services.engine_filters import CatalogueFilters, filter_catalogue

    filters = CatalogueFilters(
        data={
            key: request.GET[key]
            for key in CatalogueFilters().fields
            if key in request.GET
        }
    )
    filters.is_valid(raise_exception=True)
    if "include_unknown" in request.GET:
        schema.validated_data["unknown_policy"] = (
            "include" if request.GET["include_unknown"] == "true" else "exclude"
        )
    filters.validated_data["unknown_policy"] = schema.validated_data.get(
        "unknown_policy", "include"
    )
    queryset = filter_catalogue(
        preselect_offers(queryset, schema.validated_data), filters.validated_data
    )
    # All joins above are FK/one-to-one or a unique (offer, location) pair.
    # DISTINCT would sort wide rows without removing any duplicates.
    ordering = filters.validated_data.get("sort", "relevance" if query else "newest")
    if ordering == "relevance" and query and apply_search:
        return queryset.order_by(
            "-search_rank", F("published_at").desc(nulls_last=True), "-id"
        )
    return queryset.order_by(F("published_at").desc(nulls_last=True), "-id")


@api_view(["GET"])
@permission_classes([AllowAny])
def offers(request):
    serializer = r.OfferSerializer()
    return paginate(
        list_offers(filtered_offers(request)),
        request,
        lambda offer: serialize_offer(offer, serializer=serializer),
    )


def list_offers(queryset, *, match=False):
    deferred = [
        "description",
        "search_vector",
        "search_document",
        "search_title",
        "company__description",
        "enrichment__content",
        "enrichment__semantic_hash",
        "taxonomy_evidence",
    ]
    if not match:
        deferred.append("enrichment__facts")
    return queryset.defer(*deferred)


@api_view(["GET"])
@permission_classes([AllowAny])
def offer_suggestions(request):
    from jobboard.services.catalogue_search import suggest_offers

    queryset = filtered_offers(request, apply_search=False)
    return Response({"suggestions": suggest_offers(queryset, request.GET.get("q", ""))})


@api_view(["GET"])
@permission_classes([AllowAny])
def offer_detail(request, pk):
    from jobboard.models import OfferMergeDecision

    alias = (
        OfferMergeDecision.objects.filter(duplicate_offer_id=pk, status="merged")
        .exclude(canonical_offer__status="hidden")
        .first()
    )
    target = alias.canonical_offer_id if alias else pk
    data = serialize_offer(
        get_object_or_404(
            offer_queryset()
            .exclude(status="hidden")
            .filter(
                enrichment__classification="confirmed",
                enrichment__europe_status="in_scope",
            ),
            pk=target,
        ),
        detail=True,
    )
    if alias:
        data["redirected_from_offer_id"] = pk
    return Response(data)


@api_view(["GET"])
def catalogue(request):
    # Each vocabulary has an independent page, selected with ?kind=roles|skills|locations.
    kind = request.GET.get("kind", "roles")
    models = {"roles": Role, "skills": Skill, "locations": Location}
    if kind not in models:
        raise APIError("invalid_filter", "kind must be roles, skills or locations.")
    queryset = models[kind].objects.order_by("name", "id")
    query = request.GET.get("q", "").strip()
    if len(query) > 300:
        raise APIError("invalid_filter", "Search is limited to 300 characters.")
    if query:
        queryset = queryset.filter(name__icontains=query)
    serializer = {
        "roles": r.RoleSerializer,
        "skills": r.SkillSerializer,
        "locations": r.LocationSerializer,
    }[kind]
    result = paginate(queryset, request, lambda item: serializer(item).data)
    result.data["kind"] = kind
    return result


@api_view(["GET"])
def saved_offers(request):
    return paginate(
        offer_queryset()
        .filter(saved_by__user=request.user)
        .order_by("-saved_by__created_at", "-id"),
        request,
        serialize_offer,
    )


@api_view(["PUT", "DELETE"])
def saved_offer(request, pk):
    if request.body:
        s.validated(request, s.EmptySerializer)
    with transaction.atomic():
        lock_user(request.user)
        if request.method == "PUT":
            offer = get_object_or_404(open_offers(), pk=pk)
            SavedOffer.objects.get_or_create(user=request.user, offer=offer)
        else:
            SavedOffer.objects.filter(user=request.user, offer_id=pk).delete()
    return Response({"saved": request.method == "PUT", "offer_id": pk})


@api_view(["GET"])
def recommendations(request):
    unknown_option = request.GET.get("include_unknown", "true")
    if unknown_option not in {"true", "false"}:
        raise APIError("invalid_filter", "include_unknown must be true or false.")
    include_unknown = unknown_option == "true"
    preference = (
        SearchPreference.objects.filter(profile__user=request.user)
        .prefetch_related("roles", "locations", "contracts", "work_modes")
        .annotate(
            selected_domains=ArraySubquery(JobDomain.objects.filter(searchpreference=OuterRef("pk")).values("slug")),
            selected_subdomains=ArraySubquery(JobSubdomain.objects.filter(searchpreference=OuterRef("pk")).values("slug")),
            excluded_subdomains=ArraySubquery(JobSubdomain.objects.filter(excluded_preferences=OuterRef("pk")).values("slug")),
        )
        .first()
    )
    roles, locations, contracts, modes = set(), set(), set(), set()
    if preference:
        roles = {item.pk for item in preference.roles.all()}
        locations = {item.pk for item in preference.locations.all()}
        contracts = {item.value for item in preference.contracts.all()}
        modes = {item.value for item in preference.work_modes.all()}
    domains = set(preference.selected_domains) if preference else set()
    subdomains = set(preference.selected_subdomains) if preference else set()
    excluded_subdomains = set(preference.excluded_subdomains) if preference else set()
    profile = (
        CandidateProfile.objects.filter(user=request.user)
        .prefetch_related("work_authorizations")
        .first()
    )
    skills = set(profile.skills.values_list("id", flat=True)) if profile else set()
    queryset = (
        filtered_offers(request)
        .exclude(
            pk__in=OfferFeedback.objects.filter(user=request.user).values("offer_id")
        )
        .exclude(
            company_id__in=CompanyPreference.objects.filter(
                user=request.user, excluded=True
            ).values("company_id")
        )
    )
    # Empty accepted sets mean no accepted alternatives, including unknowns.
    if excluded_subdomains:
        from jobboard.services.job_taxonomy import filter_taxonomy

        excluded = filter_taxonomy(Offer.objects.all(), {"subdomains": list(excluded_subdomains)})
        queryset = queryset.exclude(pk__in=excluded.values("pk"))
    if not preference or not contracts or not modes:
        queryset = queryset.none()
    else:
        accepted_contracts = contracts | ({"unknown"} if include_unknown else set())
        accepted_modes = modes | ({"unknown"} if include_unknown else set())
        queryset = queryset.filter(
            contract_type__in=accepted_contracts, work_mode__in=accepted_modes
        )
    has_salary_threshold = (
        preference is not None and preference.minimum_salary is not None
    )
    if has_salary_threshold:
        comparable = CompensationBand.objects.filter(
            offer_id=OuterRef("pk"),
            currency=preference.salary_currency,
            period=preference.salary_period,
            gross_net=preference.salary_gross_net,
            source__source_status="active",
            source__board__enabled=True,
        )
        # For a range, compare its maximum. For a minimum-only disclosure,
        # compare the advertised minimum. No currency/period conversion.
        sufficient = comparable.annotate(
            advertised_upper=Coalesce("maximum", "minimum")
        ).filter(advertised_upper__gte=preference.minimum_salary)
        queryset = queryset.annotate(
            salary_comparable=Exists(comparable), salary_sufficient=Exists(sufficient)
        )
        salary_filter = Q(salary_sufficient=True)
        if include_unknown:
            salary_filter |= Q(salary_comparable=False)
        queryset = queryset.filter(salary_filter)

    from jobboard.services.catalogue_recommendations import (
        RANKER_VERSION,
        rank_recommendations,
    )

    queryset = rank_recommendations(
        queryset,
        roles=roles,
        locations=locations,
        skills=skills,
        contracts=contracts,
        modes=modes,
        domains=domains,
        subdomains=subdomains,
    )
    if request.GET.get("sort") != "newest":
        ordering = ["-recommendation_score"]
        if request.GET.get("q", "").strip():
            ordering.append("-search_rank")
        queryset = queryset.order_by(
            *ordering, F("published_at").desc(nulls_last=True), "-id"
        )
    serializer = r.OfferSerializer()

    def serialize(offer):
        reasons = []
        if offer.taxonomy_status in {"classified", "broad"}:
            selected = [offer.job_subdomain] if offer.job_subdomain else []
            exact = sorted(({s.slug for s in selected} & subdomains) | set(offer.matched_subdomains))
            family = sorted(({s.domain.slug for s in selected} & domains) | set(offer.matched_domains))
            if exact:
                reasons.append({"code": "preferred_subdomain", "subdomains": exact})
            elif family:
                reasons.append({"code": "preferred_domain", "domains": family})
        if offer.role_id in roles:
            reasons.append({"code": "preferred_role", "role_id": offer.role_id})
        common_locations = sorted(
            {item.pk for item in offer.locations.all()} & locations
        )
        common_skills = sorted({item.pk for item in offer.skills.all()} & skills)
        if common_locations:
            reasons.append(
                {"code": "preferred_location", "location_ids": common_locations}
            )
        if common_skills:
            reasons.append({"code": "profile_skills", "skill_ids": common_skills})
        if offer.contract_type != "unknown" and offer.contract_type in contracts:
            reasons.append({"code": "preferred_contract", "value": offer.contract_type})
        if offer.work_mode != "unknown" and offer.work_mode in modes:
            reasons.append({"code": "preferred_work_mode", "value": offer.work_mode})
        unknown_fields = [
            field
            for field in ("contract_type", "work_mode")
            if getattr(offer, field) == "unknown"
        ]
        salary_comparison = "not_requested"
        if has_salary_threshold:
            salary_comparison = (
                "comparable" if offer.salary_comparable else "not_comparable"
            )
            if offer.salary_sufficient:
                reasons.append(
                    {
                        "code": "salary_range_meets_minimum",
                        "minimum_salary": str(preference.minimum_salary),
                        "currency": preference.salary_currency,
                        "period": preference.salary_period,
                        "gross_net": preference.salary_gross_net,
                    }
                )
            else:
                unknown_fields.append("salary")
        from jobboard.services.engine_matching import evaluate_match

        match = evaluate_match(offer, profile)
        return {
            "match": match,
            "offer": serialize_offer(offer, serializer=serializer),
            "ranking": {"score": offer.recommendation_score, "version": RANKER_VERSION},
            "reasons": reasons,
            "unknown_fields": unknown_fields,
            "salary_comparison": salary_comparison,
        }

    result = paginate(list_offers(queryset, match=True), request, serialize)
    result.data["onboarding_required"] = not preference or not contracts or not modes
    return result


urlpatterns = [
    path("offers/", offers),
    path("offers/suggestions/", offer_suggestions),
    path("offers/<int:pk>/", offer_detail),
    path("catalogue/", catalogue),
    path("saved-offers/", saved_offers),
    path("saved-offers/<int:pk>/", saved_offer),
    path("recommendations/", recommendations),
]
