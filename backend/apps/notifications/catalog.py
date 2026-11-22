"""What each event means: default channels, who receives it, and the words (English and
Kiswahili). Defaults follow the table in the build spec; people change them in Settings."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import Channel, EventType

C = Channel

DEFAULTS: dict[str, dict[str, bool]] = {
    EventType.UPCOMING: {C.IN_APP: True, C.WHATSAPP: False, C.SMS: False, C.EMAIL: True},
    EventType.DUE_TODAY: {C.IN_APP: True, C.WHATSAPP: True, C.SMS: False, C.EMAIL: False},
    EventType.OVERDUE: {C.IN_APP: True, C.WHATSAPP: True, C.SMS: True, C.EMAIL: True},
    EventType.VACCINATION_REMINDER: {C.IN_APP: True, C.WHATSAPP: True, C.SMS: False, C.EMAIL: True},
    EventType.DEWORMING_REMINDER: {C.IN_APP: True, C.WHATSAPP: True, C.SMS: False, C.EMAIL: False},
    EventType.HEALTH_ALERT: {C.IN_APP: True, C.WHATSAPP: True, C.SMS: True, C.EMAIL: True},
    EventType.TASK_ASSIGNED: {C.IN_APP: True, C.WHATSAPP: True, C.SMS: True, C.EMAIL: False},
    EventType.ACTIVITY_COMPLETED: {C.IN_APP: True, C.WHATSAPP: False, C.SMS: False, C.EMAIL: False},
    EventType.LOW_STOCK: {C.IN_APP: True, C.WHATSAPP: True, C.SMS: False, C.EMAIL: True},
    EventType.DAILY_SUMMARY: {C.IN_APP: False, C.WHATSAPP: False, C.SMS: False, C.EMAIL: True},
}
# Shown in the Settings matrix, in this order.
MATRIX_EVENTS = list(DEFAULTS)
# Not configurable: they go where they must.
FIXED: dict[str, dict[str, bool]] = {
    EventType.USAGE_WARNING: {C.IN_APP: True, C.WHATSAPP: False, C.SMS: False, C.EMAIL: True},
    EventType.TEST: {C.IN_APP: True, C.WHATSAPP: False, C.SMS: False, C.EMAIL: False},
}


def default_enabled(event_type: str, channel: str) -> bool:
    table = DEFAULTS.get(event_type) or FIXED.get(event_type) or {}
    return table.get(channel, False)


# Who receives it: "assignee_or_managers", "assignee_and_managers", "managers", "admins",
# "recipient" (payload recipient_id) or "self".
RECIPIENTS: dict[str, str] = {
    EventType.UPCOMING: "assignee_or_managers",
    EventType.DUE_TODAY: "assignee_or_managers",
    EventType.VACCINATION_REMINDER: "assignee_or_managers",
    EventType.DEWORMING_REMINDER: "assignee_or_managers",
    EventType.OVERDUE: "assignee_and_managers",
    EventType.TASK_ASSIGNED: "recipient",
    EventType.ACTIVITY_COMPLETED: "recipient",
    EventType.HEALTH_ALERT: "managers",
    EventType.LOW_STOCK: "managers",
    EventType.USAGE_WARNING: "admins",
    EventType.DAILY_SUMMARY: "recipient",
    EventType.TEST: "recipient",
}

# Pre-approved WhatsApp template per event (created in Meta Business Manager, English and
# Kiswahili). Each takes two body parameters, {{1}} the title and {{2}} the details; activity
# templates also carry the "1 Mark done" / "2 Reschedule" quick-reply buttons.
WHATSAPP_TEMPLATES: dict[str, str] = {
    EventType.UPCOMING: "smartfarm_activity_upcoming",
    EventType.DUE_TODAY: "smartfarm_activity_due",
    EventType.OVERDUE: "smartfarm_activity_overdue",
    EventType.VACCINATION_REMINDER: "smartfarm_vaccination_reminder",
    EventType.DEWORMING_REMINDER: "smartfarm_deworming_reminder",
    EventType.HEALTH_ALERT: "smartfarm_health_alert",
    EventType.TASK_ASSIGNED: "smartfarm_task_assigned",
    EventType.ACTIVITY_COMPLETED: "smartfarm_activity_completed",
    EventType.LOW_STOCK: "smartfarm_low_stock",
    EventType.DAILY_SUMMARY: "smartfarm_daily_summary",
    EventType.USAGE_WARNING: "smartfarm_usage_warning",
    EventType.TEST: "smartfarm_test",
}
QUICK_REPLY_EVENTS = {
    EventType.UPCOMING,
    EventType.DUE_TODAY,
    EventType.OVERDUE,
    EventType.TASK_ASSIGNED,
    EventType.VACCINATION_REMINDER,
    EventType.DEWORMING_REMINDER,
}

# Titles in English and Kiswahili; {title}, {date}, {who}, {farm} are filled in.
TITLES: dict[str, dict[str, str]] = {
    EventType.UPCOMING: {"en": "Coming up: {title}", "sw": "Inakuja: {title}"},
    EventType.DUE_TODAY: {"en": "Due today: {title}", "sw": "Leo: {title}"},
    EventType.OVERDUE: {"en": "Overdue: {title}", "sw": "Imechelewa: {title}"},
    EventType.VACCINATION_REMINDER: {
        "en": "Vaccination due: {title}",
        "sw": "Chanjo inakaribia: {title}",
    },
    EventType.DEWORMING_REMINDER: {
        "en": "Deworming due: {title}",
        "sw": "Dawa ya minyoo inakaribia: {title}",
    },
    EventType.TASK_ASSIGNED: {"en": "New task: {title}", "sw": "Kazi mpya: {title}"},
    EventType.ACTIVITY_COMPLETED: {"en": "Completed: {title}", "sw": "Imekamilika: {title}"},
}
MESSAGES: dict[str, dict[str, str]] = {
    EventType.UPCOMING: {"en": "{title} is planned for {date}.", "sw": "{title} imepangwa {date}."},
    EventType.DUE_TODAY: {"en": "{title} is due today.", "sw": "{title} inatakiwa kufanyika leo."},
    EventType.OVERDUE: {
        "en": "{title} was due on {date} and is not done yet.",
        "sw": "{title} ilitakiwa {date} na bado haijafanyika.",
    },
    EventType.VACCINATION_REMINDER: {"en": "{title} on {date}.", "sw": "{title} tarehe {date}."},
    EventType.DEWORMING_REMINDER: {"en": "{title} on {date}.", "sw": "{title} tarehe {date}."},
    EventType.TASK_ASSIGNED: {
        "en": "{who} assigned you {title} for {date}.",
        "sw": "{who} amekupa kazi {title} ya {date}.",
    },
    EventType.ACTIVITY_COMPLETED: {
        "en": "{who} completed {title}.",
        "sw": "{who} amekamilisha {title}.",
    },
}
QUICK_REPLY_HINT = {
    "en": "Reply 1 to mark done, 2 to reschedule to tomorrow.",
    "sw": "Jibu 1 kukamilisha, 2 kuahirisha hadi kesho.",
}


@dataclass
class Rendered:
    title: str
    message: str
    link: str = ""


def render_activity(event_type: str, activity: Any, lang: str, who: str = "") -> Rendered:
    lang = lang if lang in ("en", "sw") else "en"
    values = {
        "title": activity.title,
        "date": f"{activity.date:%d %b %Y}",
        "who": who or "Smart Farm",
    }
    return Rendered(
        TITLES[event_type][lang].format(**values),
        MESSAGES[event_type][lang].format(**values),
        f"/activities?activity={activity.pk}",
    )


def sms_text(title: str, message: str, quick_reply: bool, lang: str) -> str:
    """One SMS segment (160 characters) where possible."""
    text = f"Smart Farm: {title}. {message}"
    if quick_reply:
        text = f"{text} {QUICK_REPLY_HINT.get(lang, QUICK_REPLY_HINT['en'])}"
    return text if len(text) <= 160 else text[:157].rstrip() + "..."


__all__ = ["Channel", "EventType"]
