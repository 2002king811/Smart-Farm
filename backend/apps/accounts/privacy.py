"""Personal data rights (Data Protection Acts of Uganda 2019 and Kenya 2019): a person can
download the personal data Smart Farm holds about them and delete their account."""

from __future__ import annotations

import datetime as dt
from typing import Any

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .models import FarmMembership, MembershipStatus, Role, User


def personal_data(user: User) -> dict[str, Any]:
    from apps.notifications.models import (
        ChannelContact,
        Notification,
        NotificationPreference,
        NotificationSettings,
    )

    def row(obj: Any, fields: list[str]) -> dict[str, Any]:
        out = {}
        for f in fields:
            v = getattr(obj, f)
            out[f] = (
                v.isoformat()
                if isinstance(v, (dt.date, dt.datetime, dt.time))
                else (str(v) if hasattr(v, "pk") else v)
            )
        return out

    return {
        "exported_at": timezone.now().isoformat(),
        "profile": row(
            user,
            [
                "username",
                "first_name",
                "last_name",
                "email",
                "phone",
                "language",
                "email_verified",
                "phone_verified",
                "alert_channels",
                "date_joined",
                "last_login",
            ],
        ),
        "farms": [
            {
                "farm": m.farm.name,
                "role": m.get_role_display(),
                "job_title": m.job_title,
                "status": m.status,
                "joined_at": m.joined_at.isoformat(),
            }
            for m in user.memberships.select_related("farm")
        ],
        "contacts_and_consent": [
            row(c, ["channel", "address", "verified", "opted_in_at", "opted_out_at", "bounced_at"])
            for c in ChannelContact.objects.filter(user=user)
        ],
        "notification_settings": [
            row(
                x,
                [
                    "farm",
                    "quiet_hours_enabled",
                    "quiet_start",
                    "quiet_end",
                    "digest_time",
                    "language",
                ],
            )
            for x in NotificationSettings.unscoped.filter(user=user).select_related("farm")
        ],
        "notification_preferences": [
            row(p, ["farm", "event_type", "channel", "enabled"])
            for p in NotificationPreference.unscoped.filter(user=user).select_related("farm")
        ],
        "notifications": [
            row(n, ["farm", "event_type", "title", "message", "created_at", "read_at"])
            for n in Notification.unscoped.filter(recipient=user).select_related("farm")[:2000]
        ],
    }


def sole_admin_farms(user: User) -> list[str]:
    names = []
    for m in user.memberships.filter(
        role=Role.ADMINISTRATOR, status=MembershipStatus.ACTIVE
    ).select_related("farm"):
        others = FarmMembership.objects.filter(
            farm=m.farm, role=Role.ADMINISTRATOR, status=MembershipStatus.ACTIVE
        ).exclude(user=user)
        if not others.exists():
            names.append(m.farm.name)
    return names


@transaction.atomic
def delete_account(user: User) -> None:
    """Removes the person's personal data. Farm records they entered stay with the farm (the
    farm owns them) but no longer point to a name, phone or email."""
    from apps.notifications.models import (
        ChannelContact,
        Notification,
        NotificationPreference,
        NotificationSettings,
        OutboundMessage,
    )

    from .services import revoke_refresh_tokens

    blocked = sole_admin_farms(user)
    if blocked:
        raise ValidationError(
            {
                "detail": [
                    f"You are the only administrator of {', '.join(blocked)}. Make someone else an administrator first."
                ]
            }
        )
    OutboundMessage.unscoped.filter(notification__recipient=user).update(to="", payload={})
    Notification.unscoped.filter(recipient=user).delete()
    NotificationPreference.unscoped.filter(user=user).delete()
    NotificationSettings.unscoped.filter(user=user).delete()
    ChannelContact.objects.filter(user=user).delete()
    FarmMembership.objects.filter(user=user).update(status=MembershipStatus.INACTIVE, job_title="")
    revoke_refresh_tokens(user)
    if user.photo:
        user.photo.delete(save=False)
    user.username = f"deleted-{user.pk.hex[:12]}"
    user.first_name, user.last_name = "Deleted", "user"
    user.email, user.phone = "", ""
    user.email_verified = user.phone_verified = False
    user.alert_channels = []
    user.is_active = False
    user.set_unusable_password()
    user.save()
