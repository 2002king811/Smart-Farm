"""The notification pipeline.

emit() → domain_event signal → (after commit) dispatch_event task → for each recipient:
  one Notification (in-app) + one OutboundMessage per enabled external channel → deliver task.

Rules applied here:
* preferences: the person's switch for event × channel, else the default from catalog.py;
* contacts: SMS/WhatsApp need a confirmed phone, email a confirmed address; WhatsApp also
  needs consent, and STOP / bounces switch a channel off;
* quiet hours: SMS and WhatsApp are held until the quiet hours end, unless urgent;
* allowance: SMS and WhatsApp count against the farm's monthly allowance; administrators get
  a warning at 80 %, and non-urgent messages stop at 100 %;
* retries: a failed send is retried 3 times (1, 2 then 4 minutes later) before it is failed.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any
from zoneinfo import ZoneInfo

from asgiref.sync import async_to_sync
from celery import shared_task
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import Farm, FarmMembership, MembershipStatus, Role, User
from apps.core.context import farm_context
from apps.core.utils import after_commit

from . import catalog
from .adapters import Message, ProviderError, get_adapter
from .events import domain_event
from .models import (
    EXTERNAL_CHANNELS,
    Channel,
    ChannelContact,
    DeliveryStatus,
    EventType,
    Notification,
    NotificationPreference,
    NotificationSettings,
    OutboundMessage,
)

logger = logging.getLogger("smartfarm.notifications")
MAX_ATTEMPTS = 4  # the first try plus 3 retries
METERED = (Channel.SMS, Channel.WHATSAPP)
WARN_AT = 0.8


# --- Preferences and settings -------------------------------------------------------------------


def settings_for(user: Any, farm: Any) -> NotificationSettings:
    row = NotificationSettings.unscoped.filter(farm=farm, user=user).first()
    if row is None:
        row = NotificationSettings(farm=farm, user=user, language=user.language or "en")
    return row


def sign_up_choice(user: Any, channel: str) -> bool:
    """Channels picked at sign-up switch external channels on or off by default."""
    if channel == Channel.IN_APP:
        return True
    return channel in (user.alert_channels or [])


def enabled_channels(user: Any, farm: Any, event_type: str) -> list[str]:
    if event_type in catalog.FIXED:
        return [c for c, on in catalog.FIXED[event_type].items() if on]
    saved = {
        p.channel: p.enabled
        for p in NotificationPreference.unscoped.filter(farm=farm, user=user, event_type=event_type)
    }
    out = []
    for channel in Channel.values:
        default = catalog.default_enabled(event_type, channel) and sign_up_choice(user, channel)
        if saved.get(channel, default):
            out.append(channel)
    return out


def matrix(user: Any, farm: Any) -> list[dict[str, Any]]:
    saved = {
        (p.event_type, p.channel): p.enabled
        for p in NotificationPreference.unscoped.filter(farm=farm, user=user)
    }
    rows = []
    for event in catalog.MATRIX_EVENTS:
        channels = {}
        for channel in Channel.values:
            default = catalog.default_enabled(event, channel) and sign_up_choice(user, channel)
            channels[channel] = saved.get((event, channel), default)
        rows.append({"event_type": event, "label": EventType(event).label, "channels": channels})
    return rows


@transaction.atomic
def save_matrix(user: Any, farm: Any, rows: list[dict[str, Any]]) -> None:
    for row in rows:
        for channel, enabled in row["channels"].items():
            NotificationPreference.unscoped.update_or_create(
                farm=farm,
                user=user,
                event_type=row["event_type"],
                channel=channel,
                defaults={"enabled": bool(enabled)},
            )


# --- Contacts ------------------------------------------------------------------------------------


def contact_for(user: Any, channel: str) -> ChannelContact | None:
    """The person's address for a channel, kept in step with their profile."""
    address = user.email if channel == Channel.EMAIL else user.phone
    verified = user.email_verified if channel == Channel.EMAIL else user.phone_verified
    if not address:
        return None
    contact = ChannelContact.objects.filter(user=user, channel=channel).first()
    if contact is None:
        consent = (
            timezone.now()
            if channel == Channel.WHATSAPP and channel in (user.alert_channels or [])
            else None
        )
        return ChannelContact.objects.create(
            user=user, channel=channel, address=address, verified=verified, opted_in_at=consent
        )
    changed = False
    if contact.address != address:
        # A new number or address starts over: confirm again, consent again.
        contact.address, contact.opted_out_at, contact.bounced_at = address, None, None
        if channel == Channel.WHATSAPP:
            contact.opted_in_at = None
        changed = True
    if contact.verified != verified:
        contact.verified = verified
        changed = True
    if changed:
        contact.save()
    return contact


