"""Base models for the tenancy layer.

Every farm-owned table extends ``FarmScopedModel``. Its default manager (``objects``):

* hides soft-deleted rows, and
* when a farm context is active (any API request, or a task run inside ``farm_context``),
  adds ``WHERE farm_id = <active farm>`` to every query automatically.

Saving enforces the other half: a row can only be written for the active farm, and every
foreign key / many-to-many link to another farm-owned row must point inside the same farm.
``unscoped`` is the escape hatch for platform code (Super Admin console, migrations, jobs that
loop over farms); it must never be used in a request handler.
"""

from __future__ import annotations

import uuid
from typing import Any, ClassVar

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from .context import current_farm_id, get_context


class TenancyViolation(ValidationError):
    """Raised when code tries to read or write across farms."""


class FarmScopedQuerySet(models.QuerySet):
    def for_farm(self, farm: Any) -> FarmScopedQuerySet:
        farm_id = getattr(farm, "pk", farm)
        return self.filter(farm_id=farm_id)

    def alive(self) -> FarmScopedQuerySet:
        if _has_soft_delete(self.model):
            return self.filter(deleted_at__isnull=True)
        return self

    def deleted(self) -> FarmScopedQuerySet:
        return self.filter(deleted_at__isnull=False)

    def delete(self) -> tuple[int, dict[str, int]]:  # type: ignore[override]
        """Bulk delete is a soft delete, one row at a time so each delete is audited."""
        if not _has_soft_delete(self.model):
            return super().delete()
        count = 0
        for obj in self:
            obj.delete()  # type: ignore[attr-defined]
            count += 1
        return count, {self.model._meta.label: count}

    def hard_delete(self) -> tuple[int, dict[str, int]]:
        return super().delete()


class FarmScopedManager(models.Manager.from_queryset(FarmScopedQuerySet)):  # type: ignore[misc]
    """Default manager: alive rows of the active farm only."""

    def get_queryset(self) -> FarmScopedQuerySet:
        qs = super().get_queryset().alive()
        farm_id = current_farm_id()
        if farm_id is not None:
            qs = qs.filter(farm_id=farm_id)
        return qs


class UnscopedManager(models.Manager.from_queryset(FarmScopedQuerySet)):  # type: ignore[misc]
    """Every row of every farm, deleted included. Platform code only."""


def _has_soft_delete(model: type[models.Model]) -> bool:
    return any(f.name == "deleted_at" for f in model._meta.concrete_fields)


class FarmOwnedModel(models.Model):
    """Smallest tenancy unit: a farm FK plus the scoped managers and write guards."""

    farm = models.ForeignKey(
        "accounts.Farm", on_delete=models.CASCADE, related_name="+", db_index=True, editable=False
    )

    objects: ClassVar[FarmScopedManager] = FarmScopedManager()
    unscoped: ClassVar[UnscopedManager] = UnscopedManager()

    class Meta:
        abstract = True
        default_manager_name = "objects"
        base_manager_name = "unscoped"

    # Snapshot of the values loaded from the database, used by the audit log for before/after.
    _loaded_values: dict[str, Any] | None = None

    @classmethod
    def from_db(  # type: ignore[override]
        cls, db: str | None, field_names: Any, values: Any, **kwargs: Any
    ) -> FarmOwnedModel:
        instance = super().from_db(db, field_names, values, **kwargs)
        instance._loaded_values = dict(zip(field_names, values, strict=False))
        return instance

    def save(self, *args: Any, **kwargs: Any) -> None:
        self._assign_and_check_farm()
        self.check_tenant_relations()
        super().save(*args, **kwargs)
        self._loaded_values = {
            f.attname: getattr(self, f.attname) for f in self._meta.concrete_fields
        }

    def _assign_and_check_farm(self) -> None:
        active = current_farm_id()
        if self.farm_id is None:  # type: ignore[attr-defined]
            if active is None:
                raise TenancyViolation(
                    f"{type(self).__name__} saved without a farm or farm context"
                )
            self.farm_id = active  # type: ignore[attr-defined]
        elif active is not None and self.farm_id != active:  # type: ignore[attr-defined]
            raise TenancyViolation(f"Cannot write {type(self).__name__} for another farm")
        if self._loaded_values and self._loaded_values.get("farm_id") not in (None, self.farm_id):  # type: ignore[attr-defined]
            raise TenancyViolation("A record cannot be moved to another farm")

    def check_tenant_relations(self) -> None:
        """Every FK to another farm-owned model must stay inside this farm."""
        for field in self._meta.concrete_fields:
            if not field.is_relation or field.name == "farm":
                continue
            related_model = field.related_model
            if not (isinstance(related_model, type) and issubclass(related_model, FarmOwnedModel)):
                continue
            value = getattr(self, field.attname)
            if value is None:
                continue
            cached = field.get_cached_value(self, default=None)  # type: ignore[attr-defined]
            related_farm = (
                cached.farm_id
                if cached is not None
                else related_model.unscoped.filter(pk=value)
                .values_list("farm_id", flat=True)
                .first()
            )
            if related_farm != self.farm_id:  # type: ignore[attr-defined]
                raise TenancyViolation({field.name: ["Select a record from this farm."]})


class FarmScopedModel(FarmOwnedModel):
    """Base for every farm-owned record: UUID id, timestamps, who-did-it and soft delete."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)

    # Field changes on these are logged as "status_change" in the audit log.
    AUDIT_STATUS_FIELDS: ClassVar[tuple[str, ...]] = ("status", "health_status")

    class Meta(FarmOwnedModel.Meta):
        abstract = True
        ordering = ("-created_at",)

    def save(self, *args: Any, **kwargs: Any) -> None:
        user_id = get_context().user_id
        if user_id is not None:
            if self._state.adding and self.created_by_id is None:  # type: ignore[attr-defined]
                self.created_by_id = user_id  # type: ignore[attr-defined]
            self.updated_by_id = user_id  # type: ignore[attr-defined]
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:  # type: ignore[override]
        """Soft delete: the row stays for history and reports; ``objects`` stops returning it."""
        if self.deleted_at is None:
            self.deleted_at = timezone.now()
            self.save(update_fields=["deleted_at", "updated_at", "updated_by"])
        return 1, {self._meta.label: 1}

    def hard_delete(self) -> tuple[int, dict[str, int]]:
        return super().delete()

    def restore(self) -> None:
        self.deleted_at = None
        self.save(update_fields=["deleted_at", "updated_at", "updated_by"])
