from typing import Any

from django.db.models.signals import m2m_changed
from django.dispatch import receiver

from .models import FarmOwnedModel, TenancyViolation


@receiver(m2m_changed)
def guard_cross_farm_m2m(
    sender: Any, instance: Any, action: str, model: Any, pk_set: set[Any] | None, **kwargs: Any
) -> None:
    """Many-to-many links between farm-owned rows must stay inside one farm."""
    if action != "pre_add" or not pk_set:
        return
    if not (isinstance(instance, FarmOwnedModel) and issubclass(model, FarmOwnedModel)):
        return
    foreign = model.unscoped.filter(pk__in=pk_set).exclude(farm_id=instance.farm_id)  # type: ignore[attr-defined]
    if foreign.exists():
        raise TenancyViolation("Select records from this farm only.")
