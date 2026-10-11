"""Daily in-app events; transactional cursors and event keys prevent replay."""

from datetime import timedelta

from django.db import transaction
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from jobboard.models import AlertEvent, CompanyPreference, OfferFeedback, SavedSearch


def run_alerts(limit=100):
    from jobboard.api.catalogue import open_offers
    from jobboard.services.engine_filters import filter_catalogue
    from jobboard.services.engine_matching import evaluate_match, preselect_offers

    total = 0
    now = timezone.now()
    due = (
        SavedSearch.objects.filter(frequency="daily", user__is_active=True)
        .filter(
            Q(last_evaluated_at__isnull=True)
            | Q(last_evaluated_at__lte=now - timedelta(days=1))
        )
        .order_by("id")
    )
    from django.contrib.auth import get_user_model

    from jobboard.api.core import lock_user

    for pk, user_id in list(due.values_list("id", "user_id")[:limit]):
        with transaction.atomic():
            user = (
                get_user_model()
                .objects.select_for_update()
                .filter(pk=user_id, is_active=True)
                .first()
            )
            if not user:
                continue
            lock_user(user)
            search = (
                SavedSearch.objects.select_for_update()
                .select_related("user")
                .get(pk=pk)
            )
            if search.frequency != "daily" or (
                search.last_evaluated_at
                and search.last_evaluated_at > now - timedelta(days=1)
            ):
                continue
            if search.last_evaluated_at is None:
                search.last_evaluated_at = now
                search.save(update_fields=["last_evaluated_at"])
                continue
            qs = filter_catalogue(
                preselect_offers(open_offers(), search.criteria), search.criteria
            ).filter(
                Q(created_at__gt=search.last_evaluated_at, created_at__lte=now)
                | Q(
                    enrichment__event_at__gt=search.last_evaluated_at,
                    enrichment__event_at__lte=now,
                )
            )
            qs = qs.exclude(
                pk__in=OfferFeedback.objects.filter(user=search.user).values("offer_id")
            ).exclude(
                company_id__in=CompanyPreference.objects.filter(
                    user=search.user, excluded=True
                ).values("company_id")
            )
            from jobboard.services.engine_filters import fresh_sources

            qs = (
                qs.annotate(
                    engine_is_fresh=Exists(
                        fresh_sources(now).filter(offer_id=OuterRef("pk"))
                    )
                )
                .filter(engine_is_fresh=True)
                .distinct()
            )
            profile = getattr(search.user, "candidate_profile", None)
            for offer in qs.iterator(chunk_size=100):
                match = evaluate_match(offer, profile, search.criteria)
                if match["compatibility"] == "incompatible_explicit":
                    continue
                _, created = AlertEvent.objects.get_or_create(
                    user=search.user,
                    offer=offer,
                    event_key=f"offer:{offer.pk}:v{getattr(getattr(offer, 'enrichment', None), 'content_version', 1)}",
                    channel="in_app",
                    defaults={
                        "payload": {
                            "title": offer.title,
                            "search_id": search.pk,
                            "search_version": search.version,
                            "compatibility": match["compatibility"],
                        }
                    },
                )
                total += created
            search.last_evaluated_at = now
            search.save(update_fields=["last_evaluated_at"])
    return total
