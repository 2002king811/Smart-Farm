from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.core.models import FarmScopedModel

KID_AGE_MONTHS = 6  # "A kid is under 6 months"


class LocationType(models.TextChoices):
    PADDOCK = "paddock", "Paddock"
    PEN = "pen", "Pen"
    ISOLATION = "isolation", "Isolation"
    QUARANTINE = "quarantine", "Quarantine"
    OTHER = "other", "Other"


class Location(FarmScopedModel):
    name = models.CharField(max_length=80)
    type = models.CharField(max_length=12, choices=LocationType.choices, default=LocationType.PEN)
    capacity = models.PositiveIntegerField(null=True, blank=True)
    description = models.CharField(max_length=200, blank=True)

    class Meta(FarmScopedModel.Meta):
        ordering = ("name",)
        constraints = [
            models.UniqueConstraint(
                fields=["farm", "name"],
                condition=Q(deleted_at__isnull=True),
                name="uniq_location_name",
            )
        ]

    def __str__(self) -> str:
        return self.name


class AnimalGroup(FarmScopedModel):
    name = models.CharField(max_length=80)
    description = models.CharField(max_length=200, blank=True)

    class Meta(FarmScopedModel.Meta):
        ordering = ("name",)
        constraints = [
            models.UniqueConstraint(
                fields=["farm", "name"],
                condition=Q(deleted_at__isnull=True),
                name="uniq_group_name",
            )
        ]

    def __str__(self) -> str:
        return self.name


class Species(models.TextChoices):
    GOAT = "goat", "Goat"
    SHEEP = "sheep", "Sheep"
    DAIRY_CATTLE = "dairy_cattle", "Dairy cattle"
    BEEF_CATTLE = "beef_cattle", "Beef cattle"
    POULTRY = "poultry", "Poultry"


class Sex(models.TextChoices):
    FEMALE = "female", "Female"
    MALE = "male", "Male"


class HealthStatus(models.TextChoices):
    HEALTHY = "healthy", "Healthy"
    UNDER_TREATMENT = "under_treatment", "Under Treatment"
    SICK = "sick", "Sick"
    QUARANTINED = "quarantined", "Quarantined"
    PREGNANT = "pregnant", "Pregnant"
    MONITORING = "monitoring", "Monitoring"


# Statuses that count as "needing attention" on the dashboard and register.
NEEDS_ATTENTION = (
    HealthStatus.UNDER_TREATMENT,
    HealthStatus.SICK,
    HealthStatus.QUARANTINED,
    HealthStatus.MONITORING,
)


class BreedingStatus(models.TextChoices):
    OPEN = "open", "Open"
    SERVED = "served", "Served"
    PREGNANT = "pregnant", "Pregnant"
    LACTATING = "lactating", "Lactating"
    DRY = "dry", "Dry"
    BREEDING_MALE = "breeding_male", "Breeding male"
    CASTRATED = "castrated", "Castrated"
    TOO_YOUNG = "too_young", "Too young"


class AcquisitionSource(models.TextChoices):
    BORN_ON_FARM = "born_on_farm", "Born on farm"
    PURCHASED = "purchased", "Purchased"
    GIFT = "gift", "Gift"
    OTHER = "other", "Other"


class ExitReason(models.TextChoices):
    SOLD = "sold", "Sold"
    DIED = "died", "Died"
    CULLED = "culled", "Culled"


