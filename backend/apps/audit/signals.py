from typing import Any

from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from apps.core.models import FarmScopedModel

from . import services


def _audited(sender: Any) -> bool:
    return isinstance(sender, type) and issubclass(sender, FarmScopedModel)


@receiver(pre_save)
def capture_before(sender: Any, instance: Any, **kwargs: Any) -> None:
    if _audited(sender):
        # from_db() stored what was loaded; keep it before save() refreshes the snapshot.
        instance._prior_values = dict(instance._loaded_values or {})


@receiver(post_save)
def audit_save(sender: Any, instance: Any, created: bool, **kwargs: Any) -> None:
    if _audited(sender) and not kwargs.get("raw"):
        services.record_save(instance, created)


@receiver(post_delete)
def audit_hard_delete(sender: Any, instance: Any, **kwargs: Any) -> None:
    if _audited(sender):
        services.record(instance, services.AuditAction.DELETE, services.snapshot(instance), None)
