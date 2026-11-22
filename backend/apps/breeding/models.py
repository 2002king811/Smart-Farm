from __future__ import annotations

from datetime import timedelta

from django.db import models
from django.utils import timezone

from apps.core.models import FarmScopedModel

GESTATION_DAYS = 150  # goats: expected kidding = mating + 150 days


class MatingMethod(models.TextChoices):
    NATURAL = "natural", "Natural"
    AI = "ai", "Artificial insemination"


class PregnancyStatus(models.TextChoices):
    AWAITING_SCAN = "awaiting_scan", "Awaiting scan"
    CONFIRMED = "confirmed", "Confirmed"
    NOT_PREGNANT = "not_pregnant", "Not pregnant"


class MatingStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    KIDDED = "kidded", "Kidded"
    FAILED = "failed", "Failed"
    ABORTED = "aborted", "Aborted"


class Mating(FarmScopedModel):
    AUDIT_STATUS_FIELDS = ("pregnancy_status", "status")

    doe = models.ForeignKey(
        "livestock.Animal", on_delete=models.CASCADE, related_name="matings_as_doe"
    )
    buck = models.ForeignKey(
        "livestock.Animal",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="matings_as_buck",
    )
    ai_straw = models.CharField(
        max_length=80, blank=True, help_text="AI straw / sire details when there is no buck"
    )
    date = models.DateField(default=timezone.localdate)
    method = models.CharField(
        max_length=8, choices=MatingMethod.choices, default=MatingMethod.NATURAL
    )
    pregnancy_status = models.CharField(
        max_length=14, choices=PregnancyStatus.choices, default=PregnancyStatus.AWAITING_SCAN
    )
    scan_date = models.DateField(null=True, blank=True)
    expected_kidding_date = models.DateField(null=True, blank=True)
    actual_kidding_date = models.DateField(null=True, blank=True)
    kids_count = models.PositiveSmallIntegerField(null=True, blank=True)
    status = models.CharField(
        max_length=8, choices=MatingStatus.choices, default=MatingStatus.ACTIVE
    )
    notes = models.TextField(blank=True)

    class Meta(FarmScopedModel.Meta):
        ordering = ("-date", "-created_at")  # type: ignore[assignment]
        indexes = [models.Index(fields=["farm", "date"]), models.Index(fields=["farm", "status"])]

    def __str__(self) -> str:
        return f"{self.doe} mated {self.date}"

    def save(self, *args: object, **kwargs: object) -> None:
        if self.expected_kidding_date is None and self.date:
            self.expected_kidding_date = self.date + timedelta(days=GESTATION_DAYS)
        super().save(*args, **kwargs)  # type: ignore[arg-type]


class BirthType(models.TextChoices):
    SINGLE = "single", "Single"
    TWINS = "twins", "Twins"
    TRIPLETS = "triplets", "Triplets"
    QUADRUPLETS = "quadruplets", "Quadruplets"


class BirthCondition(models.TextChoices):
    NORMAL = "normal", "Normal"
    ASSISTED = "assisted", "Assisted"
    DIFFICULT = "difficult", "Difficult (dystocia)"


class Birth(FarmScopedModel):
    mating = models.ForeignKey(
        Mating, null=True, blank=True, on_delete=models.SET_NULL, related_name="births"
    )
    dam = models.ForeignKey(
        "livestock.Animal", on_delete=models.CASCADE, related_name="births_as_dam"
    )
    sire = models.ForeignKey(
        "livestock.Animal",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="births_as_sire",
    )
    date = models.DateField(default=timezone.localdate)
    birth_type = models.CharField(
        max_length=12, choices=BirthType.choices, default=BirthType.SINGLE
    )
    condition = models.CharField(
        max_length=10, choices=BirthCondition.choices, default=BirthCondition.NORMAL
    )
    kids = models.ManyToManyField("livestock.Animal", blank=True, related_name="birth_records")
    stillborn_count = models.PositiveSmallIntegerField(default=0)
    notes = models.TextField(blank=True)

    class Meta(FarmScopedModel.Meta):
        ordering = ("-date", "-created_at")  # type: ignore[assignment]
        indexes = [models.Index(fields=["farm", "date"])]

    def __str__(self) -> str:
        return f"Birth to {self.dam} on {self.date}"


class DeathCause(models.TextChoices):
    DISEASE = "disease", "Disease"
    BIRTH = "birth", "Birth complications"
    PREDATOR = "predator", "Predator"
    ACCIDENT = "accident", "Accident / injury"
    POISONING = "poisoning", "Poisoning"
    MALNUTRITION = "malnutrition", "Malnutrition"
    OLD_AGE = "old_age", "Old age"
    UNKNOWN = "unknown", "Unknown"


class Disposal(models.TextChoices):
    BURIAL = "burial", "Burial"
    BURNING = "burning", "Burning"
    POST_MORTEM = "post_mortem", "Sent for post-mortem"
    OTHER = "other", "Other"


class Mortality(FarmScopedModel):
    animal = models.OneToOneField(
        "livestock.Animal", on_delete=models.CASCADE, related_name="mortality"
    )
    date = models.DateField(default=timezone.localdate)
    age_at_death_months = models.PositiveIntegerField(null=True, blank=True)
    cause_category = models.CharField(
        max_length=14, choices=DeathCause.choices, default=DeathCause.UNKNOWN
    )
    cause = models.CharField(
        max_length=160, blank=True, help_text="Details, e.g. suspected pneumonia"
    )
    disposal = models.CharField(max_length=12, choices=Disposal.choices, default=Disposal.BURIAL)
    recorded_by = models.CharField(max_length=80, blank=True)
    notes = models.TextField(blank=True)

    class Meta(FarmScopedModel.Meta):
        ordering = ("-date", "-created_at")  # type: ignore[assignment]
        verbose_name_plural = "mortalities"
        indexes = [models.Index(fields=["farm", "date"])]

    def __str__(self) -> str:
        return f"Death of {self.animal} on {self.date}"
