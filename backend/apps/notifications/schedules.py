"""Scheduled reminders, by each farm's local time. Runs every 15 minutes; dedupe keys make it
safe to run as often as you like (each reminder goes out once).

* 06:00  reminders for activities N days ahead (the activity's "remind me" days), and
         "due today" for today's activities;
* 07:00  overdue activities (once per activity and due date);
* each person's digest time: the daily summary (email by default).
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from celery import shared_task
from django.utils import timezone

from apps.accounts.models import Farm, FarmStatus
from apps.core.context import farm_context

from . import services
from .models import EventType

REMINDER_HOUR = 6
OVERDUE_HOUR = 7


def reminder_event(activity: Any) -> str:
    key = activity.category.key if activity.category_id else ""
    return {
        "vaccination": EventType.VACCINATION_REMINDER,
        "deworming": EventType.DEWORMING_REMINDER,
    }.get(key, EventType.UPCOMING)


def run_for_farm(farm: Farm, now: dt.datetime | None = None) -> int:
    from apps.calendar.models import Activity, ActivityStatus

    local = (now or timezone.now()).astimezone(services.farm_zone(farm))
    today = local.date()
    open_statuses = [ActivityStatus.PENDING, ActivityStatus.IN_PROGRESS]
    sent = 0
    with farm_context(farm.pk):
        if local.hour >= REMINDER_HOUR:
            ahead = (
                Activity.objects.filter(
                    status__in=open_statuses,
                    date__gt=today,
                    date__lte=today + dt.timedelta(days=60),
                )
                .exclude(reminder_days=[])
                .select_related("category")
            )
            for activity in ahead:
                days = (activity.date - today).days
                if days in activity.reminder_days:
                    sent += services.handle_event(
                        reminder_event(activity),
                        farm.pk,
                        {
                            "activity_id": str(activity.pk),
                            "dedupe_key": f"remind:{activity.pk}:{activity.date}:{days}",
                        },
                    )
            for activity in Activity.objects.filter(status__in=open_statuses, date=today):
                sent += services.handle_event(
                    EventType.DUE_TODAY,
                    farm.pk,
                    {
                        "activity_id": str(activity.pk),
                        "dedupe_key": f"due:{activity.pk}:{activity.date}",
                    },
                )
        if local.hour >= OVERDUE_HOUR:
            for activity in Activity.objects.filter(
                status=ActivityStatus.OVERDUE, date__gte=today - dt.timedelta(days=30)
            ):
                sent += services.handle_event(
                    EventType.OVERDUE,
                    farm.pk,
                    {
                        "activity_id": str(activity.pk),
                        "dedupe_key": f"overdue:{activity.pk}:{activity.date}",
                    },
                )
        sent += send_digests(farm, local)
    return sent


def digest_for(farm: Farm, user: Any, today: dt.date, lang: str) -> tuple[str, str] | None:
    from apps.calendar.models import Activity, ActivityStatus
    from apps.core.permissions import role_scope
    from apps.nutrition.models import FeedItem

    membership = user.memberships.filter(farm=farm).first()
    qs = Activity.objects.all()
    if membership and role_scope(membership.role, "activities") == "own":
        qs = qs.filter(assigned_to=user)
    due = qs.filter(
        date=today, status__in=[ActivityStatus.PENDING, ActivityStatus.IN_PROGRESS]
    ).count()
    overdue = qs.filter(status=ActivityStatus.OVERDUE).count()
    week = qs.filter(
        date__gt=today,
        date__lte=today + dt.timedelta(days=7),
        status__in=[ActivityStatus.PENDING, ActivityStatus.IN_PROGRESS],
    ).count()
    low = sum(1 for item in FeedItem.objects.all() if item.is_low)
    if not (due or overdue or week or low):
        return None
    if lang == "sw":
        title = f"Muhtasari wa leo – {farm.name}"
        lines = [f"Kazi za leo: {due}", f"Zilizochelewa: {overdue}", f"Siku 7 zijazo: {week}"]
        if low:
            lines.append(f"Chakula kinachopungua: {low}")
    else:
        title = f"Today at {farm.name}"
        lines = [f"Due today: {due}", f"Overdue: {overdue}", f"Next 7 days: {week}"]
        if low:
            lines.append(f"Feeds running low: {low}")
    return title, "\n".join(lines)


def send_digests(farm: Farm, local: dt.datetime) -> int:
    sent = 0
    for user in services.members(farm):
        prefs = services.settings_for(user, farm)
        if local.time() < prefs.digest_time:
            continue
        if not services.enabled_channels(user, farm, EventType.DAILY_SUMMARY):
            continue
        content = digest_for(farm, user, local.date(), prefs.language)
        if content is None:
            continue
        note = services.notify(
            user,
            farm,
            EventType.DAILY_SUMMARY,
            title=content[0],
            message=content[1],
            link="/activities",
            dedupe_key=f"digest:{farm.pk}:{local.date()}",
        )
        sent += note is not None
    return sent


@shared_task(name="notifications.run_schedules")
def run_schedules() -> int:
    return sum(run_for_farm(farm) for farm in Farm.objects.filter(status=FarmStatus.ACTIVE))