def unreachable_reason(contact: ChannelContact | None, channel: str) -> str:
    """Why a message cannot go to this contact, or "" if it can."""
    if contact is None:
        return "No email address" if channel == Channel.EMAIL else "No mobile number"
    if not contact.verified:
        return (
            "Email address not confirmed"
            if channel == Channel.EMAIL
            else "Mobile number not confirmed"
        )
    if contact.opted_out_at:
        return "Opted out"
    if contact.bounced_at:
        return "Email bounced"
    if channel == Channel.WHATSAPP and not contact.opted_in_at:
        return "WhatsApp not switched on"
    return ""


# --- Quiet hours ----------------------------------------------------------------------------------


def farm_zone(farm: Any) -> ZoneInfo:
    try:
        return ZoneInfo(farm.timezone)
    except Exception:  # noqa: BLE001
        return ZoneInfo(settings.TIME_ZONE)


def quiet_until(
    prefs: NotificationSettings, farm: Any, now: dt.datetime | None = None
) -> dt.datetime | None:
    """End of the quiet hours if ``now`` falls inside them, else None."""
    if not prefs.quiet_hours_enabled or prefs.quiet_start == prefs.quiet_end:
        return None
    zone = farm_zone(farm)
    local = (now or timezone.now()).astimezone(zone)
    t, start, end = local.time(), prefs.quiet_start, prefs.quiet_end
    inside = (start <= t or t < end) if start > end else (start <= t < end)
    if not inside:
        return None
    day = local.date() if t < end else local.date() + dt.timedelta(days=1)
    return dt.datetime.combine(day, end, tzinfo=zone)


# --- Usage ----------------------------------------------------------------------------------------


def month_start(farm: Any, now: dt.datetime | None = None) -> dt.datetime:
    local = (now or timezone.now()).astimezone(farm_zone(farm))
    return local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def usage(farm: Any) -> dict[str, dict[str, Any]]:
    since = month_start(farm)
    out: dict[str, dict[str, Any]] = {}
    for channel in METERED:
        used = OutboundMessage.unscoped.filter(
            farm=farm,
            channel=channel,
            sent_at__gte=since,
            status__in=[DeliveryStatus.SENT, DeliveryStatus.DELIVERED, DeliveryStatus.READ],
        ).count()
        allowance = (
            farm.sms_monthly_allowance
            if channel == Channel.SMS
            else farm.whatsapp_monthly_allowance
        )
        out[channel] = {"used": used, "allowance": allowance, "month": f"{since:%Y-%m}"}
    out[Channel.EMAIL] = {
        "used": OutboundMessage.unscoped.filter(
            farm=farm, channel=Channel.EMAIL, sent_at__gte=since
        ).count(),
        "allowance": None,
        "month": f"{since:%Y-%m}",
    }
    return out


def check_usage_warning(farm: Farm, channel: str) -> None:
    """Warn administrators once a month when a channel passes 80 % of its allowance."""
    info = usage(farm)[channel]
    if not info["allowance"] or info["used"] < info["allowance"] * WARN_AT:
        return
    farm = Farm.objects.get(pk=farm.pk)
    if (farm.usage_warning_sent or {}).get(channel) == info["month"]:
        return
    farm.usage_warning_sent = {**(farm.usage_warning_sent or {}), channel: info["month"]}
    farm.save(update_fields=["usage_warning_sent", "updated_at"])
    label = Channel(channel).label
    percent = round(info["used"] * 100 / info["allowance"])
    for user in recipients_for(farm, "admins", {}):
        notify(
            user,
            farm,
            EventType.USAGE_WARNING,
            title=f"{label} allowance {percent}% used",
            message=(
                f"{farm.name} has sent {info['used']} of {info['allowance']} {label} messages this month. "
                "Non-urgent messages stop when the allowance is used up."
            ),
            link="/settings?tab=notifications",
            dedupe_key=f"usage.warning:{channel}:{info['month']}",
        )


