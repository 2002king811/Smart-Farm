from collections.abc import Callable

from django.conf import settings
from django.db import transaction


def after_commit(fn: Callable[[], object]) -> None:
    """Run ``fn`` once the current transaction commits (immediately in tests), so background
    work such as sending messages never acts on data that was rolled back."""
    if getattr(settings, "RUN_ON_COMMIT_IMMEDIATELY", False):
        fn()
    else:
        transaction.on_commit(fn)
