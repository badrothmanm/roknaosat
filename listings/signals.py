"""
listings/signals.py
===================
Django signals for the listings app.

Reverse Matching: when a Property is created or updated and is published
(visibility=منشور) and available (status=متاح), we automatically find
PropertyRequests that match this property and create/update PropertyMatch
records.
"""

import logging
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Property

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Property)
def run_reverse_matching_on_property_save(sender, instance, created, **kwargs):
    """
    After a Property is saved, run the reverse matching engine when the
    property is published and available, so that matching PropertyRequests
    get new PropertyMatch rows (or updated scores) without manual action.

    Triggered on:
      - create: when the new property is منشور and متاح
      - update: when the saved property is منشور and متاح (e.g. after
        editing price, district, property_type, etc.)

    Does not run when the property is hidden or not available (e.g. مباع),
    so we avoid linking requests to unavailable listings.
    """
    if instance.visibility != "منشور" or instance.status != "متاح":
        return
    try:
        from .services.matching import PropertyMatcher
        matcher = PropertyMatcher()
        matches = matcher.find_matching_requests(instance)
        if matches:
            logger.info(
                "[ReverseMatch] post_save Property %s (%s) → %d request(s) matched",
                instance.listing_id or instance.pk, instance.property_type, len(matches),
            )
    except Exception as exc:
        logger.exception(
            "[ReverseMatch] Failed for Property %s: %s",
            getattr(instance, "listing_id", instance.pk), exc,
        )