# --- Recipients -----------------------------------------------------------------------------------


def members(farm: Any, roles: list[str] | None = None) -> list[User]:
    qs = FarmMembership.objects.filter(
        farm=farm, status=MembershipStatus.ACTIVE, user__is_active=True
    )
    if roles:
        qs = qs.filter(role__in=roles)
    return [m.user for m in qs.select_related("user").order_by("joined_at")]


def is_member(farm: Any, user_id: Any) -> User | None:
    m = (
        FarmMembership.objects.filter(
            farm=farm, user_id=user_id, status=MembershipStatus.ACTIVE, user__is_active=True
        )
        .select_related("user")
        .first()
    )
    return m.user if m else None


def recipients_for(
    farm: Any, rule: str, payload: dict[str, Any], activity: Any = None
) -> list[User]:
    managers = lambda: members(farm, [Role.ADMINISTRATOR, Role.FARM_MANAGER])  # noqa: E731
    assignee = (
        is_member(farm, activity.assigned_to_id)
        if activity is not None and activity.assigned_to_id
        else None
    )
    if rule == "admins":
        return members(farm, [Role.ADMINISTRATOR])
    if rule == "managers":
        return managers()
    if rule == "assignee_or_managers":
        return [assignee] if assignee else managers()
    if rule == "assignee_and_managers":
        people = managers()
        if assignee and assignee not in people:
            people.insert(0, assignee)
        return people
    if rule == "recipient":
        user = is_member(farm, payload.get("recipient_id")) if payload.get("recipient_id") else None
        return [user] if user else []
    return []


# --- Creating notifications -----------------------------------------------------------------------


def notify(
    user: Any,
    farm: Any,
    event_type: str,
    *,
    title: str,
    message: str,
    link: str = "",
    urgent: bool = False,
    dedupe_key: str = "",
    related: Any = None,
    quick_reply_activity: Any = None,
    force_channels: list[str] | None = None,
) -> Notification | None:
    """Create the in-app notification and queue the external messages for one person.

    Returns None when the person has every channel switched off, or already got this one."""
    channels = (
        force_channels if force_channels is not None else enabled_channels(user, farm, event_type)
    )
    if not channels:
        return None
    if dedupe_key and Notification.unscoped.filter(recipient=user, dedupe_key=dedupe_key).exists():
        return None
    prefs = settings_for(user, farm)
    lang = prefs.language if prefs.language in ("en", "sw") else "en"
    with farm_context(farm.pk):
        try:
            with transaction.atomic():
                note = Notification.objects.create(
                    farm=farm,
                    recipient=user,
                    event_type=event_type,
                    title=title[:160],
                    message=message,
                    link=link,
                    urgent=urgent,
                    dedupe_key=dedupe_key,
                    show_in_app=Channel.IN_APP in channels,
                    related_type=(
                        ContentType.objects.get_for_model(related) if related is not None else None
                    ),
                    related_id=str(related.pk) if related is not None else "",
                )
        except IntegrityError:  # the same reminder raced in from another worker
            return None
        hold = None if urgent else quiet_until(prefs, farm)
        quick = quick_reply_activity is not None and event_type in catalog.QUICK_REPLY_EVENTS
        for channel in channels:
            if channel not in EXTERNAL_CHANNELS:
                continue
            contact = contact_for(user, channel)
            reason = unreachable_reason(contact, channel)
            payload: dict[str, Any] = {
                "title": note.title,
                "message": message,
                "link": link,
                "farm_name": farm.name,
            }
            if quick:
                payload["activity_id"] = str(quick_reply_activity.pk)
            out = OutboundMessage.objects.create(
                farm=farm,
                notification=note,
                channel=channel,
                to=contact.address if contact else "",
                template=(
                    catalog.WHATSAPP_TEMPLATES.get(event_type, "smartfarm_generic")
                    if channel == Channel.WHATSAPP
                    else event_type
                ),
                payload=payload,
                language=lang,
                status=DeliveryStatus.FAILED if reason else DeliveryStatus.QUEUED,
                error=reason,
                status_at=timezone.now() if reason else None,
                send_after=hold if channel in METERED and not reason else None,
            )
            if not reason and out.send_after is None:
                out_id = out.pk
                after_commit(_deliver_later(str(out_id)))
    if note.show_in_app:
        push_live(user.pk, farm.pk, note)
    return note


