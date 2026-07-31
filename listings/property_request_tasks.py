"""
Background follow-up for PropertyRequest (matching engine + optional Sheets sync).
Shared by legacy form POST and REST API to avoid duplicated threading logic.
"""
from __future__ import annotations

import logging
import threading

from django.db import close_old_connections

logger = logging.getLogger(__name__)


def schedule_property_request_follow_up(request_id: int) -> None:
    """Run matching + sheets sync in a daemon thread (non-blocking for HTTP)."""

    def _bg() -> None:
        # Each thread needs its own DB connection (SQLite-safe in tests / dev).
        close_old_connections()
        try:
            from listings.models import PropertyRequest
            from listings.services.matching import PropertyMatcher

            r = PropertyRequest.objects.get(pk=request_id)
            PropertyMatcher().match_request(r)
        except Exception as e:
            logger.exception("[PropertyRequest] Matching failed for #%s: %s", request_id, e)
        try:
            from listings.services.sheets_sync import sync_property_request_async

            sync_property_request_async(request_id)
        except Exception as e:
            logger.exception("[PropertyRequest] Sheets sync failed for #%s: %s", request_id, e)

    threading.Thread(target=_bg, daemon=True).start()
