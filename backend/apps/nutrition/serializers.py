from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.utils import timezone
from rest_framework import serializers

from apps.core.serializers import FarmScopedModelSerializer
from apps.health.serializers import HealthRecordSerializer

from . import services
from .models import (
    FeedingRecord,
    FeedItem,
    FeedStockMovement,
    MovementKind,
    NutritionAssessment,
    Supplementation,
    WaterHygieneCheck,
)


class FeedItemSerializer(FarmScopedModelSerializer):
    is_low = serializers.BooleanField(read_only=True)
    days_left = serializers.SerializerMethodField()
    average_daily_use = serializers.SerializerMethodField()

    class Meta(FarmScopedModelSerializer.Meta):
        model = FeedItem
        fields = (
            "id",
            "name",
            "category",
            "unit",
            "reorder_level",
            "unit_cost_cents",
            "stock_quantity",
            "is_low",
            "days_left",
            "average_daily_use",
            "notes",
        )
        read_only_fields = ("id", "stock_quantity")

    def get_days_left(self, obj: FeedItem) -> int | None:
        return services.days_left(obj)

    def get_average_daily_use(self, obj: FeedItem) -> str:
        return f"{services.average_daily_use(obj):.2f}"

    def validate_name(self, value: str) -> str:
        qs = FeedItem.objects.filter(name__iexact=value.strip())
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A feed item with this name already exists.")
        return value.strip()


class StockChangeSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(
        choices=[MovementKind.PURCHASE, MovementKind.ADJUSTMENT, MovementKind.WASTE]
    )
    quantity = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        min_value=Decimal("0.01"),
        help_text="Amount bought or wasted",
    )
    counted_quantity = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        min_value=Decimal("0"),
        help_text="For a stock count: what is actually in the store",
    )
    unit_cost_cents = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    supplier = serializers.CharField(max_length=80, required=False, allow_blank=True)
    date = serializers.DateField(default=timezone.localdate)
    notes = serializers.CharField(max_length=200, required=False, allow_blank=True)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if attrs["kind"] == MovementKind.ADJUSTMENT and attrs.get("counted_quantity") is None:
            raise serializers.ValidationError(
                {"counted_quantity": ["Enter what you counted in the store."]}
            )
        if attrs["kind"] != MovementKind.ADJUSTMENT and not attrs.get("quantity"):
            raise serializers.ValidationError({"quantity": ["Enter the quantity."]})
        if attrs["date"] > timezone.localdate():
            raise serializers.ValidationError({"date": ["The date cannot be in the future."]})
        return attrs


class MovementSerializer(serializers.ModelSerializer):
    feed_item_name = serializers.CharField(source="feed_item.name", read_only=True)
    unit = serializers.CharField(source="feed_item.unit", read_only=True)
    recorded_by = serializers.SerializerMethodField()

    class Meta:
        model = FeedStockMovement
        fields = (
            "id",
            "feed_item",
            "feed_item_name",
            "unit",
            "date",
            "kind",
            "quantity",
            "unit_cost_cents",
            "total_cost_cents",
            "supplier",
            "notes",
            "recorded_by",
            "created_at",
        )
        read_only_fields = fields

    def get_recorded_by(self, obj: FeedStockMovement) -> str | None:
        return obj.created_by.full_name if obj.created_by else None


class FeedingRecordSerializer(HealthRecordSerializer):
    feed_item_name = serializers.CharField(source="feed_item.name", read_only=True)
    unit = serializers.CharField(source="feed_item.unit", read_only=True)
    location_label = serializers.CharField(source="location.name", read_only=True, default=None)

    class Meta(HealthRecordSerializer.Meta):
        model = FeedingRecord
        fields = (
            *HealthRecordSerializer.Meta.fields,
            "feed_item",
            "feed_item_name",
            "unit",
            "quantity",
            "group",
            "location",
            "location_label",
            "animals_fed",
            "responsible",
        )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        attrs = super().validate(attrs)
        item = attrs.get("feed_item") or getattr(self.instance, "feed_item", None)
        quantity = attrs.get("quantity") or getattr(self.instance, "quantity", None)
        if item is not None and quantity is not None:
            taken = (
                self.instance.quantity
                if self.instance and self.instance.feed_item_id == item.pk
                else Decimal("0")
            )
            services.check_available(item, quantity, taken)
        return attrs


class NutritionAssessmentSerializer(HealthRecordSerializer):
    class Meta(HealthRecordSerializer.Meta):
        model = NutritionAssessment
        fields = (
            *HealthRecordSerializer.Meta.fields,
            "animal",
            "group",
            "body_condition_score",
            "pasture_condition",
            "assessor",
            "findings",
            "recommendations",
            "next_assessment_date",
        )


class SupplementationSerializer(HealthRecordSerializer):
    class Meta(HealthRecordSerializer.Meta):
        model = Supplementation
        fields = (
            *HealthRecordSerializer.Meta.fields,
            "supplement",
            "feed_item",
            "quantity",
            "animal",
            "group",
            "dosage",
            "reason",
            "given_by",
        )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        attrs = super().validate(attrs)
        item = attrs.get("feed_item") or getattr(self.instance, "feed_item", None)
        quantity = attrs.get("quantity") or getattr(self.instance, "quantity", None)
        if item is not None and not quantity:
            raise serializers.ValidationError(
                {"quantity": ["Enter how much was taken from stock."]}
            )
        if item is not None and quantity:
            taken = (
                self.instance.quantity or Decimal("0")
                if self.instance and self.instance.feed_item_id == item.pk
                else Decimal("0")
            )
            services.check_available(item, quantity, taken)
        return attrs


class WaterHygieneSerializer(HealthRecordSerializer):
    score = serializers.IntegerField(read_only=True)
    location_label = serializers.CharField(source="location.name", read_only=True, default=None)

    class Meta(HealthRecordSerializer.Meta):
        model = WaterHygieneCheck
        fields = (
            *HealthRecordSerializer.Meta.fields,
            "location",
            "location_label",
            "water_source",
            "water_available",
            "water_clean",
            "troughs_clean",
            "pen_clean",
            "bedding_dry",
            "score",
            "issues",
            "actions_taken",
            "checked_by",
        )


class NutritionSummarySerializer(serializers.Serializer):
    feed_items = serializers.IntegerField()
    low_stock_items = serializers.IntegerField()
    feedings_today = serializers.IntegerField()
    feed_cost_this_month_cents = serializers.IntegerField()
    last_hygiene_score = serializers.IntegerField(allow_null=True)
