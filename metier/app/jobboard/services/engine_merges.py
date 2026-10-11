"""Conservative, operator-reviewed source merges; IDs and private histories remain.

Only matching job links + company + content equality can create a candidate.
Boards/requisitions with conflicting evidence remain separate. No title-only merges.
"""

from django.db import transaction
from django.utils import timezone

from jobboard.models import Offer, OfferMergeDecision, OfferSource


def propose_merges(limit=100, *, after_source_id=0):
    """Inspect at most limit sources/peers; use the source-ID cursor for later batches."""
    limit = max(1, min(limit, 1000))
    count = 0
    sources = (
        OfferSource.objects.filter(
            source_status="active", offer__status="open", pk__gt=after_source_id
        )
        .select_related("offer")
        .order_by("pk")[:limit]
    )
    for source in sources.iterator():
        peers = (
            OfferSource.objects.filter(
                source_status="active",
                offer__status="open",
                origin_url=source.origin_url,
                offer__company_id=source.offer.company_id,
                offer__title=source.offer.title,
                offer__description=source.offer.description,
                offer_id__lt=source.offer_id,
            )
            .exclude(board=source.board)
            .order_by("pk")[:limit]
        )
        for peer in peers:
            if (
                source.external_requisition_id
                and peer.external_requisition_id
                and source.external_requisition_id != peer.external_requisition_id
            ):
                continue
            _, created = OfferMergeDecision.objects.get_or_create(
                canonical_offer_id=peer.offer_id,
                duplicate_offer_id=source.offer_id,
                defaults={
                    "evidence": {
                        "method": "exact_employer_url_content",
                        "url": source.origin_url,
                    }
                },
            )
            count += int(created)
            if count >= limit:
                return count
    return count


@transaction.atomic
def merge(decision_id):
    decision = OfferMergeDecision.objects.select_for_update().get(pk=decision_id)
    if decision.status != "candidate":
        raise ValueError("merge_not_pending")
    offers = {
        offer.pk: offer
        for offer in Offer.objects.select_for_update()
        .filter(pk__in=[decision.canonical_offer_id, decision.duplicate_offer_id])
        .order_by("pk")
    }
    canonical, duplicate = (
        offers[decision.canonical_offer_id],
        offers[decision.duplicate_offer_id],
    )
    verified = decision.evidence.get("method") == "verified_job_link"
    content = decision.evidence.get("method") in {
        "content_duplicate",
        "reviewed_content_duplicate",
    }
    if (
        canonical.status != "open"
        or duplicate.status != "open"
        or (
            not (verified or content)
            and (
                canonical.company_id != duplicate.company_id
                or (canonical.title, canonical.description)
                != (duplicate.title, duplicate.description)
            )
        )
    ):
        raise ValueError("merge_content_conflict")
    # Submission composite foreign keys bind source and offer. Never rewrite a dossier.
    if duplicate.applications.exists() or duplicate.compensation_bands.exists():
        raise ValueError("merge_has_bound_history")
    if (
        OfferMergeDecision.objects.filter(
            duplicate_offer=canonical, status="merged"
        ).exists()
        or OfferMergeDecision.objects.filter(
            canonical_offer=duplicate, status="merged"
        ).exists()
    ):
        raise ValueError("merge_chain_not_supported")
    sources = list(duplicate.sources.select_for_update())
    canonical_urls = set(canonical.sources.values_list("origin_url", flat=True))
    if content:
        from jobboard.services.content_duplicates import matches, requisitions_conflict
        from jobboard.services.targeted_merges import ATS, compatible, fingerprint

        list(canonical.sources.select_for_update())
        if (
            not compatible(canonical, duplicate)
            or canonical.company_id != duplicate.company_id
            or requisitions_conflict(canonical, duplicate)
            or (
                decision.evidence["method"] == "content_duplicate"
                and not matches(canonical, duplicate)
            )
            or fingerprint(canonical) != decision.evidence.get("canonical_fingerprint")
            or fingerprint(duplicate) != decision.evidence.get("duplicate_fingerprint")
        ):
            raise ValueError("merge_identity_conflict")
        decision.evidence["preferred_board_ids"] = sorted(
            {s.board_id for s in canonical.sources.all() if s.board.provider in ATS}
        )
    elif verified:
        from jobboard.services.targeted_merges import ATS, fingerprint, validate_pair

        list(canonical.sources.select_for_update())
        if (
            not validate_pair(canonical, duplicate)
            or fingerprint(canonical) != decision.evidence.get("canonical_fingerprint")
            or fingerprint(duplicate) != decision.evidence.get("duplicate_fingerprint")
        ):
            raise ValueError("merge_identity_conflict")
        decision.evidence["preferred_board_ids"] = list(
            canonical.sources.filter(board__provider__in=ATS).values_list(
                "board_id", flat=True
            )
        )
    elif decision.evidence.get("method") == "exact_employer_link_content":
        canonical_sources = list(canonical.sources.select_for_update())
        links = set().union(*(source_links(item) for item in canonical_sources))
        requisitions = {
            item.external_requisition_id
            for item in sources + canonical_sources
            if item.external_requisition_id
        }
        if (
            merge_signature(canonical) != merge_signature(duplicate)
            or len(requisitions) > 1
            or not sources
            or any(not (source_links(item) & links) for item in sources)
        ):
            raise ValueError("merge_identity_conflict")
    elif not sources or any(
        source.origin_url not in canonical_urls for source in sources
    ):
        raise ValueError("merge_identity_conflict")
    decision.evidence = {
        **decision.evidence,
        "source_ids": [source.pk for source in sources],
        "previous_status": duplicate.status,
    }
    OfferSource.objects.filter(pk__in=decision.evidence["source_ids"]).update(
        offer=canonical
    )
    duplicate.status = "hidden"
    duplicate.save(update_fields=["status", "updated_at"])
    decision.status, decision.resolved_at = "merged", timezone.now()
    decision.save(update_fields=["evidence", "status", "resolved_at"])
    return decision


