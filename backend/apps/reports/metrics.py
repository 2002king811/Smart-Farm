"""Shared figures. The dashboard and the reports both count through these functions, so the
same period always gives the same numbers.

Every function runs inside a farm context (the request's, or ``farm_context`` in jobs)."""

from __future__ import annotations

import calendar
import datetime as dt
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from django.db.models import Count, Q, QuerySet, Sum
from django.db.models.functions import TruncDay, TruncMonth, TruncWeek

from apps.breeding.models import Birth, Mating, MatingStatus, Mortality
from apps.calendar.models import Activity, ActivityStatus
from apps.health.models import (
    Deworming,
    HealthObservation,
    Severity,
    Treatment,
    Vaccination,
    VetVisit,
)
from apps.livestock.models import NEEDS_ATTENTION, Animal, HealthStatus, Sex
from apps.livestock.services import age_band_bounds

OPEN = [ActivityStatus.PENDING, ActivityStatus.IN_PROGRESS]


@dataclass(frozen=True)
class Period:
    start: dt.date
    end: dt.date  # inclusive

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    def label(self) -> str:
        if self.start == self.end:
            return f"{self.start:%d %b %Y}"
        return f"{self.start:%d %b %Y} – {self.end:%d %b %Y}"


def month_period(day: dt.date) -> Period:
    last = calendar.monthrange(day.year, day.month)[1]
    return Period(day.replace(day=1), day.replace(day=last))


