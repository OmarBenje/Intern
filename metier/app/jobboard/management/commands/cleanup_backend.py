from datetime import timedelta

from django.contrib.sessions.models import Session
from django.core.management.base import BaseCommand
from django.utils import timezone

from jobboard.models import OfferSource, RequestThrottle


class Command(BaseCommand):
    help = 'Remove expired sessions/counters and source payloads after their retention period.'

    def handle(self, *args, **options):
        now = timezone.now()
        sessions, _ = Session.objects.filter(expire_date__lt=now).delete()
        counters, _ = RequestThrottle.objects.filter(expires_at__lt=now - timedelta(days=1)).delete()
        payloads = OfferSource.objects.filter(raw_expires_at__lte=now).exclude(raw_payload={}).update(raw_payload={})
        self.stdout.write(f'sessions={sessions} counters={counters} payloads={payloads}')