def _deliver_later(out_id: str) -> Any:
    return lambda: deliver_outbound.delay(out_id)


def push_live(user_id: Any, farm_id: Any, note: Notification) -> None:
    """Tell the person's open browser tabs (bell badge) straight away."""
    from channels.layers import get_channel_layer

    layer = get_channel_layer()
    if layer is None:
        return
    data = {
        "type": "notification.new",
        "id": str(note.pk),
        "farm_id": str(farm_id),
        "title": note.title,
        "urgent": note.urgent,
    }
    try:
        after_commit(lambda: async_to_sync(layer.group_send)(group_name(user_id), data))
    except Exception:
        logger.exception("Live notification push failed")


def group_name(user_id: Any) -> str:
    return f"notify.{user_id}"


# --- Events ---------------------------------------------------------------------------------------


def _activity(payload: dict[str, Any]) -> Any:
    from apps.calendar.models import Activity

    if not payload.get("activity_id"):
        return None
    return (
        Activity.objects.select_related("farm", "category", "created_by")
        .filter(pk=payload["activity_id"])
        .first()
    )


def handle_event(event_type: str, farm_id: Any, payload: dict[str, Any]) -> int:
    farm = Farm.objects.filter(pk=farm_id).first()
    if farm is None or event_type not in catalog.RECIPIENTS:
        return 0
    sent = 0
    with farm_context(farm.pk):
        activity = _activity(payload)
        if payload.get("activity_id") and activity is None:
            return 0  # deleted meanwhile
        actor_id = payload.get("actor_id")
        actor = User.objects.filter(pk=actor_id).first() if actor_id else None
        for user in recipients_for(farm, catalog.RECIPIENTS[event_type], payload, activity):
            if (
                actor is not None
                and user.pk == actor.pk
                and event_type not in (EventType.HEALTH_ALERT, EventType.TEST)
            ):
                continue
            lang = settings_for(user, farm).language
            if activity is not None and event_type in catalog.TITLES:
                who = ""
                if event_type == EventType.TASK_ASSIGNED:
                    who = (
                        (actor or activity.created_by or user).get_full_name()
                        if (actor or activity.created_by)
                        else ""
                    )
                elif event_type == EventType.ACTIVITY_COMPLETED:
                    who = activity.completed_by.get_full_name() if activity.completed_by_id else ""
                r = catalog.render_activity(event_type, activity, lang, who)
                title, message, link = r.title, r.message, r.link
            else:
                title = payload.get("title") or EventType(event_type).label
                message = payload.get("message") or ""
                link = payload.get("link") or ""
            if not link and payload.get("animal_id"):
                link = f"/livestock/{payload['animal_id']}"
            if not link and event_type == EventType.LOW_STOCK:
                link = "/nutrition"
            note = notify(
                user,
                farm,
                event_type,
                title=title,
                message=message,
                link=link,
                urgent=bool(payload.get("urgent")),
                dedupe_key=payload.get("dedupe_key", ""),
                related=activity,
                quick_reply_activity=activity,
            )
            sent += note is not None
    return sent


@shared_task(name="notifications.dispatch_event")
def dispatch_event(event_type: str, farm_id: str, payload: dict[str, Any]) -> int:
    return handle_event(event_type, farm_id, payload)


def on_domain_event(sender: Any, event_type: str, farm_id: Any, **payload: Any) -> None:
    clean = {
        k: (str(v) if v is not None and not isinstance(v, (bool, int, float, str)) else v)
        for k, v in payload.items()
    }
    after_commit(lambda: dispatch_event.delay(event_type, str(farm_id), clean))


domain_event.connect(on_domain_event, dispatch_uid="notifications.on_domain_event")


# --- Delivery -------------------------------------------------------------------------------------


