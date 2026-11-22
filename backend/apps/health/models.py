from __future__ import annotations

from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.core.models import FarmScopedModel


class DiseaseCategory(models.TextChoices):
    CLOSTRIDIAL = "clostridial", "Clostridial"
    PPR = "ppr", "PPR"
    GOAT_POX = "goat_pox", "Goat Pox"
    BRUCELLOSIS = "brucellosis", "Brucellosis"
    ANTHRAX = "anthrax", "Anthrax"
    CCPP = "ccpp", "CCPP"
    FMD = "fmd", "FMD"
    OTHER = "other", "Other"


class Route(models.TextChoices):
    SUBCUTANEOUS = "sc", "Subcutaneous (SC)"
    INTRAMUSCULAR = "im", "Intramuscular (IM)"
    ORAL = "oral", "Oral"
    INTRANASAL = "intranasal", "Intranasal"
    TOPICAL = "topical", "Topical / pour-on"
    OTHER = "other", "Other"


class MedicineType(models.TextChoices):
    ANTIBIOTIC = "antibiotic", "Antibiotic"
    ANTI_INFLAMMATORY = "anti_inflammatory", "Anti-inflammatory"
    DEWORMER = "dewormer", "Dewormer"
    ACARICIDE = "acaricide", "Acaricide"
    VITAMIN = "vitamin", "Vitamin / mineral"
    OTHER = "other", "Other"


class Vaccine(FarmScopedModel):
    name = models.CharField(max_length=80)
    disease_category = models.CharField(max_length=12, choices=DiseaseCategory.choices)
    manufacturer = models.CharField(max_length=80, blank=True)
    default_dose = models.CharField(max_length=40, blank=True)
    route = models.CharField(max_length=10, choices=Route.choices, default=Route.SUBCUTANEOUS)
    withdrawal_days = models.PositiveSmallIntegerField(default=0)
    booster_interval_days = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="Suggests the next due date"
    )

    class Meta(FarmScopedModel.Meta):
        ordering = ("name",)
        constraints = [
            models.UniqueConstraint(
                fields=["farm", "name"],
                condition=Q(deleted_at__isnull=True),
                name="uniq_vaccine_name",
            )
        ]

    def __str__(self) -> str:
        return self.name


class Medicine(FarmScopedModel):
    name = models.CharField(max_length=80)
    type = models.CharField(max_length=18, choices=MedicineType.choices, default=MedicineType.OTHER)
    manufacturer = models.CharField(max_length=80, blank=True)
    default_dose = models.CharField(max_length=40, blank=True)
    route = models.CharField(max_length=10, choices=Route.choices, default=Route.ORAL)
    withdrawal_days = models.PositiveSmallIntegerField(
        default=0, help_text="Meat/milk withdrawal period"
    )

    class Meta(FarmScopedModel.Meta):
        ordering = ("name",)
        constraints = [
            models.UniqueConstraint(
                fields=["farm", "name"],
                condition=Q(deleted_at__isnull=True),
                name="uniq_medicine_name",
            )
        ]

    def __str__(self) -> str:
        return self.name


class HealthRecord(FarmScopedModel):
    """Fields every health record shares. Animal-or-group records set one of the two."""

    date = models.DateField(default=timezone.localdate)
    notes = models.TextField(blank=True)

    # Name of the field holding the follow-up date that creates a calendar activity, if any.
    NEXT_DATE_FIELD: str | None = None

    class Meta(FarmScopedModel.Meta):
        abstract = True
        ordering = ("-date", "-created_at")  # type: ignore[assignment]


class DoneStatus(models.TextChoices):
    COMPLETED = "completed", "Completed"
    MISSED = "missed", "Missed"


class Vaccination(HealthRecord):
    NEXT_DATE_FIELD = "next_due_date"

    animal = models.ForeignKey(
        "livestock.Animal",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="vaccinations",
    )
    group = models.ForeignKey(
        "livestock.AnimalGroup",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="vaccinations",
    )
    vaccine = models.ForeignKey(
        Vaccine, null=True, blank=True, on_delete=models.SET_NULL, related_name="records"
    )
    vaccine_name = models.CharField(
        max_length=80, blank=True, help_text="When the vaccine is not in the list"
    )
    disease_category = models.CharField(max_length=12, choices=DiseaseCategory.choices)
    batch_number = models.CharField(max_length=40, blank=True)
    dosage = models.CharField(max_length=40, blank=True)
    route = models.CharField(max_length=10, choices=Route.choices, blank=True)
    administered_by = models.CharField(max_length=80, blank=True)
    vet_officer = models.CharField(max_length=80, blank=True)
    next_due_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=10, choices=DoneStatus.choices, default=DoneStatus.COMPLETED
    )

    class Meta(HealthRecord.Meta):
        indexes = [
            models.Index(fields=["farm", "date"]),
            models.Index(fields=["farm", "next_due_date"]),
        ]

    def __str__(self) -> str:
        return f"{self.get_disease_category_display()} vaccination on {self.date}"


class Deworming(HealthRecord):
    NEXT_DATE_FIELD = "next_due_date"

    animal = models.ForeignKey(
        "livestock.Animal",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="dewormings",
    )
    group = models.ForeignKey(
        "livestock.AnimalGroup",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="dewormings",
    )
    product = models.ForeignKey(
        Medicine, null=True, blank=True, on_delete=models.SET_NULL, related_name="dewormings"
    )
    product_name = models.CharField(max_length=80, blank=True)
    dosage = models.CharField(max_length=40, blank=True)
    administered_by = models.CharField(max_length=80, blank=True)
    next_due_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=10, choices=DoneStatus.choices, default=DoneStatus.COMPLETED
    )

    class Meta(HealthRecord.Meta):
        indexes = [models.Index(fields=["farm", "date"])]

    def __str__(self) -> str:
        return f"Deworming on {self.date}"


