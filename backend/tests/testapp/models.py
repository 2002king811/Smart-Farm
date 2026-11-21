from django.db import models

from apps.core.models import FarmScopedModel


class Pen(FarmScopedModel):
    name = models.CharField(max_length=50)

    def __str__(self) -> str:
        return self.name


class Goat(FarmScopedModel):
    class Status(models.TextChoices):
        HEALTHY = "healthy", "Healthy"
        SICK = "sick", "Sick"

    name = models.CharField(max_length=50)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.HEALTHY)
    pen = models.ForeignKey(
        Pen, null=True, blank=True, on_delete=models.SET_NULL, related_name="goats"
    )
    visited_pens = models.ManyToManyField(Pen, blank=True, related_name="visitors")

    def __str__(self) -> str:
        return self.name
