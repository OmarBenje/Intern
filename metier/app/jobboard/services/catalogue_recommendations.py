"""Rank confirmed preferences in SQL before pagination, independently of eligibility."""

from django.contrib.postgres.expressions import ArraySubquery
from django.db.models import (
    Case,
    Count,
    Exists,
    IntegerField,
    OuterRef,
    Subquery,
    Value,
    When,
)
from django.db.models.functions import Coalesce, Least

from jobboard.models import OfferLocation, OfferSkill

RANKER_VERSION = "preferences-taxonomy-2"
ROLE_WEIGHT, LOCATION_WEIGHT, SKILL_WEIGHT = 12, 8, 4
CONTRACT_WEIGHT, MODE_WEIGHT, SKILL_CAP = 2, 2, 3


def rank_recommendations(
    queryset, *, roles, locations, skills, contracts, modes, domains=(), subdomains=()
):
    from jobboard.models import Offer

    secondary = Offer.secondary_subdomains.through.objects.filter(
        offer_id=OuterRef("pk")
    )
    queryset = queryset.alias(
        preferred_subdomain_secondary=Exists(
            secondary.filter(jobsubdomain__slug__in=subdomains)
        ),
        preferred_domain_secondary=Exists(
            secondary.filter(jobsubdomain__domain__slug__in=domains)
        ),
    )
    queryset = queryset.annotate(
        matched_subdomains=ArraySubquery(
            secondary.filter(jobsubdomain__slug__in=subdomains).values(
                "jobsubdomain__slug"
            )
        ),
        matched_domains=ArraySubquery(
            secondary.filter(jobsubdomain__domain__slug__in=domains)
            .order_by()
            .values("jobsubdomain__domain__slug")
            .distinct()
        ),
    )
    location_match = Exists(
        OfferLocation.objects.filter(offer_id=OuterRef("pk"), location_id__in=locations)
    )
    skill_count = (
        OfferSkill.objects.filter(offer_id=OuterRef("pk"), skill_id__in=skills)
        .order_by()
        .values("offer_id")
        .annotate(total=Count("pk"))
        .values("total")
    )
    queryset = queryset.annotate(
        recommendation_score=Case(
            When(role_id__in=roles, then=Value(ROLE_WEIGHT)),
            default=Value(0),
            output_field=IntegerField(),
        )
        + Case(
            When(
                taxonomy_status__in=["classified", "broad"],
                job_subdomain__slug__in=subdomains,
                then=Value(16),
            ),
            When(
                taxonomy_status__in=["classified", "broad"],
                preferred_subdomain_secondary=True,
                then=Value(16),
            ),
            When(
                taxonomy_status__in=["classified", "broad"],
                job_subdomain__domain__slug__in=domains,
                then=Value(8),
            ),
            When(
                taxonomy_status__in=["classified", "broad"],
                preferred_domain_secondary=True,
                then=Value(8),
            ),
            default=Value(0),
            output_field=IntegerField(),
        )
        + Case(
            When(location_match, then=Value(LOCATION_WEIGHT)),
            default=Value(0),
            output_field=IntegerField(),
        )
        + SKILL_WEIGHT
        * Least(
            Coalesce(Subquery(skill_count, output_field=IntegerField()), Value(0)),
            Value(SKILL_CAP),
        )
        + Case(
            When(
                contract_type__in=contracts - {"unknown"}, then=Value(CONTRACT_WEIGHT)
            ),
            default=Value(0),
            output_field=IntegerField(),
        )
        + Case(
            When(work_mode__in=modes - {"unknown"}, then=Value(MODE_WEIGHT)),
            default=Value(0),
            output_field=IntegerField(),
        )
    )
    return queryset
