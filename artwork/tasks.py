import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from .config import ARTWORK_STATUS_CONFIG, STAGE_ORDER
from .models import ArtworkRequest
from .services import ArtworkNotificationService

logger = logging.getLogger('artwork')


@shared_task
def check_artwork_deadlines():
    """Send reminder emails when approvers exceed stage timelines."""
    now = timezone.now()
    for stage_key in STAGE_ORDER:
        cfg = ARTWORK_STATUS_CONFIG[stage_key]
        hours = cfg.get('timeline_hours')
        if not hours:
            continue
        db_status = cfg['db_status']
        cutoff = now - timedelta(hours=hours)
        pending = ArtworkRequest.objects.filter(
            status=db_status,
            last_status_change__lte=cutoff,
        ).exclude(
            last_reminder_sent__gte=cutoff,
        )
        for artwork in pending:
            try:
                ArtworkNotificationService.send_deadline_reminder(artwork, stage_key)
                artwork.last_reminder_sent = now
                artwork.save(update_fields=['last_reminder_sent'])
            except Exception as exc:
                logger.error('Deadline reminder failed for %s: %s', artwork.artwork_no, exc)
