from __future__ import annotations

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.db.models import Q

from apps.core.models import FarmScopedModel


class CategoryKey(models.TextChoices):
    VACCINATION = "vaccination", "Vaccination"
    DEWORMING = "deworming", "Deworming"
    PARASITE_CONTROL = "parasite_control", "Parasite Control"
    TREATMENT = "treatment", "Treatment"
    VET_VISIT = "vet_visit", "Vet Visit"
    INSPECTION = "inspection", "Health Inspection"
    BREEDING = "breeding", "Breeding"
    FEEDING = "feeding", "Feeding & Nutrition"


# The 8 activity categories: key, colour, Lucide icon name.
DEFAULT_CATEGORIES = [
    (CategoryKey.VACCINATION, "#2E7D32", "syringe"),
    (CategoryKey.DEWORMING, "#6A1B9A", "bug"),
    (CategoryKey.PARASITE_CONTROL, "#00838F", "shield"),
    (CategoryKey.TREATMENT, "#C62828", "pill"),
    (CategoryKey.VET_VISIT, "#1565C0", "stethoscope"),
    (CategoryKey.INSPECTION, "#455A64", "clipboard-check"),
    (CategoryKey.BREEDING, "#AD1457", "heart"),
    (CategoryKey.FEEDING, "#EF6C00", "wheat"),
]


class ActivityCategory(FarmScopedModel):
    name = models.CharField(max_length=60)
    key = models.CharField(max_length=20, blank=True, help_text="Set for the built-in categories")
    colour = models.CharField(max_length=7, default="#2E7D32")
    icon = models.CharField(max_length=40, default="calendar")

    class Meta(FarmScopedModel.Meta):
        ordering = ("name",)
        verbose_name_plural = "activity categories"
        constraints = [
            models.UniqueConstraint(
                fields=["farm", "name"],
                condition=Q(deleted_at__isnull=True),
                name="uniq_category_name",
            )
        ]

    def __str__(self) -> str:
        return self.name


class Priority(models.TextChoices):
    HIGH = "high", "High"
    MEDIUM = "medium", "Medium"
    LOW = "low", "Low"


class ActivityStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    IN_PROGRESS = "in_progress", "In Progress"
    COMPLETED = "completed", "Completed"
    OVERDUE = "overdue", "Overdue"
    CANCELLED = "cancelled", "Cancelled"


OPEN_STATUSES = (ActivityStatus.PENDING, ActivityStatus.IN_PROGRESS, ActivityStatus.OVERDUE)


class ActivitySource(models.TextChoices):
    MANUAL = "manual", "Manual"
    VACCINATION = "vaccination", "Vaccination"
    DEWORMING = "deworming", "Deworming"
    TREATMENT = "treatment", "Treatment"
    HEALTH = "health", "Health record"
    BREEDING = "breeding", "Breeding"
    TEMPLATE = "template", "Health calendar template"


class Activity(FarmScopedModel):
    title = models.CharField(max_length=160)
    category = models.ForeignKey(
        ActivityCategory,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="activities",
    )
    date = models.DateField()
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    all_day = models.BooleanField(default=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_activities",
    )
    animals = models.ManyToManyField("livestock.Animal", blank=True, related_name="activities")
    group = models.ForeignKey(
        "livestock.AnimalGroup",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="activities",
    )
    description = models.TextField(blank=True)
    priority = models.CharField(max_length=6, choices=Priority.choices, default=Priority.MEDIUM)
    status = models.CharField(
        max_length=12, choices=ActivityStatus.choices, default=ActivityStatus.PENDING
    )
    # Days before the activity to remind (phase 6 sends them), e.g. [3, 1].
    reminder_days = ArrayField(models.PositiveSmallIntegerField(), default=list, blank=True)
    # iCalendar RRULE, e.g. "FREQ=MONTHLY;INTERVAL=3". Set on the first activity of a series.
    recurrence_rule = models.CharField(max_length=200, blank=True)
    series = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.CASCADE, related_name="occurrences"
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    source = models.CharField(
        max_length=12, choices=ActivitySource.choices, default=ActivitySource.MANUAL
    )
    # The record that created it (e.g. the vaccination whose next due date this is).
    source_type = models.ForeignKey(
        ContentType, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    source_id = models.CharField(max_length=64, blank=True)
    template_key = models.CharField(max_length=60, blank=True)

    class Meta(FarmScopedModel.Meta):
        ordering = ("date", "start_time", "created_at")  # type: ignore[assignment]
        verbose_name_plural = "activities"
        indexes = [
            models.Index(fields=["farm", "date"]),
            models.Index(fields=["farm", "status"]),
            models.Index(fields=["source_type", "source_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.title} ({self.date})"

    @property
    def is_open(self) -> bool:
        return self.status in OPEN_STATUSES


class ActivityStatusHistory(FarmScopedModel):
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE, related_name="history")
    from_status = models.CharField(max_length=12, choices=ActivityStatus.choices, blank=True)
    to_status = models.CharField(max_length=12, choices=ActivityStatus.choices)
    note = models.CharField(max_length=300, blank=True)

    class Meta(FarmScopedModel.Meta):
        ordering = ("created_at",)  # type: ignore[assignment]
        verbose_name_plural = "activity status history"

    def __str__(self) -> str:
        return f"{self.activity}: {self.from_status} → {self.to_status}"


class ActivityNote(FarmScopedModel):
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE, related_name="notes")
    text = models.TextField()

    class Meta(FarmScopedModel.Meta):
        ordering = ("created_at",)  # type: ignore[assignment]

    def __str__(self) -> str:
        return self.text[:40]