@transaction.atomic
def reverse_merge(decision_id):
    decision = OfferMergeDecision.objects.select_for_update().get(pk=decision_id)
    if decision.status != "merged":
        raise ValueError("merge_not_active")
    list(
        Offer.objects.select_for_update()
        .filter(pk__in=[decision.canonical_offer_id, decision.duplicate_offer_id])
        .order_by("pk")
    )
    source_ids = decision.evidence["source_ids"]
    sources = list(OfferSource.objects.select_for_update().filter(pk__in=source_ids))
    if any(
        source.offer_id != decision.canonical_offer_id
        or source.applications.exists()
        or source.compensation_bands.exists()
        for source in sources
    ):
        raise ValueError("merge_has_new_bound_history")
    OfferSource.objects.filter(pk__in=source_ids).update(
        offer_id=decision.duplicate_offer_id
    )
    Offer.objects.filter(pk=decision.duplicate_offer_id).update(
        status=decision.evidence["previous_status"]
    )
    decision.status, decision.resolved_at = "reversed", timezone.now()
    decision.save(update_fields=["status", "resolved_at"])
    return decision


def canonical_job_url(value):
    """Remove only known tracking keys, retaining job IDs and all unknown parameters."""
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

    try:
        url = urlsplit(value)
        if url.scheme != "https" or not url.hostname or url.username or url.password:
            return None
        query = [
            (k, v)
            for k, v in parse_qsl(url.query, keep_blank_values=True)
            if not k.lower().startswith("utm_") and k.lower() not in {"gclid", "fbclid"}
        ]
        path = url.path.rstrip("/")
        if path.lower() in ("", "/jobs", "/careers", "/apply") and not query:
            return None
        return urlunsplit(
            ("https", url.netloc.lower(), path, urlencode(query), url.fragment)
        )
    except (TypeError, ValueError):
        return None


def source_links(source):
    return {
        link
        for value in (source.origin_url, source.apply_url)
        if (link := canonical_job_url(value))
    }


def merge_signature(offer):
    return (
        offer.company_id,
        offer.title,
        offer.description,
        offer.contract_type,
        offer.work_mode,
        offer.expires_at,
        tuple(sorted(offer.locations.values_list("pk", flat=True))),
    )


def propose_link_merges():
    """Scan the published catalogue; exact full content + locations + job link only."""
    from collections import defaultdict

    from jobboard.api.catalogue import open_offers
    from jobboard.services.engine_filters import fresh_sources

    index = defaultdict(list)
    created = 0
    visible = open_offers().order_by("pk").prefetch_related("locations")
    fresh = set(fresh_sources().values_list("pk", flat=True))
    for offer in visible.prefetch_related("sources").iterator(chunk_size=200):
        if len(offer.description.strip()) < 100:
            continue
        signature = merge_signature(offer)
        sources = [s for s in offer.sources.all() if s.pk in fresh]
        for source in sources:
            for link in sorted(source_links(source)):
                key = (signature, link)
                for peer, peer_source in index[key]:
                    if peer.pk == offer.pk or peer_source.board_id == source.board_id:
                        continue
                    if (
                        peer_source.external_requisition_id
                        and source.external_requisition_id
                        and peer_source.external_requisition_id
                        != source.external_requisition_id
                    ):
                        continue
                    _, added = OfferMergeDecision.objects.get_or_create(
                        canonical_offer=peer,
                        duplicate_offer=offer,
                        defaults={
                            "evidence": {
                                "method": "exact_employer_link_content",
                                "url": link,
                            }
                        },
                    )
                    created += int(added)
                    break
                index[key].append((offer, source))
    return created


def preferred_content_board(offer, board):
    return OfferMergeDecision.objects.filter(
        canonical_offer=offer,
        status="merged",
        evidence__method__in=[
            "verified_job_link",
            "content_duplicate",
            "reviewed_content_duplicate",
        ],
        evidence__preferred_board_ids__contains=[board.pk],
    ).exists()
