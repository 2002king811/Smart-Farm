from __future__ import annotations

import datetime as dt
import uuid

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import Q

from apps.core.models import FarmOwnedModel


class Channel(models.TextChoices):
    IN_APP = "in_app", "In-app"
    WHATSAPP = "whatsapp", "WhatsApp"
    SMS = "sms", "SMS"
    EMAIL = "email", "Email"


EXTERNAL_CHANNELS = (Channel.WHATSAPP, Channel.SMS, Channel.EMAIL)


class EventType(models.TextChoices):
    UPCOMING = "activity.upcoming", "Upcoming activity"
    DUE_TODAY = "activity.due_today", "Activity due today"
    OVERDUE = "activity.overdue", "Overdue activity"
    VACCINATION_REMINDER = "vaccination.reminder", "Vaccination reminder"
    DEWORMING_REMINDER = "deworming.reminder", "Deworming reminder"
    HEALTH_ALERT = "health.alert", "Health alert"
    TASK_ASSIGNED = "task.assigned", "Task assigned"
    ACTIVITY_COMPLETED = "activity.completed", "Activity completed"
    LOW_STOCK = "feed.low_stock", "Low feed stock"
    DAILY_SUMMARY = "daily.summary", "Daily summary"
    USAGE_WARNING = "usage.warning", "Message allowance warning"
    REPORT_READY = "report.ready", "Report ready"
    REPORT_SHARED = "report.shared", "Report shared"
    TEST = "test", "Test message"


class NotificationPreference(FarmOwnedModel):
    """One switch in the Settings matrix: event × channel, for one person on one farm.

    Rows exist only where the person changed a default; the defaults live in events.py."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notification_preferences"
    )
    event_type = models.CharField(max_length=30, choices=EventType.choices)
    channel = models.CharField(max_length=10, choices=Channel.choices)
    enabled = models.BooleanField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["farm", "user", "event_type", "channel"], name="uniq_notification_pref"
            )
        ]

    def __str__(self) -> str:
        return f"{self.user} {self.event_type} {self.channel}={self.enabled}"


class NotificationSettings(FarmOwnedModel):
    """Per person per farm: quiet hours, digest time, language and the default reminder."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notification_settings"
    )
    quiet_hours_enabled = models.BooleanField(default=True)
    quiet_start = models.TimeField(default=dt.time(21, 0))
    quiet_end = models.TimeField(default=dt.time(6, 0))
    digest_time = models.TimeField(default=dt.time(7, 0))
    language = models.CharField(
        max_length=5, choices=[("en", "English"), ("sw", "Kiswahili")], default="en"
    )
    default_reminder_days = models.PositiveSmallIntegerField(default=1)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["farm", "user"], name="uniq_notification_settings")
        ]
        verbose_name_plural = "notification settings"

    def __str__(self) -> str:
        return f"Notification settings for {self.user}"


class ChannelContact(models.Model):
    """Where a person receives a channel, and their consent. Not farm-owned: a person has one
    phone and one email whichever farm they are on."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="channel_contacts"
    )
    channel = models.CharField(max_length=10, choices=Channel.choices)
    address = models.CharField(max_length=254)
    verified = models.BooleanField(default=False)
    opted_in_at = models.DateTimeField(
        null=True, blank=True, help_text="WhatsApp needs recorded consent"
    )
    opted_out_at = models.DateTimeField(
        null=True, blank=True, help_text="SMS STOP / WhatsApp opt-out"
    )
    bounced_at = models.DateTimeField(null=True, blank=True, help_text="Email hard bounce")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "channel"], name="uniq_channel_contact")
        ]

    def __str__(self) -> str:
        return f"{self.user} {self.channel} {self.address}"


class Notification(FarmOwnedModel):
    """One in-app notification for one person. Every alert creates one, whatever the channels."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )
    event_type = models.CharField(max_length=30, choices=EventType.choices)
    title = models.CharField(max_length=160)
    message = models.TextField()
    link = models.CharField(max_length=200, blank=True)
    urgent = models.BooleanField(default=False)
    related_type = models.ForeignKey(
        ContentType, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    related_id = models.CharField(max_length=64, blank=True)
    # Stops the same reminder going out twice (e.g. "activity.upcoming:<id>:3").
    dedupe_key = models.CharField(max_length=120, blank=True)
    show_in_app = models.BooleanField(default=True)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["farm", "recipient", "read_at"]),
            models.Index(fields=["farm", "created_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["recipient", "dedupe_key"],
                condition=~Q(dedupe_key=""),
                name="uniq_notification_dedupe",
            )
        ]

    def __str__(self) -> str:
        return self.title


class DeliveryStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    SENT = "sent", "Sent"
    DELIVERED = "delivered", "Delivered"
    READ = "read", "Read"
    FAILED = "failed", "Failed"


class OutboundMessage(FarmOwnedModel):
    """One message on one external channel, sent by a Celery worker, tracked by webhooks."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Empty for messages to people outside the farm's users (e.g. a report shared with the vet).
    notification = models.ForeignKey(
        Notification, null=True, blank=True, on_delete=models.CASCADE, related_name="deliveries"
    )
    channel = models.CharField(max_length=10, choices=Channel.choices)
    to = models.CharField(max_length=254)
    template = models.CharField(max_length=60)
    payload = models.JSONField(default=dict)
    language = models.CharField(max_length=5, default="en")
    status = models.CharField(
        max_length=10, choices=DeliveryStatus.choices, default=DeliveryStatus.QUEUED
    )
    send_after = models.DateTimeField(null=True, blank=True, help_text="Held for quiet hours")
    provider_id = models.CharField(max_length=120, blank=True, db_index=True)
    error = models.CharField(max_length=300, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    cost = models.CharField(
        max_length=30, blank=True, help_text="As reported by the provider, e.g. 'UGX 35.0000'"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    status_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["farm", "channel", "created_at"]),
            models.Index(fields=["status", "send_after"]),
        ]

    def __str__(self) -> str:
        return f"{self.channel} to {self.to}: {self.status}"
