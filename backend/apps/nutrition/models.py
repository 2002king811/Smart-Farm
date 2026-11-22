from __future__ import annotations

from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.core.models import FarmScopedModel


class FeedCategory(models.TextChoices):
    FORAGE = "forage", "Forage / hay"
    CONCENTRATE = "concentrate", "Concentrate"
    MINERAL = "mineral", "Mineral / lick"
    SUPPLEMENT = "supplement", "Supplement"
    OTHER = "other", "Other"


class FeedUnit(models.TextChoices):
    KG = "kg", "kg"
    BALE = "bale", "bale"
    BAG = "bag", "bag"
    LITRE = "litre", "litre"
    BLOCK = "block", "block"


class FeedItem(FarmScopedModel):
    name = models.CharField(max_length=80)
    category = models.CharField(
        max_length=12, choices=FeedCategory.choices, default=FeedCategory.FORAGE
    )
    unit = models.CharField(max_length=6, choices=FeedUnit.choices, default=FeedUnit.KG)
    reorder_level = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"))
    unit_cost_cents = models.PositiveIntegerField(
        null=True, blank=True, help_text="Latest price per unit, in cents"
    )
    # Kept equal to the sum of this item's stock movements (updated on every movement).
    stock_quantity = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    notes = models.CharField(max_length=200, blank=True)

    class Meta(FarmScopedModel.Meta):
        ordering = ("name",)
        constraints = [
            models.UniqueConstraint(
                fields=["farm", "name"],
                condition=Q(deleted_at__isnull=True),
                name="uniq_feed_item_name",
            )
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def is_low(self) -> bool:
        return self.reorder_level > 0 and self.stock_quantity <= self.reorder_level


class MovementKind(models.TextChoices):
    PURCHASE = "purchase", "Purchase / stock in"
    USAGE = "usage", "Used (feeding)"
    ADJUSTMENT = "adjustment", "Stock count adjustment"
    WASTE = "waste", "Spoiled / wasted"


class FeedStockMovement(FarmScopedModel):
    feed_item = models.ForeignKey(FeedItem, on_delete=models.CASCADE, related_name="movements")
    date = models.DateField(default=timezone.localdate)
    kind = models.CharField(max_length=10, choices=MovementKind.choices)
    # Positive adds stock, negative removes it.
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    unit_cost_cents = models.PositiveIntegerField(null=True, blank=True)
    total_cost_cents = models.PositiveIntegerField(null=True, blank=True)
    supplier = models.CharField(max_length=80, blank=True)
    notes = models.CharField(max_length=200, blank=True)
    feeding_record = models.OneToOneField(
        "nutrition.FeedingRecord",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="movement",
    )
    supplementation = models.OneToOneField(
        "nutrition.Supplementation",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="movement",
    )

    class Meta(FarmScopedModel.Meta):
        ordering = ("-date", "-created_at")  # type: ignore[assignment]
        indexes = [
            models.Index(fields=["farm", "date"]),
            models.Index(fields=["feed_item", "date"]),
        ]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} {self.quantity} {self.feed_item}"


class FeedingRecord(FarmScopedModel):
    date = models.DateField(default=timezone.localdate)
    feed_item = models.ForeignKey(FeedItem, on_delete=models.PROTECT, related_name="feedings")
    quantity = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )
    group = models.ForeignKey(
        "livestock.AnimalGroup",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="feedings",
    )
    location = models.ForeignKey(
        "livestock.Location",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="feedings",
    )
    animals_fed = models.PositiveIntegerField(null=True, blank=True)
    responsible = models.CharField(max_length=80, blank=True)
    notes = models.CharField(max_length=200, blank=True)

    class Meta(FarmScopedModel.Meta):
        ordering = ("-date", "-created_at")  # type: ignore[assignment]
        indexes = [models.Index(fields=["farm", "date"])]

    def __str__(self) -> str:
        return f"{self.quantity} {self.feed_item} on {self.date}"


class NutritionAssessment(FarmScopedModel):
    NEXT_DATE_FIELD = "next_assessment_date"

    date = models.DateField(default=timezone.localdate)
    animal = models.ForeignKey(
        "livestock.Animal",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="nutrition_assessments",
    )
    group = models.ForeignKey(
        "livestock.AnimalGroup",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="nutrition_assessments",
    )
    body_condition_score = models.DecimalField(
        max_digits=2,
        decimal_places=1,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("1")), MaxValueValidator(Decimal("5"))],
    )
    pasture_condition = models.CharField(
        max_length=10, blank=True, choices=[("good", "Good"), ("fair", "Fair"), ("poor", "Poor")]
    )
    assessor = models.CharField(max_length=80, blank=True)
    findings = models.TextField(blank=True)
    recommendations = models.TextField(blank=True)
    next_assessment_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta(FarmScopedModel.Meta):
        ordering = ("-date", "-created_at")  # type: ignore[assignment]

    def __str__(self) -> str:
        return f"Nutrition assessment on {self.date}"


class Supplementation(FarmScopedModel):
    date = models.DateField(default=timezone.localdate)
    supplement = models.CharField(max_length=80, help_text="Mineral lick, vitamins, molasses…")
    feed_item = models.ForeignKey(
        FeedItem,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="supplementations",
        help_text="When set, the quantity is taken from stock",
    )
    quantity = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    animal = models.ForeignKey(
        "livestock.Animal",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="supplementations",
    )
    group = models.ForeignKey(
        "livestock.AnimalGroup",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="supplementations",
    )
    dosage = models.CharField(max_length=60, blank=True)
    reason = models.CharField(max_length=120, blank=True)
    given_by = models.CharField(max_length=80, blank=True)
    notes = models.TextField(blank=True)

    class Meta(FarmScopedModel.Meta):
        ordering = ("-date", "-created_at")  # type: ignore[assignment]

    def __str__(self) -> str:
        return f"{self.supplement} on {self.date}"


class WaterHygieneCheck(FarmScopedModel):
    date = models.DateField(default=timezone.localdate)
    location = models.ForeignKey(
        "livestock.Location",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="hygiene_checks",
    )
    water_source = models.CharField(max_length=60, blank=True, help_text="Borehole, tank, river…")
    water_available = models.BooleanField(default=True)
    water_clean = models.BooleanField(default=True)
    troughs_clean = models.BooleanField(default=True)
    pen_clean = models.BooleanField(default=True)
    bedding_dry = models.BooleanField(default=True)
    issues = models.TextField(blank=True)
    actions_taken = models.TextField(blank=True)
    checked_by = models.CharField(max_length=80, blank=True)
    notes = models.TextField(blank=True)

    class Meta(FarmScopedModel.Meta):
        ordering = ("-date", "-created_at")  # type: ignore[assignment]

    def __str__(self) -> str:
        return f"Water & hygiene check on {self.date}"

    CHECKS = ("water_available", "water_clean", "troughs_clean", "pen_clean", "bedding_dry")

    @property
    def score(self) -> int:
        """Checks passed out of 5."""
        return sum(1 for c in self.CHECKS if getattr(self, c))
