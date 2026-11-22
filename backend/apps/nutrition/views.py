from __future__ import annotations

from typing import Any

from django.db import transaction
from django.db.models import QuerySet, Sum
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from apps.calendar.services import sync_linked_activity
from apps.core.views import FarmContextMixin, FarmScopedAPIView, FarmScopedViewSet
from apps.health.views import filterset_for

from . import serializers as s
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


class FeedItemViewSet(FarmScopedViewSet):
    model = FeedItem
    serializer_class = s.FeedItemSerializer
    permission_module = "nutrition"
    pagination_class = None
    filterset_fields = ("category",)
    search_fields = ("name",)
    ordering = ("name",)
    action_permissions = {
        "create": "manage",
        "update": "manage",
        "partial_update": "manage",
        "destroy": "manage",
        "stock": "manage",
    }

    @extend_schema(request=s.StockChangeSerializer, responses=s.FeedItemSerializer)
    @action(detail=True, methods=["post"])
    def stock(self, request: Request, pk: str | None = None) -> Response:
        """Stock in (purchase), a stock count (adjustment) or spoiled feed (waste)."""
        item = self.get_object()
        body = s.StockChangeSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        d = body.validated_data
        if d["kind"] == MovementKind.ADJUSTMENT:
            quantity = d["counted_quantity"] - item.stock_quantity
        elif d["kind"] == MovementKind.WASTE:
            services.check_available(item, d["quantity"])
            quantity = -d["quantity"]
        else:
            quantity = d["quantity"]
        services.add_movement(
            item,
            d["kind"],
            quantity,
            request.user,
            date=d["date"],
            unit_cost_cents=d.get("unit_cost_cents"),
            supplier=d.get("supplier", ""),
            notes=d.get("notes", ""),
        )
        item.refresh_from_db()
        return Response(s.FeedItemSerializer(item).data)


class FeedStockViewSet(
    FarmContextMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """Every stock movement: purchases, feeding, counts and waste."""

    model = FeedStockMovement
    serializer_class = s.MovementSerializer
    permission_module = "nutrition"
    filterset_class = filterset_for(FeedStockMovement, ("feed_item", "kind"))
    ordering = ("-date", "-created_at")

    def get_queryset(self) -> QuerySet:
        return self.farm_queryset().select_related("feed_item", "created_by")


class FeedingRecordViewSet(FarmScopedViewSet):
    """Attendants record feeding; each record takes its quantity from stock."""

    model = FeedingRecord
    serializer_class = s.FeedingRecordSerializer
    permission_module = "nutrition"
    filterset_class = filterset_for(FeedingRecord, ("feed_item", "group", "location"))
    search_fields = ("feed_item__name", "responsible", "notes")
    ordering = ("-date", "-created_at")
    action_permissions = {"create": "record_feeding"}

    def get_queryset(self) -> QuerySet:
        return super().get_queryset().select_related("feed_item", "group", "location", "created_by")

    @transaction.atomic
    def perform_create(self, serializer: Any) -> None:
        super().perform_create(serializer)
        r = serializer.instance
        services.save_usage(r, r.feed_item, r.quantity, self.request.user)

    @transaction.atomic
    def perform_update(self, serializer: Any) -> None:
        super().perform_update(serializer)
        r = serializer.instance
        services.save_usage(r, r.feed_item, r.quantity, self.request.user)

    @transaction.atomic
    def perform_destroy(self, instance: Any) -> None:
        services.remove_usage(instance)
        instance.delete()


class NutritionAssessmentViewSet(FarmScopedViewSet):
    model = NutritionAssessment
    serializer_class = s.NutritionAssessmentSerializer
    permission_module = "nutrition"
    filterset_class = filterset_for(NutritionAssessment, ("animal", "group"))
    search_fields = ("findings", "assessor", "animal__animal_id")
    ordering = ("-date", "-created_at")

    def get_queryset(self) -> QuerySet:
        return super().get_queryset().select_related("animal", "group", "created_by")

    def _sync(self, record: NutritionAssessment) -> None:
        subject = (
            record.animal.animal_id
            if record.animal
            else (record.group.name if record.group else "herd")
        )
        sync_linked_activity(
            record,
            f"Nutrition assessment – {subject}",
            [record.animal] if record.animal else None,
            record.group,
        )

    @transaction.atomic
    def perform_create(self, serializer: Any) -> None:
        super().perform_create(serializer)
        self._sync(serializer.instance)

    @transaction.atomic
    def perform_update(self, serializer: Any) -> None:
        super().perform_update(serializer)
        self._sync(serializer.instance)

    @transaction.atomic
    def perform_destroy(self, instance: Any) -> None:
        instance.delete()
        self._sync(instance)


class SupplementationViewSet(FarmScopedViewSet):
    model = Supplementation
    serializer_class = s.SupplementationSerializer
    permission_module = "nutrition"
    filterset_class = filterset_for(Supplementation, ("animal", "group", "feed_item"))
    search_fields = ("supplement", "reason", "animal__animal_id")
    ordering = ("-date", "-created_at")

    def get_queryset(self) -> QuerySet:
        return super().get_queryset().select_related("animal", "group", "feed_item", "created_by")

    @transaction.atomic
    def perform_create(self, serializer: Any) -> None:
        super().perform_create(serializer)
        r = serializer.instance
        services.save_usage(r, r.feed_item, r.quantity, self.request.user)

    @transaction.atomic
    def perform_update(self, serializer: Any) -> None:
        super().perform_update(serializer)
        r = serializer.instance
        services.save_usage(r, r.feed_item, r.quantity, self.request.user)

    @transaction.atomic
    def perform_destroy(self, instance: Any) -> None:
        services.remove_usage(instance)
        instance.delete()


class WaterHygieneViewSet(FarmScopedViewSet):
    model = WaterHygieneCheck
    serializer_class = s.WaterHygieneSerializer
    permission_module = "nutrition"
    filterset_class = filterset_for(WaterHygieneCheck, ("location",))
    search_fields = ("issues", "checked_by", "water_source")
    ordering = ("-date", "-created_at")

    def get_queryset(self) -> QuerySet:
        return super().get_queryset().select_related("location", "created_by")


class NutritionSummaryView(FarmScopedAPIView):
    permission_module = "nutrition"

    @extend_schema(responses=s.NutritionSummarySerializer)
    def get(self, request: Request) -> Response:
        today = timezone.localdate()
        items = list(FeedItem.objects.all())
        cost = (
            FeedStockMovement.objects.filter(
                kind=MovementKind.PURCHASE, date__year=today.year, date__month=today.month
            ).aggregate(c=Sum("total_cost_cents"))["c"]
            or 0
        )
        last = WaterHygieneCheck.objects.order_by("-date", "-created_at").first()
        return Response(
            {
                "feed_items": len(items),
                "low_stock_items": sum(1 for i in items if i.is_low),
                "feedings_today": FeedingRecord.objects.filter(date=today).count(),
                "feed_cost_this_month_cents": cost,
                "last_hygiene_score": last.score if last else None,
            }
        )
