"""Writes audit entries. Called automatically for every FarmScopedModel save/delete."""

from __future__ import annotations

import json
from typing import Any

from django.contrib.contenttypes.models import ContentType
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models

from apps.core.context import get_context

from .models import AuditAction, AuditLog

# Never copied into the audit log.
REDACTED_FIELDS = {"password", "token_hash", "code_hash"}
IGNORED_FIELDS = {"updated_at", "updated_by_id"}


def _jsonable(value: Any) -> Any:
    return json.loads(json.dumps(value, cls=DjangoJSONEncoder))


def snapshot(instance: models.Model) -> dict[str, Any]:
    data = {}
    for field in instance._meta.concrete_fields:
        if field.attname in REDACTED_FIELDS:
            continue
        value = getattr(instance, field.attname)
        if isinstance(value, models.fields.files.FieldFile):
            value = value.name or None
        data[field.attname] = value
    return _jsonable(data)


def record(
    instance: models.Model,
    action: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    changed: list[str] | None = None,
    farm_id: Any = None,
) -> AuditLog:
    ctx = get_context()
    return AuditLog.objects.create(
        farm_id=farm_id or instance.farm_id,  # type: ignore[attr-defined]
        user_id=ctx.user_id,
        action=action,
        content_type=ContentType.objects.get_for_model(type(instance)),
        object_id=str(instance.pk),
        object_repr=str(instance)[:200],
        changed_fields=changed or [],
        before=before,
        after=after,
        ip=ctx.ip,
        request_id=ctx.request_id or "",
    )


def record_save(instance: Any, created: bool) -> AuditLog | None:
    after = snapshot(instance)
    if created:
        return record(instance, AuditAction.CREATE, None, after, sorted(after))

    loaded = instance._prior_values or {}
    before = _jsonable({k: v for k, v in loaded.items() if k not in REDACTED_FIELDS})
    changed = sorted(
        k for k in after if k not in IGNORED_FIELDS and k in before and before[k] != after[k]
    )
    if not changed:
        return None

    if "deleted_at" in changed:
        action = AuditAction.DELETE if after["deleted_at"] else AuditAction.RESTORE
    elif any(f in changed for f in getattr(instance, "AUDIT_STATUS_FIELDS", ())):
        action = AuditAction.STATUS_CHANGE
    else:
        action = AuditAction.UPDATE
    return record(
        instance,
        action,
        {k: before[k] for k in changed},
        {k: after[k] for k in changed},
        changed,
    )


def record_event(
    farm_id: Any,
    instance: models.Model,
    action: str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> AuditLog:
    """Audit a change to a model that is not a FarmScopedModel (farm settings, memberships,
    invitations). ``before``/``after`` hold only the fields that changed."""
    before = _jsonable(before) if before is not None else None
    after = _jsonable(after) if after is not None else None
    changed = sorted(set(before or {}) | set(after or {}))
    return record(instance, action, before, after, changed, farm_id=farm_id)


def diff(instance: models.Model, old: dict[str, Any], fields: list[str]) -> tuple[dict, dict]:
    """(before, after) for the given fields that changed since ``old`` was taken."""
    before, after = {}, {}
    for f in fields:
        new = getattr(instance, f)
        if old.get(f) != new:
            before[f], after[f] = old.get(f), new
    return before, after