class Animal(FarmScopedModel):
    AUDIT_STATUS_FIELDS = ("health_status", "breeding_status", "is_active")

    animal_id = models.CharField(max_length=30, help_text="Farm ID, e.g. YPA-001")
    ear_tag = models.CharField(max_length=30, blank=True)
    name = models.CharField(max_length=80, blank=True)
    species = models.CharField(max_length=20, choices=Species.choices, default=Species.GOAT)
    breed = models.CharField(max_length=60, blank=True)
    sex = models.CharField(max_length=6, choices=Sex.choices)
    date_of_birth = models.DateField(null=True, blank=True)
    # When the exact birth date is unknown we store an estimated date and flag it, so the age
    # keeps counting up instead of freezing at the number typed in.
    dob_estimated = models.BooleanField(default=False)
    acquisition_date = models.DateField(null=True, blank=True)
    acquisition_source = models.CharField(
        max_length=14, choices=AcquisitionSource.choices, default=AcquisitionSource.BORN_ON_FARM
    )
    acquisition_details = models.CharField(
        max_length=200, blank=True, help_text="Seller, price, market…"
    )
    health_status = models.CharField(
        max_length=16, choices=HealthStatus.choices, default=HealthStatus.HEALTHY
    )
    breeding_status = models.CharField(
        max_length=14, choices=BreedingStatus.choices, default=BreedingStatus.OPEN
    )
    dam = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="offspring_as_dam"
    )
    sire = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="offspring_as_sire"
    )
    sire_details = models.CharField(
        max_length=120, blank=True, help_text="For AI or an outside buck: straw code, owner…"
    )
    location = models.ForeignKey(
        Location, null=True, blank=True, on_delete=models.SET_NULL, related_name="animals"
    )
    group = models.ForeignKey(
        AnimalGroup, null=True, blank=True, on_delete=models.SET_NULL, related_name="animals"
    )
    colour_markings = models.CharField(max_length=120, blank=True)
    current_condition = models.TextField(blank=True)
    previous_history = models.TextField(blank=True)
    remarks = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    exit_reason = models.CharField(max_length=8, choices=ExitReason.choices, blank=True)
    exit_date = models.DateField(null=True, blank=True)
    exit_notes = models.CharField(max_length=200, blank=True)

    class Meta(FarmScopedModel.Meta):
        ordering = ("animal_id",)
        constraints = [
            models.UniqueConstraint(
                fields=["farm", "animal_id"],
                condition=Q(deleted_at__isnull=True),
                name="uniq_animal_id_per_farm",
            ),
            models.UniqueConstraint(
                fields=["farm", "ear_tag"],
                condition=Q(deleted_at__isnull=True) & ~Q(ear_tag=""),
                name="uniq_ear_tag_per_farm",
            ),
        ]
        indexes = [
            models.Index(fields=["farm", "animal_id"]),
            models.Index(fields=["farm", "ear_tag"]),
            models.Index(fields=["farm", "health_status"]),
            models.Index(fields=["farm", "is_active"]),
        ]

    def __str__(self) -> str:
        return f"{self.animal_id} {self.name}".strip()

    def age_in_months(self, on: date | None = None) -> int | None:
        if self.date_of_birth is None:
            return None
        on = on or timezone.localdate()
        months = (on.year - self.date_of_birth.year) * 12 + on.month - self.date_of_birth.month
        if on.day < self.date_of_birth.day:
            months -= 1
        return max(months, 0)

    @property
    def is_kid(self) -> bool:
        months = self.age_in_months()
        return months is not None and months < KID_AGE_MONTHS


class WeightRecord(FarmScopedModel):
    animal = models.ForeignKey(Animal, on_delete=models.CASCADE, related_name="weights")
    date = models.DateField(default=timezone.localdate)
    weight_kg = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.1")), MaxValueValidator(Decimal("2000"))],
    )
    body_condition_score = models.DecimalField(
        max_digits=2,
        decimal_places=1,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("1")), MaxValueValidator(Decimal("5"))],
        help_text="1 (very thin) to 5 (very fat)",
    )
    notes = models.CharField(max_length=200, blank=True)

    class Meta(FarmScopedModel.Meta):
        ordering = ("-date", "-created_at")  # type: ignore[assignment]
        indexes = [models.Index(fields=["farm", "date"]), models.Index(fields=["animal", "date"])]

    def __str__(self) -> str:
        return f"{self.animal} {self.weight_kg} kg on {self.date}"


class AnimalPhoto(FarmScopedModel):
    animal = models.ForeignKey(Animal, on_delete=models.CASCADE, related_name="photos")
    file = models.ImageField(upload_to="animals/photos/")
    thumbnail = models.ImageField(upload_to="animals/thumbs/")
    is_primary = models.BooleanField(default=False)
    caption = models.CharField(max_length=120, blank=True)

    class Meta(FarmScopedModel.Meta):
        ordering = ("-is_primary", "-created_at")  # type: ignore[assignment]

    def __str__(self) -> str:
        return f"Photo of {self.animal}"
