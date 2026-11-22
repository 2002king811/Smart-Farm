from __future__ import annotations

from typing import Any

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.accounts.models import MembershipStatus, User
from apps.core.context import current_farm_id
from apps.core.serializers import FarmScopedModelSerializer, FarmScopedRelatedField
from apps.livestock.models import Animal

from . import services
from .models import Activity, ActivityCategory, ActivityNote, ActivityStatusHistory


class CategorySerializer(FarmScopedModelSerializer):
    class Meta(FarmScopedModelSerializer.Meta):
        model = ActivityCategory
        fields = ("id", "name", "key", "colour", "icon")
        read_only_fields = ("id", "key")


@extend_schema_field(OpenApiTypes.UUID)
class MemberField(serializers.PrimaryKeyRelatedField):
    """A user who is an active member of the active farm."""

    def get_queryset(self) -> Any:
        return User.objects.filter(
            memberships__farm_id=current_farm_id(),  # type: ignore[misc]
            memberships__status=MembershipStatus.ACTIVE,
        )


class ActivitySerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True, allow_null=True)
    assigned_to = serializers.SerializerMethodField()
    animals = serializers.SerializerMethodField()
    group = serializers.SerializerMethodField()
    is_recurring = serializers.SerializerMethodField()
    series_id = serializers.UUIDField(
        source="series.id", read_only=True, allow_null=True, default=None
    )
    completed_by_name = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()
    source_label = serializers.CharField(source="get_source_display", read_only=True)
    source_record = serializers.SerializerMethodField()

    class Meta:
        model = Activity
        fields = (
            "id",
            "title",
            "category",
            "date",
            "start_time",
            "end_time",
            "all_day",
            "assigned_to",
            "animals",
            "group",
            "description",
            "priority",
            "status",
            "reminder_days",
            "recurrence_rule",
            "is_recurring",
            "series_id",
            "completed_at",
            "completed_by_name",
            "source",
            "source_label",
            "source_record",
            "template_key",
            "created_by_name",
            "created_at",
            "updated_at",
        )

    def get_assigned_to(self, obj: Activity) -> dict[str, str] | None:
        u = obj.assigned_to
        return {"id": str(u.pk), "name": u.full_name} if u else None

    def get_animals(self, obj: Activity) -> list[dict[str, str]]:
        return [
            {"id": str(a.pk), "animal_id": a.animal_id, "name": a.name} for a in obj.animals.all()
        ]

    def get_group(self, obj: Activity) -> dict[str, str] | None:
        return {"id": str(obj.group.pk), "name": obj.group.name} if obj.group else None

    def get_is_recurring(self, obj: Activity) -> bool:
        return bool(obj.recurrence_rule or obj.series_id)

    def get_completed_by_name(self, obj: Activity) -> str | None:
        return obj.completed_by.full_name if obj.completed_by else None

    def get_created_by_name(self, obj: Activity) -> str | None:
        return obj.created_by.full_name if obj.created_by else None

    def get_source_record(self, obj: Activity) -> dict[str, str] | None:
        if not obj.source_type_id:
            return None
        return {"type": obj.source_type.model, "id": obj.source_id}  # type: ignore[union-attr]


class ActivityWriteSerializer(FarmScopedModelSerializer):
    assigned_to = MemberField(required=False, allow_null=True)
    animals = FarmScopedRelatedField(many=True, queryset=Animal.objects.all(), required=False)
    repeat = serializers.ChoiceField(
        choices=[("", "Does not repeat"), *[(k, k.title()) for k in services.RULE_PRESETS]],
        required=False,
        allow_blank=True,
        write_only=True,
        help_text="Shortcut for recurrence_rule",
    )
    repeat_until = serializers.DateField(required=False, allow_null=True, write_only=True)
    scope = serializers.ChoiceField(
        choices=[("this", "This one"), ("following", "This and following")],
        required=False,
        write_only=True,
    )

    class Meta(FarmScopedModelSerializer.Meta):
        model = Activity
        fields = (
            "id",
            "title",
            "category",
            "date",
            "start_time",
            "end_time",
            "all_day",
            "assigned_to",
            "animals",
            "group",
            "description",
            "priority",
            "reminder_days",
            "recurrence_rule",
            "repeat",
            "repeat_until",
            "scope",
        )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        repeat = attrs.pop("repeat", None)
        until = attrs.pop("repeat_until", None)
        if repeat is not None:
            attrs["recurrence_rule"] = services.RULE_PRESETS.get(repeat, "")
        if "recurrence_rule" in attrs:
            rule = services.validate_rule(attrs["recurrence_rule"])
            if rule and until:
                rule = services.rule_until(rule, until)
            attrs["recurrence_rule"] = rule
        start, end = attrs.get("start_time"), attrs.get("end_time")
        if start and end and end <= start:
            raise serializers.ValidationError(
                {"end_time": ["The end time must be after the start time."]}
            )
        if start:
            attrs["all_day"] = False
        if (
            self.instance
            and self.instance.series_id
            and attrs.get("recurrence_rule")
            and attrs.get("scope") != "following"
        ):
            raise serializers.ValidationError(
                {"scope": ["Changing how it repeats applies to this and following."]}
            )
        if len(set(attrs.get("reminder_days") or [])) != len(attrs.get("reminder_days") or []):
            raise serializers.ValidationError(
                {"reminder_days": ["Each reminder must be on a different day."]}
            )
        return attrs


class ActionSerializer(serializers.Serializer):
    note = serializers.CharField(required=False, allow_blank=True, max_length=300)


class AssignSerializer(serializers.Serializer):
    assigned_to = MemberField(allow_null=True)


class NoteSerializer(serializers.ModelSerializer):
    author = serializers.SerializerMethodField()

    class Meta:
        model = ActivityNote
        fields = ("id", "text", "author", "created_at")
        read_only_fields = ("id", "author", "created_at")

    def get_author(self, obj: ActivityNote) -> str | None:
        return obj.created_by.full_name if obj.created_by else None


class HistorySerializer(serializers.ModelSerializer):
    by = serializers.SerializerMethodField()

    class Meta:
        model = ActivityStatusHistory
        fields = ("id", "from_status", "to_status", "note", "by", "created_at")

    def get_by(self, obj: ActivityStatusHistory) -> str | None:
        return obj.created_by.full_name if obj.created_by else "Smart Farm"


class TemplateSerializer(serializers.Serializer):
    key = serializers.CharField()
    name = serializers.CharField()
    description = serializers.CharField()
    count = serializers.IntegerField()
    applied = serializers.IntegerField()


class ApplyResultSerializer(serializers.Serializer):
    created = serializers.IntegerField()
    skipped = serializers.IntegerField()


class CalendarSerializer(serializers.Serializer):
    view = serializers.CharField()
    start = serializers.DateField()
    end = serializers.DateField()
    activities = ActivitySerializer(many=True)
