"""Domain events. Code emits an event once; phase 6 fans it out to in-app, WhatsApp, SMS and
email for each recipient. Until then events are only logged, so nothing waits on providers."""

import logging
from typing import Any

from django.dispatch import Signal

logger = logging.getLogger("smartfarm.events")

# Receivers get: event_type (str), farm_id, and the payload keyword arguments.
domain_event = Signal()


def emit(event_type: str, farm_id: Any, **payload: Any) -> None:
    logger.info("event %s farm=%s %s", event_type, farm_id, payload)
    domain_event.send(sender=None, event_type=event_type, farm_id=farm_id, **payload)
