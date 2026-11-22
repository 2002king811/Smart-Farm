from __future__ import annotations

from typing import Any

from rest_framework import serializers

from . import catalog
from .models import (
    Channel,
    ChannelContact,
    EventType,
    Notification,
    NotificationSettings,
    OutboundMessage,
)


class DeliverySerializer(serializers.ModelSerializer):
    class Meta:
        model = OutboundMessage
        fields = (
            "id",
            "channel",
            "status",
            "error",
            "attempts",
            "send_after",
            "sent_at",
            "status_at",
        )


class NotificationSerializer(serializers.ModelSerializer):
    deliveries = DeliverySerializer(many=True, read_only=True)
    event_label = serializers.CharField(source="get_event_type_display", read_only=True)
    read = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = (
            "id",
            "event_type",
            "event_label",
            "title",
            "message",
            "link",
            "urgent",
            "read",
            "read_at",
            "created_at",
            "deliveries",
        )

    def get_read(self, obj: Notification) -> bool:
        return obj.read_at is not None


class MatrixRowSerializer(serializers.Serializer):
    event_type = serializers.ChoiceField(
        choices=[(e, EventType(e).label) for e in catalog.MATRIX_EVENTS]
    )
    label = serializers.CharField(read_only=True)  # type: ignore[assignment]
    channels = serializers.DictField(child=serializers.BooleanField())

    def validate_channels(self, value: dict[str, bool]) -> dict[str, bool]:
        unknown = set(value) - set(Channel.values)
        if unknown:
            raise serializers.ValidationError(f"Unknown channel: {', '.join(sorted(unknown))}")
        return value


class NotificationSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationSettings
        fields = (
            "quiet_hours_enabled",
            "quiet_start",
            "quiet_end",
            "digest_time",
            "language",
            "default_reminder_days",
        )
        extra_kwargs = {"default_reminder_days": {"min_value": 0, "max_value": 30}}


class PreferencesSerializer(serializers.Serializer):
    matrix = MatrixRowSerializer(many=True)
    settings = NotificationSettingsSerializer()


class ContactSerializer(serializers.ModelSerializer):
    channel_label = serializers.CharField(source="get_channel_display", read_only=True)
    opted_in = serializers.SerializerMethodField()
    problem = serializers.SerializerMethodField()

    class Meta:
        model = ChannelContact
        fields = (
            "channel",
            "channel_label",
            "address",
            "verified",
            "opted_in",
            "opted_in_at",
            "opted_out_at",
            "bounced_at",
            "problem",
        )

    def get_opted_in(self, obj: ChannelContact) -> bool:
        return obj.opted_out_at is None and (
            obj.channel != Channel.WHATSAPP or obj.opted_in_at is not None
        )

    def get_problem(self, obj: ChannelContact) -> str:
        from .services import unreachable_reason

        return unreachable_reason(obj, obj.channel)


class ContactUpdateSerializer(serializers.Serializer):
    opted_in = serializers.BooleanField()


class TestSendSerializer(serializers.Serializer):
    channel = serializers.ChoiceField(choices=Channel.choices)


class UnreadCountSerializer(serializers.Serializer):
    unread = serializers.IntegerField()
    urgent = serializers.IntegerField()


def usage_payload(data: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"channel": c, "label": Channel(c).label, **v} for c, v in data.items()]


class UsageSerializer(serializers.Serializer):
    channel = serializers.CharField()
    label = serializers.CharField()  # type: ignore[assignment]
    used = serializers.IntegerField()
    allowance = serializers.IntegerField(allow_null=True)
    month = serializers.CharField()
