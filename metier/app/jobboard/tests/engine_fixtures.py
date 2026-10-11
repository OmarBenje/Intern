"""Explicit evidence fixtures for tests that exercise published internships."""

from django.utils import timezone

from jobboard import models as m


def publishable(offer):
    m.OfferEnrichment.objects.get_or_create(
        offer=offer,
        defaults={
            "classification": "confirmed",
            "europe_status": "in_scope",
            "country_codes": ["FR"],
        },
    )
    if not offer.sources.exists():
        board, _ = m.SourceBoard.objects.get_or_create(
            provider="greenhouse",
            instance="global",
            board_key="published-test",
            defaults={"company": offer.company},
        )
        m.OfferSource.objects.create(
            offer=offer,
            board=board,
            external_id=str(offer.pk),
            origin_url="https://example.com/job",
            apply_url="https://example.com/job",
            content_hash="a" * 64,
            last_checked_at=timezone.now(),
        )
    else:
        offer.sources.filter(last_checked_at__isnull=True).update(
            last_checked_at=timezone.now()
        )
    return offer