def quarter_period(day: dt.date) -> Period:
    first_month = 3 * ((day.month - 1) // 3) + 1
    start = day.replace(month=first_month, day=1)
    end_month = first_month + 2
    return Period(
        start, start.replace(month=end_month, day=calendar.monthrange(day.year, end_month)[1])
    )


def year_period(day: dt.date) -> Period:
    return Period(dt.date(day.year, 1, 1), dt.date(day.year, 12, 31))


def months_back(today: dt.date, months: int) -> Period:
    """The last ``months`` calendar months, ending with the current one."""
    y, m = today.year, today.month - (months - 1)
    while m <= 0:
        m += 12
        y -= 1
    return Period(dt.date(y, m, 1), month_period(today).end)


# --- Herd -----------------------------------------------------------------------------------------


def herd(on: dt.date | None = None) -> dict[str, int]:
    """Active animals now: the register's and the dashboard's stat cards."""
    animals = Animal.objects.filter(is_active=True)
    kid_born_after, _ = age_band_bounds("kid", on)
    return animals.aggregate(
        total=Count("pk"),
        males=Count("pk", filter=Q(sex=Sex.MALE)),
        females=Count("pk", filter=Q(sex=Sex.FEMALE)),
        kids=Count("pk", filter=Q(date_of_birth__gte=kid_born_after)),
        needing_attention=Count("pk", filter=Q(health_status__in=NEEDS_ATTENTION)),
        pregnant=Count("pk", filter=Q(health_status=HealthStatus.PREGNANT)),
    )


def health_status_counts() -> dict[str, int]:
    rows = (
        Animal.objects.filter(is_active=True).values_list("health_status").annotate(n=Count("pk"))
    )
    counts = dict.fromkeys(HealthStatus.values, 0)
    counts.update(dict(rows))
    return counts


def herd_size_on(day: dt.date) -> int:
    """Animals on the farm at the end of ``day``: arrived (born, bought) by then, not yet left."""
    arrived = (
        Q(acquisition_date__lte=day)
        | Q(acquisition_date__isnull=True, date_of_birth__lte=day)
        | Q(acquisition_date__isnull=True, date_of_birth__isnull=True, created_at__date__lte=day)
    )
    still_here = Q(exit_date__isnull=True) | Q(exit_date__gt=day)
    return Animal.objects.filter(arrived & still_here).count()


# --- Period figures -------------------------------------------------------------------------------


def _in(qs: QuerySet[Any], p: Period, field: str = "date") -> QuerySet[Any]:
    return qs.filter(**{f"{field}__range": (p.start, p.end)})


def vaccinations(p: Period) -> QuerySet[Vaccination]:
    return _in(Vaccination.objects.all(), p)


def dewormings(p: Period) -> QuerySet[Deworming]:
    return _in(Deworming.objects.all(), p)


def treatments(p: Period) -> QuerySet[Treatment]:
    return _in(Treatment.objects.all(), p)


def observations(p: Period) -> QuerySet[HealthObservation]:
    return _in(HealthObservation.objects.all(), p)


def vet_visits(p: Period) -> QuerySet[VetVisit]:
    return _in(VetVisit.objects.all(), p)


def births(p: Period) -> QuerySet[Birth]:
    return _in(Birth.objects.all(), p)


def deaths(p: Period) -> QuerySet[Mortality]:
    return _in(Mortality.objects.all(), p)


def matings(p: Period) -> QuerySet[Mating]:
    return _in(Mating.objects.all(), p)


def activities(p: Period) -> QuerySet[Activity]:
    return _in(Activity.objects.all(), p)


def kids_born_alive(p: Period) -> int:
    return Birth.kids.through.objects.filter(
        birth__in=births(p).values("pk"), birth__deleted_at__isnull=True
    ).count()


def stillborn(p: Period) -> int:
    return births(p).aggregate(n=Sum("stillborn_count"))["n"] or 0


def health_counts(p: Period) -> dict[str, int]:
    """The health figures used by the dashboard, the quarterly and the annual report."""
    obs = observations(p)
    return {
        "vaccinations": vaccinations(p).count(),
        "dewormings": dewormings(p).count(),
        "treatments": treatments(p).count(),
        "observations": obs.count(),
        "severe_cases": obs.filter(
            Q(severity=Severity.SEVERE) | Q(temperature_c__gte=HealthObservation.FEVER_C)
        ).count(),
        "vet_visits": vet_visits(p).count(),
        "births": births(p).count(),
        "kids_born": kids_born_alive(p),
        "deaths": deaths(p).count(),
    }


def activity_counts(p: Period, qs: QuerySet[Activity] | None = None) -> dict[str, Any]:
    """Activity overview: the dashboard card and the monthly activities report."""
    qs = activities(p) if qs is None else qs
    counts = qs.aggregate(
        total=Count("pk"),
        completed=Count("pk", filter=Q(status=ActivityStatus.COMPLETED)),
        pending=Count("pk", filter=Q(status__in=OPEN)),
        overdue=Count("pk", filter=Q(status=ActivityStatus.OVERDUE)),
        cancelled=Count("pk", filter=Q(status=ActivityStatus.CANCELLED)),
    )
    due = counts["total"] - counts["cancelled"]
    counts["completion_rate"] = round(counts["completed"] * 100 / due) if due else 0
    return counts


def breeding_counts(p: Period) -> dict[str, Any]:
    qs = matings(p)
    counts = qs.aggregate(
        matings=Count("pk"),
        confirmed=Count("pk", filter=Q(pregnancy_status="confirmed")),
        kidded=Count("pk", filter=Q(status=MatingStatus.KIDDED)),
        failed=Count("pk", filter=Q(status__in=[MatingStatus.FAILED, MatingStatus.ABORTED])),
    )
    scanned = qs.exclude(pregnancy_status="awaiting_scan").count()
    succeeded = qs.filter(Q(pregnancy_status="confirmed") | Q(status=MatingStatus.KIDDED)).count()
    counts["conception_rate"] = round(succeeded * 100 / scanned) if scanned else 0
    return counts


# --- Series for charts ----------------------------------------------------------------------------

TRUNC = {"day": TruncDay, "week": TruncWeek, "month": TruncMonth}


def buckets(p: Period, group: str) -> list[dt.date]:
    """Start date of each day / week (Monday) / month in the period."""
    out: list[dt.date] = []
    if group == "day":
        d = p.start
        while d <= p.end:
            out.append(d)
            d += dt.timedelta(days=1)
    elif group == "week":
        d = p.start - dt.timedelta(days=p.start.weekday())
        while d <= p.end:
            out.append(d)
            d += dt.timedelta(days=7)
    else:
        d = p.start.replace(day=1)
        while d <= p.end:
            out.append(d)
            d = (d.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    return out


def bucket_label(d: dt.date, group: str) -> str:
    return {"day": f"{d:%d %b}", "week": f"Wk {d:%d %b}", "month": f"{d:%b %Y}"}[group]


def series(
    qs: QuerySet[Any],
    p: Period,
    group: str,
    field: str = "date",
    value: Callable[[Any], Any] | None = None,
) -> list[int]:
    """Counts per bucket (or a custom aggregate via ``value``)."""
    trunc = TRUNC[group]
    rows = (
        _in(qs, p, field)
        .annotate(b=trunc(field))
        .values("b")
        .annotate(n=value() if value else Count("pk"))  # type: ignore[call-arg]
        .values_list("b", "n")
    )
    found = {(b.date() if isinstance(b, dt.datetime) else b): n or 0 for b, n in rows}
    return [int(found.get(b, 0)) for b in buckets(p, group)]


def kids_series(p: Period, group: str) -> list[int]:
    through = Birth.kids.through.objects.filter(
        birth__in=births(p).values("pk"), birth__deleted_at__isnull=True
    )
    trunc = TRUNC[group]
    rows = (
        through.annotate(b=trunc("birth__date"))  # type: ignore[misc]
        .values("b")
        .annotate(n=Count("pk"))
        .values_list("b", "n")
    )
    found = {(b.date() if isinstance(b, dt.datetime) else b): n for b, n in rows}
    return [found.get(b, 0) for b in buckets(p, group)]


def auto_group(p: Period) -> str:
    if p.days <= 31:
        return "day" if p.days <= 14 else "week"
    return "month"