class TreatmentStatus(models.TextChoices):
    ONGOING = "ongoing", "Ongoing"
    RESOLVED = "resolved", "Resolved"


class Treatment(HealthRecord):
    NEXT_DATE_FIELD = "follow_up_date"
    AUDIT_STATUS_FIELDS = ("status",)

    animal = models.ForeignKey(
        "livestock.Animal", on_delete=models.CASCADE, related_name="treatments"
    )
    diagnosis = models.CharField(max_length=120)
    symptoms = models.TextField(blank=True)
    treatment = models.TextField(blank=True, help_text="What was done")
    medication = models.ForeignKey(
        Medicine, null=True, blank=True, on_delete=models.SET_NULL, related_name="treatments"
    )
    medication_name = models.CharField(max_length=80, blank=True)
    dosage = models.CharField(max_length=60, blank=True)
    route = models.CharField(max_length=10, choices=Route.choices, blank=True)
    responsible_person = models.CharField(max_length=80, blank=True)
    vet_officer = models.CharField(max_length=80, blank=True)
    follow_up_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=10, choices=TreatmentStatus.choices, default=TreatmentStatus.ONGOING
    )
    resolved_date = models.DateField(null=True, blank=True)
    withdrawal_until = models.DateField(
        null=True, blank=True, help_text="Do not sell or milk until this date"
    )

    class Meta(HealthRecord.Meta):
        indexes = [models.Index(fields=["farm", "date"]), models.Index(fields=["farm", "status"])]

    def __str__(self) -> str:
        return f"{self.diagnosis} ({self.date})"


class VetVisit(HealthRecord):
    NEXT_DATE_FIELD = "next_visit_date"

    vet_name = models.CharField(max_length=80)
    reason = models.CharField(max_length=160)
    animals = models.ManyToManyField("livestock.Animal", blank=True, related_name="vet_visits")
    findings = models.TextField(blank=True)
    recommendations = models.TextField(blank=True)
    next_visit_date = models.DateField(null=True, blank=True)
    cost_cents = models.PositiveIntegerField(
        null=True, blank=True, help_text="In cents of the farm currency"
    )

    def __str__(self) -> str:
        return f"Vet visit by {self.vet_name} on {self.date}"


class Severity(models.TextChoices):
    MILD = "mild", "Mild"
    MODERATE = "moderate", "Moderate"
    SEVERE = "severe", "Severe"


class HealthObservation(HealthRecord):
    """Disease monitoring: what someone noticed in an animal."""

    animal = models.ForeignKey(
        "livestock.Animal", on_delete=models.CASCADE, related_name="observations"
    )
    observed_by = models.CharField(max_length=80, blank=True)
    symptoms = models.TextField()
    temperature_c = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("30")), MaxValueValidator(Decimal("45"))],
    )
    severity = models.CharField(max_length=10, choices=Severity.choices, default=Severity.MILD)
    suspected_disease = models.CharField(max_length=80, blank=True)
    action_taken = models.TextField(blank=True)

    # Goats run 38.5–40 °C; above this an observation is a health alert.
    FEVER_C = Decimal("40.5")

    def __str__(self) -> str:
        return f"Observation on {self.date}"


class InspectionResult(models.TextChoices):
    GOOD = "good", "Good"
    NEEDS_ATTENTION = "needs_attention", "Needs attention"
    POOR = "poor", "Poor"


class HealthInspection(HealthRecord):
    NEXT_DATE_FIELD = "next_inspection_date"

    inspector = models.CharField(max_length=80)
    animals = models.ManyToManyField("livestock.Animal", blank=True, related_name="inspections")
    group = models.ForeignKey(
        "livestock.AnimalGroup",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="inspections",
    )
    animals_inspected = models.PositiveIntegerField(null=True, blank=True)
    findings = models.TextField(blank=True)
    score = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
        help_text="1 (poor) to 10 (excellent)",
    )
    result = models.CharField(
        max_length=16, choices=InspectionResult.choices, default=InspectionResult.GOOD
    )
    next_inspection_date = models.DateField(null=True, blank=True)

    def __str__(self) -> str:
        return f"Inspection on {self.date}"


class ParasiteMethod(models.TextChoices):
    DIPPING = "dipping", "Dipping"
    SPRAYING = "spraying", "Spraying"
    POUR_ON = "pour_on", "Pour-on"
    INJECTION = "injection", "Injection"
    ENVIRONMENT = "environment", "Pen / pasture treatment"


class ParasiteControl(HealthRecord):
    NEXT_DATE_FIELD = "next_due_date"

    method = models.CharField(max_length=12, choices=ParasiteMethod.choices)
    target = models.CharField(max_length=80, help_text="Ticks, mites, lice, flies…")
    product = models.ForeignKey(
        Medicine, null=True, blank=True, on_delete=models.SET_NULL, related_name="parasite_controls"
    )
    product_name = models.CharField(max_length=80, blank=True)
    animals = models.ManyToManyField(
        "livestock.Animal", blank=True, related_name="parasite_controls"
    )
    group = models.ForeignKey(
        "livestock.AnimalGroup",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="parasite_controls",
    )
    administered_by = models.CharField(max_length=80, blank=True)
    next_due_date = models.DateField(null=True, blank=True)

    def __str__(self) -> str:
        return f"{self.get_method_display()} on {self.date}"
