"""Celery helpers. A task that touches farm data runs inside farm_context(farm_id)."""

from __future__ import annotations

from typing import Any

from celery import Task, shared_task

from .context import farm_context


class FarmTask(Task):
    """Base for tasks called with farm_id=...: the farm scope applies for the whole run."""

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        farm_id = kwargs.get("farm_id")
        if farm_id is None:
            return super().__call__(*args, **kwargs)
        with farm_context(farm_id):
            return super().__call__(*args, **kwargs)


@shared_task(name="core.ping")
def ping() -> str:
    """Used by the health check and smoke tests to prove the worker is consuming."""
    return "pong"
