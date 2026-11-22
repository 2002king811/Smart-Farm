import logging
from collections.abc import Callable

from django.conf import settings
from django.db import transaction

logger = logging.getLogger(__name__)


def after_commit(fn: Callable[[], object]) -> None:
    """Run ``fn`` once the current transaction commits (immediately in tests), so background
    work such as sending messages never acts on data that was rolled back. A failure in ``fn``
    is logged and never breaks the request that scheduled it."""

    def safe() -> None:
        try:
            fn()
        except Exception:
            logger.exception("Background work scheduled after commit failed")

    if getattr(settings, "RUN_ON_COMMIT_IMMEDIATELY", False):
        safe()
    else:
        transaction.on_commit(safe)
