"""Public shared vocabulary and counts respecting the catalogue boundary."""

from collections import defaultdict

from django.urls import path
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from jobboard.models import JobDomain, Offer
from jobboard.services.job_taxonomy import CLASSIFIED, VERSION


@api_view(["GET"])
@permission_classes([AllowAny])
def taxonomy(request):
    from .catalogue import filtered_offers

    # Remove only this facet's selections: other applied filters (including q,
    # country, duration, freshness) still determine available options.
    params = request.query_params.copy()
    for key in ("domain", "domains", "subdomains", "page", "page_size"):
        params.pop(key, None)
    queryset = (
        filtered_offers(request, params=params)
        .order_by()
        .filter(taxonomy_status__in=CLASSIFIED)
    )
    # UNION deduplicates secondary overlap for both leaves and parent totals.
    primary = queryset.exclude(job_subdomain__isnull=True).values_list(
        "pk", "job_subdomain_id", "job_subdomain__domain_id"
    )
    links = Offer.secondary_subdomains.through.objects.filter(
        offer_id__in=queryset.values("pk")
    )
    secondary = links.values_list(
        "offer_id", "jobsubdomain_id", "jobsubdomain__domain_id"
    )
    sub_counts, domain_members = defaultdict(set), defaultdict(set)
    for offer_id, sub_id, domain_id in primary.union(secondary):
        sub_counts[sub_id].add(offer_id)
        domain_members[domain_id].add(offer_id)
    domains = []
    for domain in JobDomain.objects.prefetch_related("subdomains"):
        domains.append(
            {
                "slug": domain.slug,
                "name": domain.name,
                "count": len(domain_members[domain.pk]),
                "subdomains": [
                    {
                        "slug": sub.slug,
                        "name": sub.name,
                        "aliases": sub.aliases,
                        "generalist": sub.generalist,
                        "count": len(sub_counts[sub.pk]),
                    }
                    for sub in domain.subdomains.all()
                ],
            }
        )
    return Response({"version": VERSION, "domains": domains})


urlpatterns = [path("taxonomy/", taxonomy)]
