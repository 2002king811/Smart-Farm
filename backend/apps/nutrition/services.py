"""Feed stock rules: movements keep each item's stock in step, feeding deducts it, low stock
raises an alert once when it crosses the reorder level, and "days left" uses the last 14 days."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import timedelta
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.livestock.models import Animal
from apps.livestock.services import TIMELINE_SOURCES, TimelineEvent, _as_datetime
from apps.notifications.events import emit

from .models import (
    FeedingRecord,
    FeedItem,
    FeedStockMovement,
    MovementKind,
    NutritionAssessment,
    Supplementation,
)

USAGE_WINDOW_DAYS = 14

DEFAULT_FEED_ITEMS = [
    # name, category, unit, reorder level
    ("Rhodes grass hay", "forage", "bale", Decimal("10")),
    ("Dairy meal", "concentrate", "kg", Decimal("50")),
    ("Maize germ", "concentrate", "kg", Decimal("50")),
    ("Mineral lick", "mineral", "block", Decimal("2")),
]


def seed_feed_items(farm: Any) -> None:
    for name, cat, unit, reorder in DEFAULT_FEED_ITEMS:
        FeedItem.unscoped.get_or_create(
            farm=farm,
            name=name,
            deleted_at=None,
            defaults={"category": cat, "unit": unit, "reorder_level": reorder},
        )


@transaction.atomic
def recompute_stock(item: FeedItem) -> FeedItem:
    item = FeedItem.objects.select_for_update().get(pk=item.pk)
    was_low = item.is_low
    total = FeedStockMovement.objects.filter(feed_item=item).aggregate(s=Sum("quantity"))[
        "s"
    ] or Decimal("0")
    item.stock_quantity = total
    item.save(update_fields=["stock_quantity", "updated_at", "updated_by"])
    if item.is_low and not was_low:
        emit(
            "feed.low_stock",
            item.farm_id,
            feed_item_id=str(item.pk),
            title=f"Low stock: {item.name}",
            message=f"{item.name}: {item.stock_quantity} {item.unit} left (reorder level {item.reorder_level}).",
        )
    return item


def average_daily_use(item: FeedItem) -> Decimal:
    since = timezone.localdate() - timedelta(days=USAGE_WINDOW_DAYS)
    used = FeedStockMovement.objects.filter(
        feed_item=item, kind=MovementKind.USAGE, date__gt=since
    ).aggregate(s=Sum("quantity"))["s"] or Decimal("0")
    return -used / USAGE_WINDOW_DAYS


def days_left(item: FeedItem) -> int | None:
    per_day = average_daily_use(item)
    if per_day <= 0:
        return None
    return max(int(item.stock_quantity / per_day), 0)


def add_movement(
    item: FeedItem, kind: str, quantity: Decimal, user: Any, **extra: Any
) -> FeedStockMovement:
    unit_cost = extra.pop("unit_cost_cents", None)
    movement = FeedStockMovement.objects.create(
        farm_id=item.farm_id,
        feed_item=item,
        kind=kind,
        quantity=quantity,
        unit_cost_cents=unit_cost,
        total_cost_cents=int(abs(quantity) * unit_cost) if unit_cost is not None else None,
        created_by=user,
        updated_by=user,
        **extra,
    )
    if kind == MovementKind.PURCHASE and unit_cost is not None:
        FeedItem.objects.filter(pk=item.pk).update(unit_cost_cents=unit_cost)
    recompute_stock(item)
    return movement


def check_available(
    item: FeedItem, quantity: Decimal, already_taken: Decimal = Decimal("0")
) -> None:
    available = item.stock_quantity + already_taken
    if quantity > available:
        raise ValidationError(
            {"quantity": [f"Only {available.normalize():f} {item.unit} of {item.name} in stock."]}
        )


@transaction.atomic
def save_usage(
    record: FeedingRecord | Supplementation,
    item: FeedItem | None,
    quantity: Decimal | None,
    user: Any,
) -> None:
    """A feeding (or supplementation from stock) owns one usage movement of -quantity."""
    field = "feeding_record" if isinstance(record, FeedingRecord) else "supplementation"
    movement = FeedStockMovement.objects.filter(**{field: record}).first()
    old_item = movement.feed_item if movement else None
    if item is None or not quantity:
        if movement:
            movement.hard_delete()
            recompute_stock(old_item)  # type: ignore[arg-type]
        return
    if movement is None:
        add_movement(
            item,
            MovementKind.USAGE,
            -quantity,
            user,
            date=record.date,
            notes=str(record)[:200],
            **{field: record},
        )
        return
    movement.feed_item, movement.quantity, movement.date = item, -quantity, record.date
    movement.updated_by = user
    movement.save()
    recompute_stock(item)
    if old_item and old_item.pk != item.pk:
        recompute_stock(old_item)


@transaction.atomic
def remove_usage(record: FeedingRecord | Supplementation) -> None:
    field = "feeding_record" if isinstance(record, FeedingRecord) else "supplementation"
    movement = FeedStockMovement.unscoped.filter(**{field: record}).first()
    if movement:
        item = movement.feed_item
        movement.hard_delete()
        recompute_stock(item)


def _nutrition_events(animal: Animal) -> Iterable[TimelineEvent]:
    for a in NutritionAssessment.objects.filter(animal=animal):
        bcs = f"Body condition {a.body_condition_score}" if a.body_condition_score else ""
        yield TimelineEvent(_as_datetime(a.date), "nutrition", "Nutrition assessment", bcs)
    for s in Supplementation.objects.filter(animal=animal):
        yield TimelineEvent(
            _as_datetime(s.date), "nutrition", f"Supplement: {s.supplement}", s.dosage
        )


TIMELINE_SOURCES.append(_nutrition_events)