def build_message(out: OutboundMessage) -> Message:
    p = out.payload
    quick = bool(p.get("activity_id"))
    link = p.get("link", "")
    full_link = f"{settings.FRONTEND_URL.rstrip('/')}{link}" if link else ""
    if out.channel == Channel.SMS:
        text = catalog.sms_text(p.get("title", ""), p.get("message", ""), quick, out.language)
    else:
        text = p.get("message", "")
        if quick and out.channel == Channel.WHATSAPP:
            text = f"{text}\n{catalog.QUICK_REPLY_HINT.get(out.language, catalog.QUICK_REPLY_HINT['en'])}"
    params: dict[str, Any] = {"farm_name": p.get("farm_name", "Smart Farm"), "link": full_link}
    if out.channel == Channel.WHATSAPP:
        params["body"] = [p.get("title", ""), p.get("message", "")]
        if quick:
            params["buttons"] = [f"done:{out.pk}", f"reschedule:{out.pk}"]
    return Message(
        to=out.to,
        template=out.template,
        params=params,
        language=out.language,
        text=text,
        subject=p.get("title", ""),
    )


def over_allowance(out: OutboundMessage) -> bool:
    if out.channel not in METERED or (out.notification is not None and out.notification.urgent):
        return False
    info = usage(out.farm)[out.channel]
    return bool(info["allowance"]) and info["used"] >= info["allowance"]


def deliver_now(out_id: str) -> OutboundMessage | None:
    with transaction.atomic():
        out = (
            OutboundMessage.unscoped.select_for_update(skip_locked=True, of=("self",))
            .select_related("farm", "notification")
            .filter(pk=out_id, status=DeliveryStatus.QUEUED)
            .first()
        )
        if out is None:
            return None
        if out.send_after and out.send_after > timezone.now():
            return out
        if over_allowance(out):
            out.status, out.error, out.status_at = (
                DeliveryStatus.FAILED,
                "Monthly allowance used up",
                timezone.now(),
            )
            out.save(update_fields=["status", "error", "status_at"])
            return out
        out.attempts += 1
        try:
            result = get_adapter(out.channel).send(build_message(out))
        except ProviderError as exc:
            logger.warning("Delivery %s failed (attempt %s): %s", out.pk, out.attempts, exc)
            out.error = str(exc)[:300]
            if exc.retry and out.attempts < MAX_ATTEMPTS:
                out.send_after = timezone.now() + dt.timedelta(minutes=2 ** (out.attempts - 1))
            else:
                out.status, out.status_at = DeliveryStatus.FAILED, timezone.now()
            out.save(update_fields=["error", "send_after", "status", "status_at", "attempts"])
            return out
        now = timezone.now()
        out.status, out.provider_id, out.cost = (
            result.status,
            result.provider_id[:120],
            result.cost[:30],
        )
        out.sent_at = out.status_at = now
        out.error, out.send_after = "", None
        out.save(
            update_fields=[
                "status",
                "provider_id",
                "cost",
                "sent_at",
                "status_at",
                "error",
                "send_after",
                "attempts",
            ]
        )
    if out.channel in METERED:
        with farm_context(out.farm_id):
            check_usage_warning(out.farm, out.channel)
    return out


@shared_task(name="notifications.deliver")
def deliver_outbound(out_id: str) -> str:
    out = deliver_now(out_id)
    return out.status if out else "skipped"


@shared_task(name="notifications.release_due")
def release_due() -> int:
    """Every minute: send messages held for quiet hours and retries that are now due."""
    due = list(
        OutboundMessage.unscoped.filter(status=DeliveryStatus.QUEUED)
        .filter(
            Q(send_after__isnull=True, created_at__lt=timezone.now() - dt.timedelta(minutes=5))
            | Q(send_after__lte=timezone.now())
        )
        .values_list("pk", flat=True)[:500]
    )
    for pk in due:
        deliver_now(str(pk))
    return len(due)


# --- Delivery reports and replies -----------------------------------------------------------------

STATUS_ORDER: list[str] = [
    DeliveryStatus.QUEUED,
    DeliveryStatus.SENT,
    DeliveryStatus.DELIVERED,
    DeliveryStatus.READ,
]


