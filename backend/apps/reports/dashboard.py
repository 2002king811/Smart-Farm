"""Dashboard figures. Staff see the whole farm; attendants see their own tasks and alerts.

All counts come from metrics.py, the same functions the reports use."""

from __future__ import annotations

import datetime as dt
from typing import Any

from django.utils import timezone

from apps.calendar.models import Activity, ActivityStatus
from apps.calendar.services import farm_today
from apps.health.models import HealthObservation, Treatment, Vaccination
from apps.notifications.models import Notification
from apps.nutrition.models import FeedItem

from . import metrics as m
from .metrics import Period


def summary(farm: Any, user: Any, own: bool, period: Period) -> dict[str, Any]:
    today = farm_today(farm)
    tasks = Activity.objects.filter(assigned_to=user) if own else Activity.objects.all()
    unread = Notification.objects.filter(recipient=user, show_in_app=True, read_at__isnull=True)
    base = {
        "own": own,
        "today": today,
        "from": period.start,
        "to": period.end,
        "period_label": period.label(),
        "tasks_today": tasks.filter(date=today, status__in=m.OPEN).count(),
        "overdue": tasks.filter(status=ActivityStatus.OVERDUE).count(),
        "unread_alerts": unread.count(),
        "urgent_alerts": unread.filter(urgent=True).count(),
        "activity_overview": m.activity_counts(
            period, m.activities(period).filter(assigned_to=user) if own else None
        ),
    }
    if own:
        return base
    return {
        **base,
        "herd": m.herd(),
        "health_status": m.health_status_counts(),
        "health": m.health_counts(period),
        "low_stock": sum(1 for item in FeedItem.objects.all() if item.is_low),
    }


def charts(farm: Any, months: int) -> dict[str, Any]:
    period = m.months_back(farm_today(farm), months)
    starts = m.buckets(period, "month")
    labels = [m.bucket_label(b, "month") for b in starts]
    herd_size = [m.herd_size_on(min(m.month_period(b).end, farm_today(farm))) for b in starts]
    return {
        "from": period.start,
        "to": period.end,
        "labels": labels,
        "herd_size": herd_size,
        "kids_born": m.kids_series(period, "month"),
        "deaths": m.series(m.deaths(period), period, "month"),
        "vaccinations": m.series(m.vaccinations(period), period, "month"),
        "dewormings": m.series(m.dewormings(period), period, "month"),
        "treatments": m.series(m.treatments(period), period, "month"),
        "activities_completed": m.series(
            m.activities(period).filter(status=ActivityStatus.COMPLETED), period, "month"
        ),
    }


def upcoming(farm: Any, user: Any, own: bool, days: int = 7) -> list[dict[str, Any]]:
    today = farm_today(farm)
    qs = Activity.objects.filter(
        status__in=[*m.OPEN, ActivityStatus.OVERDUE], date__lte=today + dt.timedelta(days=days)
    ).exclude(status=ActivityStatus.OVERDUE, date__lt=today - dt.timedelta(days=60))
    if own:
        qs = qs.filter(assigned_to=user)
    qs = (
        qs.select_related("category", "assigned_to")
        .prefetch_related("animals")
        .order_by("date", "start_time")[:12]
    )
    return [
        {
            "id": str(a.pk),
            "title": a.title,
            "date": a.date,
            "start_time": a.start_time,
            "status": a.status,
            "priority": a.priority,
            "category": (
                {"name": a.category.name, "colour": a.category.colour, "key": a.category.key}
                if a.category_id
                else None
            ),
            "assigned_to": a.assigned_to.full_name if a.assigned_to_id else None,
            "animals": [x.animal_id for x in a.animals.all()][:5],
        }
        for a in qs
    ]


def recent_health(limit: int = 8) -> list[dict[str, Any]]:
    since = timezone.localdate() - dt.timedelta(days=60)
    items: list[dict[str, Any]] = []
    for o in (
        HealthObservation.objects.filter(date__gte=since)
        .select_related("animal")
        .order_by("-date", "-created_at")[:limit]
    ):
        items.append(
            {
                "id": str(o.pk),
                "kind": "observation",
                "date": o.date,
                "animal": o.animal.animal_id,
                "animal_pk": str(o.animal_id),
                "title": f"{o.get_severity_display()} – {o.symptoms[:80]}",
                "status": o.severity,
                "created_at": o.created_at,
            }
        )
    for t in (
        Treatment.objects.filter(date__gte=since)
        .select_related("animal")
        .order_by("-date", "-created_at")[:limit]
    ):
        items.append(
            {
                "id": str(t.pk),
                "kind": "treatment",
                "date": t.date,
                "animal": t.animal.animal_id,
                "animal_pk": str(t.animal_id),
                "title": f"Treatment: {t.diagnosis or t.medication_name}",
                "status": t.status,
                "created_at": t.created_at,
            }
        )
    for v in (
        Vaccination.objects.filter(date__gte=since)
        .select_related("animal", "group")
        .order_by("-date", "-created_at")[:limit]
    ):
        items.append(
            {
                "id": str(v.pk),
                "kind": "vaccination",
                "date": v.date,
                "animal": (
                    v.animal.animal_id
                    if v.animal_id
                    else (f"Group: {v.group.name}" if v.group_id else "")
                ),
                "animal_pk": str(v.animal_id) if v.animal_id else None,
                "title": f"Vaccination: {v.vaccine_name}",
                "status": v.status,
                "created_at": v.created_at,
            }
        )
    items.sort(key=lambda i: (i["date"], i["created_at"]), reverse=True)
    for i in items:
        i.pop("created_at")
    return items[:limit]
