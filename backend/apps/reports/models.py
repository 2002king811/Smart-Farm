from __future__ import annotations

import uuid

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models

from apps.core.models import FarmOwnedModel, FarmScopedModel


class ReportFormat(models.TextChoices):
    PDF = "pdf", "PDF"
    XLSX = "xlsx", "Excel"
    CSV = "csv", "CSV"


class RunStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    RUNNING = "running", "Running"
    DONE = "done", "Done"
    FAILED = "failed", "Failed"


class ReportRun(FarmOwnedModel):
    """One export of one report. Large ones are built in the background and kept as a file
    that the requester downloads through a link valid for 24 hours."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    report_type = models.CharField(max_length=40)
    filters = models.JSONField(default=dict, blank=True)
    date_from = models.DateField()
    date_to = models.DateField()
    group = models.CharField(max_length=6, default="month")
    format = models.CharField(max_length=4, choices=ReportFormat.choices)
    file = models.FileField(upload_to="reports/", blank=True)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    status = models.CharField(max_length=8, choices=RunStatus.choices, default=RunStatus.QUEUED)
    row_count = models.PositiveIntegerField(default=0)
    error = models.CharField(max_length=300, blank=True)
    purpose = models.CharField(
        max_length=10, default="download", help_text="download | schedule | share"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["farm", "created_at"])]

    def __str__(self) -> str:
        return f"{self.report_type} {self.date_from}–{self.date_to} ({self.format})"


class ScheduledType(models.TextChoices):
    MONTHLY_ACTIVITIES = "monthly_activities", "Monthly Farm Activities (1st of each month)"
    QUARTERLY_HEALTH = "quarterly_health", "Quarterly Health Report (1st of each quarter)"


class ReportSchedule(FarmScopedModel):
    """Emails last month's activities or last quarter's health report to chosen people."""

    report_type = models.CharField(max_length=40, choices=ScheduledType.choices)
    recipients = ArrayField(models.EmailField(), default=list)
    format = models.CharField(max_length=4, choices=ReportFormat.choices, default=ReportFormat.PDF)
    enabled = models.BooleanField(default=True)
    last_period = models.CharField(
        max_length=10, blank=True, help_text="Last period sent, e.g. 2026-10 or 2026-Q3"
    )
    last_sent_at = models.DateTimeField(null=True, blank=True)

    class Meta(FarmScopedModel.Meta):
        ordering = ("report_type",)

    def __str__(self) -> str:
        return f"{self.get_report_type_display()} → {', '.join(self.recipients)}"
