from typing import Any

from rest_framework import serializers

from .context import current_farm_id


class FarmScopedRelatedField(serializers.PrimaryKeyRelatedField):
    """Only accepts IDs of rows that belong to the active farm; others are "does not exist"."""

    def get_queryset(self) -> Any:
        qs = super().get_queryset()
        assert qs is not None
        farm_id = current_farm_id()
        if farm_id is None:
            return qs.none()
        if hasattr(qs.model, "farm_id") or any(f.name == "farm" for f in qs.model._meta.fields):
            return qs.filter(farm_id=farm_id)
        return qs


class FarmScopedModelSerializer(serializers.ModelSerializer):
    """ModelSerializer whose auto-generated foreign keys are limited to the active farm."""

    serializer_related_field = FarmScopedRelatedField

    class Meta:
        read_only_fields: tuple[str, ...] = (
            "id",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        )