def update_status(channel: str, provider_id: str, status: str, error: str = "") -> bool:
    out = OutboundMessage.unscoped.filter(channel=channel, provider_id=provider_id).first()
    if out is None or not provider_id:
        return False
    if status == DeliveryStatus.FAILED:
        out.status, out.error = DeliveryStatus.FAILED, error[:300] or "Not delivered"
    elif out.status in STATUS_ORDER and STATUS_ORDER.index(status) > STATUS_ORDER.index(out.status):
        out.status = status
    else:
        return True
    out.status_at = timezone.now()
    out.save(update_fields=["status", "error", "status_at"])
    return True


def contact_by_address(channel: str, address: str) -> ChannelContact | None:
    digits = "".join(ch for ch in address if ch.isdigit())
    if not digits:
        return None
    return (
        ChannelContact.objects.filter(channel=channel, address=f"+{digits}")
        .select_related("user")
        .first()
    )


def opt_out(channel: str, address: str) -> bool:
    contact = contact_by_address(channel, address)
    if contact is None:
        return False
    contact.opted_out_at = timezone.now()
    contact.save(update_fields=["opted_out_at", "updated_at"])
    return True


def quick_reply(channel: str, address: str, answer: str, out_id: str | None = None) -> str:
    """'1' / done → mark the activity done; '2' / reschedule → move it to tomorrow.

    Returns what happened, for the reply text and the log."""
    from apps.calendar import services as calendar
    from apps.calendar.models import Activity, ActivityStatus

    contact = contact_by_address(channel, address)
    if contact is None:
        return "unknown_sender"
    qs = OutboundMessage.unscoped.filter(
        notification__recipient=contact.user, payload__has_key="activity_id"
    )
    out = (
        qs.filter(pk=out_id).first()
        if out_id
        else qs.filter(channel=channel).order_by("-created_at").first()
    )
    if out is None or out.created_at < timezone.now() - dt.timedelta(days=7):
        return "nothing_to_answer"
    with farm_context(out.farm_id):
        if not is_member(out.farm, contact.user.pk):
            return "not_member"
        activity = (
            Activity.objects.filter(pk=out.payload["activity_id"]).select_related("farm").first()
        )
        if activity is None:
            return "gone"
        if answer == "done":
            if activity.status in (ActivityStatus.COMPLETED, ActivityStatus.CANCELLED):
                return "already_done"
            calendar.set_status(
                activity,
                ActivityStatus.COMPLETED,
                contact.user,
                f"Marked done by {Channel(channel).label} reply",
            )
            return "done"
        if answer == "reschedule":
            if activity.status in (ActivityStatus.COMPLETED, ActivityStatus.CANCELLED):
                return "already_done"
            activity.date = max(activity.date, calendar.farm_today(activity.farm)) + dt.timedelta(
                days=1
            )
            activity.updated_by = contact.user
            activity.save(update_fields=["date", "updated_by", "updated_at"])
            if activity.status == ActivityStatus.OVERDUE:
                calendar.set_status(
                    activity,
                    ActivityStatus.PENDING,
                    contact.user,
                    f"Rescheduled by {Channel(channel).label} reply",
                )
            return "rescheduled"
    return "unknown_answer"


# --- Test message ---------------------------------------------------------------------------------


def send_test(user: Any, farm: Any, channel: str) -> Notification | None:
    return notify(
        user,
        farm,
        EventType.TEST,
        title="Test message from Smart Farm",
        message=f"This is a test {Channel(channel).label} message for {farm.name}. If you can read it, it works.",
        link="/notifications",
        urgent=True,  # a test should not wait for quiet hours
        force_channels=sorted({Channel.IN_APP, channel}),
    )


# --- Retention ------------------------------------------------------------------------------------

RETENTION_DAYS = 365


@shared_task(name="notifications.purge_old")
def purge_old() -> int:
    """Daily: message logs and notifications are kept for 12 months, then deleted."""
    cutoff = timezone.now() - dt.timedelta(days=RETENTION_DAYS)
    removed, _ = OutboundMessage.unscoped.filter(created_at__lt=cutoff).delete()
    notes, _ = Notification.unscoped.filter(created_at__lt=cutoff).delete()
    return removed + notes
