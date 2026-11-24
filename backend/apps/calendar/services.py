"""Calendar rules: categories, status changes with history, recurrence, overdue marking, the
activities created by health records, and the 2027 health calendar template."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from dateutil.rrule import rrulestr
from django.contrib.contenttypes.models import ContentType
from django.db import models, transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.core.context import farm_context
from apps.notifications.events import emit

from .models import (
    DEFAULT_CATEGORIES,
    OPEN_STATUSES,
    Activity,
    ActivityCategory,
    ActivitySource,
    ActivityStatus,
    ActivityStatusHistory,
    CategoryKey,
    Priority,
)

SERIES_HORIZON_DAYS = 365
MAX_OCCURRENCES = 400

# --- Categories ------------------------------------------------------------------------------------


def seed_categories(farm: Any) -> None:
    for key, colour, icon in DEFAULT_CATEGORIES:
        if not ActivityCategory.unscoped.filter(farm=farm, key=key, deleted_at=None).exists():
            ActivityCategory.unscoped.create(
                farm=farm, key=key, name=key.label, colour=colour, icon=icon
            )


def category(farm_id: Any, key: str) -> ActivityCategory | None:
    return ActivityCategory.unscoped.filter(farm_id=farm_id, key=key, deleted_at=None).first()


def farm_today(farm: Any) -> date:
    try:
        return timezone.now().astimezone(ZoneInfo(farm.timezone)).date()
    except Exception:  # noqa: BLE001 - bad tz string: fall back to the server zone
        return timezone.localdate()


# --- Status changes ----------------------------------------------------------------------------------

ALLOWED = {
    "start": ({ActivityStatus.PENDING, ActivityStatus.OVERDUE}, ActivityStatus.IN_PROGRESS),
    "complete": (
        {ActivityStatus.PENDING, ActivityStatus.IN_PROGRESS, ActivityStatus.OVERDUE},
        ActivityStatus.COMPLETED,
    ),
    "cancel": (
        {ActivityStatus.PENDING, ActivityStatus.IN_PROGRESS, ActivityStatus.OVERDUE},
        ActivityStatus.CANCELLED,
    ),
    "reopen": ({ActivityStatus.COMPLETED, ActivityStatus.CANCELLED}, ActivityStatus.PENDING),
}


def set_status(activity: Activity, to: str, user: Any = None, note: str = "") -> Activity:
    """Changes the status, keeps the history row and the completed_* fields in step."""
    old = activity.status
    if old == to:
        return activity
    activity.status = to
    if to == ActivityStatus.COMPLETED:
        activity.completed_at, activity.completed_by = timezone.now(), user
    elif old == ActivityStatus.COMPLETED:
        activity.completed_at, activity.completed_by = None, None
    activity.save()
    ActivityStatusHistory.unscoped.create(
        farm_id=activity.farm_id,
        activity=activity,
        from_status=old,
        to_status=to,
        note=note[:300],
        created_by=user,
        updated_by=user,
    )
    if (
        to == ActivityStatus.COMPLETED
        and activity.created_by_id
        and activity.created_by_id != getattr(user, "pk", None)
    ):
        emit(
            "activity.completed",
            activity.farm_id,
            activity_id=str(activity.pk),
            recipient_id=str(activity.created_by_id),
            actor_id=str(user.pk) if user is not None else None,
        )
    return activity


def transition(
    activity: Activity, action: str, user: Any, note: str = "", offline_at: Any = None
) -> Activity:
    allowed, to = ALLOWED[action]
    if offline_at is not None:
        # A change made offline and synced later. Repeating it is harmless, and if someone
        # changed the activity meanwhile the latest sync wins ("last write wins"); the history
        # says so either way.
        if activity.status == to:
            return activity
        when = timezone.localtime(offline_at).strftime("%d %b %H:%M")
        conflict = activity.status not in allowed
        extra = f"Done offline at {when}, synced later" + (" (last write wins)" if conflict else "")
        return set_status(activity, to, user, f"{note} – {extra}" if note else extra)
    if activity.status not in allowed:
        raise ValidationError(
            {
                "detail": [
                    f"A {activity.get_status_display().lower()} activity cannot be {action}ed."
                ]
            }
        )
    # Reopening a past-due activity makes it overdue again rather than pending.
    if action == "reopen" and activity.date < farm_today(activity.farm):
        to = ActivityStatus.OVERDUE
    return set_status(activity, to, user, note)


def mark_overdue(farm: Any) -> int:
    """Past-due pending or in-progress activities become Overdue (runs at 00:05 farm time)."""
    today = farm_today(farm)
    count = 0
    with farm_context(farm.pk):
        due = Activity.objects.filter(
            status__in=[ActivityStatus.PENDING, ActivityStatus.IN_PROGRESS], date__lt=today
        ).select_related("farm")
        for activity in due:
            set_status(
                activity, ActivityStatus.OVERDUE, None, "Passed its date without being completed"
            )
            # Reminders about it go out at 07:00 farm time (notifications.run_schedules).
            count += 1
    return count


# --- Recurrence --------------------------------------------------------------------------------------

RULE_PRESETS = {
    "weekly": "FREQ=WEEKLY",
    "monthly": "FREQ=MONTHLY",
    "quarterly": "FREQ=MONTHLY;INTERVAL=3",
    "yearly": "FREQ=YEARLY",
}


def validate_rule(rule: str) -> str:
    rule = rule.strip().upper().removeprefix("RRULE:")
    if not rule:
        return ""
    try:
        rrulestr(rule, dtstart=datetime(2027, 1, 1))
    except (ValueError, TypeError) as exc:
        raise ValidationError({"recurrence_rule": ["This repeat rule is not valid."]}) from exc
    if "FREQ=" not in rule:
        raise ValidationError({"recurrence_rule": ["This repeat rule is not valid."]})
    return rule


def occurrence_dates(rule: str, start: date, after: date, until: date) -> list[date]:
    dates = rrulestr(rule, dtstart=datetime.combine(start, datetime.min.time()))
    found: list[date] = []
    for dt in dates:
        day = dt.date()
        if day > until or len(found) >= MAX_OCCURRENCES:
            break
        if day > after:
            found.append(day)
    return found


def _copy(head: Activity, day: date) -> Activity:
    clone = Activity(
        farm_id=head.farm_id,
        title=head.title,
        category_id=head.category_id,
        date=day,
        start_time=head.start_time,
        end_time=head.end_time,
        all_day=head.all_day,
        assigned_to_id=head.assigned_to_id,
        group_id=head.group_id,
        description=head.description,
        priority=head.priority,
        reminder_days=list(head.reminder_days),
        series=head,
        source=head.source,
        created_by_id=head.created_by_id,
        updated_by_id=head.created_by_id,
    )
    clone.save()
    animal_ids = list(head.animals.values_list("pk", flat=True))
    if animal_ids:
        clone.animals.set(animal_ids)
    return clone


@transaction.atomic
def extend_series(head: Activity) -> int:
    """Creates the series' occurrences up to 12 months ahead of today (or of its start)."""
    if not head.recurrence_rule:
        return 0
    last = head.occurrences.order_by("-date").values_list("date", flat=True).first() or head.date
    horizon = max(head.date, farm_today(head.farm)) + timedelta(days=SERIES_HORIZON_DAYS)
    days = occurrence_dates(head.recurrence_rule, head.date, last, horizon)
    for day in days:
        _copy(head, day)
    return len(days)


def rule_until(rule: str, last_day: date) -> str:
    """The same rule, ending on ``last_day`` (replaces any COUNT or UNTIL)."""
    parts = [p for p in rule.split(";") if p and not p.startswith(("UNTIL=", "COUNT="))]
    return ";".join([*parts, f"UNTIL={last_day:%Y%m%d}"])


def series_head(activity: Activity) -> Activity | None:
    if activity.recurrence_rule:
        return activity
    return activity.series


@transaction.atomic
def update_following(
    activity: Activity, changes: dict[str, Any], animals: list[Any] | None
) -> Activity:
    """ "This and following": changes this occurrence and the open ones after it. A changed date
    shifts them by the same number of days; a changed repeat rule rebuilds them."""
    head = series_head(activity)
    if head is None:
        raise ValidationError({"scope": ["This activity does not repeat."]})
    shift = (changes["date"] - activity.date) if "date" in changes else timedelta(0)
    new_rule = changes.pop("recurrence_rule", None)
    later = Activity.objects.filter(
        models.Q(series=head) | models.Q(pk=head.pk),
        date__gt=activity.date,
        status__in=OPEN_STATUSES,
    ).exclude(pk=activity.pk)

    if new_rule is not None and new_rule != head.recurrence_rule:
        later.delete()
        apply_changes(activity, changes, animals)
        if activity.pk != head.pk:
            # The old series stops before this date; this occurrence starts a new one.
            head.recurrence_rule = rule_until(
                head.recurrence_rule, activity.date - timedelta(days=1)
            )
            head.save()
            activity.series = None
        activity.recurrence_rule = new_rule
        activity.save()
        extend_series(activity)
        return activity

    apply_changes(activity, changes, animals)
    for occ in later:
        occ_changes = {k: v for k, v in changes.items() if k != "date"}
        if shift:
            occ_changes["date"] = occ.date + shift
        apply_changes(occ, occ_changes, animals)
    return activity


def apply_changes(activity: Activity, changes: dict[str, Any], animals: list[Any] | None) -> None:
    for key, value in changes.items():
        setattr(activity, key, value)
    activity.save()
    if animals is not None:
        activity.animals.set(animals)


# --- Activities created by health records --------------------------------------------------------------

LINKS: dict[str, tuple[str, str, list[int]]] = {
    # model name: (category key, activity source, reminder days)
    "vaccination": (CategoryKey.VACCINATION, ActivitySource.VACCINATION, [7, 1]),
    "deworming": (CategoryKey.DEWORMING, ActivitySource.DEWORMING, [7, 1]),
    "parasitecontrol": (CategoryKey.PARASITE_CONTROL, ActivitySource.HEALTH, [3, 1]),
    "treatment": (CategoryKey.TREATMENT, ActivitySource.TREATMENT, [1]),
    "vetvisit": (CategoryKey.VET_VISIT, ActivitySource.HEALTH, [3, 1]),
    "healthinspection": (CategoryKey.INSPECTION, ActivitySource.HEALTH, [3, 1]),
    "nutritionassessment": (CategoryKey.FEEDING, ActivitySource.HEALTH, [3, 1]),
}


def linked_activities(record: models.Model) -> models.QuerySet[Activity]:
    ct = ContentType.objects.get_for_model(type(record))
    return Activity.unscoped.filter(
        source_type=ct, source_id=str(record.pk), deleted_at__isnull=True
    )


def sync_linked_activity(
    record: Any, title: str, animals: list[Any] | None = None, group: Any = None
) -> Activity | None:
    """A record with a next/follow-up date keeps one open calendar activity on that date.

    Changing the date moves it; clearing the date or deleting the record removes it. An activity
    that was already completed or cancelled is left alone as history.
    """
    due = getattr(record, record.NEXT_DATE_FIELD) if record.NEXT_DATE_FIELD else None
    existing = linked_activities(record).filter(status__in=OPEN_STATUSES).first()
    if record.deleted_at is not None or due is None:
        if existing:
            existing.delete()
        return None
    key, source, reminders = LINKS[type(record).__name__.lower()]
    today = farm_today(record.farm)
    status = ActivityStatus.OVERDUE if due < today else ActivityStatus.PENDING
    if existing:
        existing.date, existing.title = due, title
        if existing.status in (ActivityStatus.PENDING, ActivityStatus.OVERDUE):
            existing.status = status
        existing.save()
        activity = existing
    else:
        activity = Activity(
            farm_id=record.farm_id,
            title=title,
            category=category(record.farm_id, key),
            date=due,
            priority=(
                Priority.HIGH
                if key in (CategoryKey.VACCINATION, CategoryKey.TREATMENT)
                else Priority.MEDIUM
            ),
            status=status,
            reminder_days=reminders,
            source=source,
            source_type=ContentType.objects.get_for_model(type(record)),
            source_id=str(record.pk),
            group=group,
            created_by_id=record.created_by_id,
            updated_by_id=record.created_by_id,
        )
        activity.save()
    if animals is not None:
        activity.animals.set(animals)
    return activity


# --- 2027 health calendar template -----------------------------------------------------------------------

VAC, DEW, PAR, TRT, VET, INS, BRD, FED = (
    CategoryKey.VACCINATION,
    CategoryKey.DEWORMING,
    CategoryKey.PARASITE_CONTROL,
    CategoryKey.TREATMENT,
    CategoryKey.VET_VISIT,
    CategoryKey.INSPECTION,
    CategoryKey.BREEDING,
    CategoryKey.FEEDING,
)
H, M, L = Priority.HIGH, Priority.MEDIUM, Priority.LOW

# (key, date, title, category, priority, description). 23 planned activities for 2027.
HEALTH_CALENDAR_2027: list[tuple[str, str, str, str, str, str]] = [
    (
        "2027-01-opening-assessment",
        "2027-01-05",
        "Opening herd health assessment",
        INS,
        H,
        "Check every animal: body condition, eyes (FAMACHA), feet, udder, coat. Update records.",
    ),
    (
        "2027-01-deworming",
        "2027-01-12",
        "Deworming – whole herd",
        DEW,
        H,
        "Deworm all animals over 3 months. Weigh first so the dose is right.",
    ),
    (
        "2027-01-weighing",
        "2027-01-19",
        "Weighing and body condition scoring",
        INS,
        M,
        "Weigh all animals and record body condition scores.",
    ),
    (
        "2027-02-clostridial",
        "2027-02-09",
        "Clostridial (enterotoxaemia) vaccination – whole herd",
        VAC,
        H,
        "Annual clostridial vaccination. Kids get two doses 4 weeks apart.",
    ),
    (
        "2027-02-hoof-trimming",
        "2027-02-23",
        "Hoof trimming and foot-rot check",
        TRT,
        M,
        "Trim all adult hooves; treat and isolate foot-rot cases.",
    ),
    (
        "2027-03-ppr",
        "2027-03-09",
        "PPR vaccination – kids and new stock",
        VAC,
        H,
        "PPR vaccine for animals not yet vaccinated (protection lasts about 3 years).",
    ),
    (
        "2027-03-tick-control",
        "2027-03-23",
        "Tick control – spraying or dipping",
        PAR,
        M,
        "Spray or dip the whole herd before the long rains.",
    ),
    (
        "2027-04-deworming",
        "2027-04-06",
        "Deworming – long-rains round",
        DEW,
        H,
        "Worm burden rises in the rains. Check FAMACHA scores and deworm.",
    ),
    (
        "2027-04-prebreeding-exam",
        "2027-04-20",
        "Pre-breeding examination of does and bucks",
        VET,
        M,
        "Vet checks breeding condition, testicles and udders before the season.",
    ),
    (
        "2027-05-ccpp",
        "2027-05-11",
        "CCPP vaccination – whole herd",
        VAC,
        H,
        "Contagious caprine pleuropneumonia vaccination.",
    ),
    (
        "2027-05-buck-introduction",
        "2027-05-25",
        "Breeding season starts – introduce bucks",
        BRD,
        M,
        "Record matings so expected kidding dates are tracked.",
    ),
    (
        "2027-06-goat-pox",
        "2027-06-08",
        "Goat pox vaccination",
        VAC,
        H,
        "Annual goat pox vaccination.",
    ),
    (
        "2027-06-midyear-inspection",
        "2027-06-22",
        "Mid-year herd health inspection",
        INS,
        M,
        "Repeat the herd assessment and compare with January.",
    ),
    (
        "2027-07-deworming",
        "2027-07-06",
        "Deworming – mid-year round",
        DEW,
        H,
        "Deworm based on FAMACHA scores; rotate the dewormer class.",
    ),
    (
        "2027-07-pregnancy-scanning",
        "2027-07-20",
        "Pregnancy scanning",
        BRD,
        M,
        "Scan does served in May–June; update pregnancy status.",
    ),
    (
        "2027-08-anthrax",
        "2027-08-10",
        "Anthrax vaccination",
        VAC,
        H,
        "Annual anthrax vaccination (required in high-risk areas).",
    ),
    (
        "2027-08-mange-tick-control",
        "2027-08-24",
        "Tick and mange control",
        PAR,
        M,
        "Spray or dip; check for mange and lice.",
    ),
    (
        "2027-09-vet-review",
        "2027-09-14",
        "Vet visit – quarterly herd review",
        VET,
        M,
        "Review treatments, mortality and vaccination coverage with the vet.",
    ),
    (
        "2027-09-feed-review",
        "2027-09-28",
        "Feed and mineral review before the dry season",
        FED,
        M,
        "Check feed stock, plan hay and supplements, refill mineral licks.",
    ),
    (
        "2027-10-deworming",
        "2027-10-12",
        "Deworming – short-rains round",
        DEW,
        H,
        "Deworm ahead of the short rains.",
    ),
    (
        "2027-10-kidding-preparation",
        "2027-10-26",
        "Kidding preparation",
        BRD,
        M,
        "Clean and disinfect kid pens; stock iodine, colostrum and kidding supplies.",
    ),
    (
        "2027-11-brucellosis",
        "2027-11-16",
        "Brucellosis screening",
        VET,
        H,
        "Blood test breeding stock; separate any reactors.",
    ),
    (
        "2027-12-health-planning",
        "2027-12-07",
        "Annual health review and 2028 health planning",
        INS,
        M,
        "Review the year and plan next year's vaccinations, deworming and breeding.",
    ),
]

TEMPLATES = {
    "health-calendar-2027": {
        "name": "2027 health calendar",
        "description": "23 planned health activities for a goat farm in Kenya, from the opening herd assessment in January to health planning in December.",
        "items": HEALTH_CALENDAR_2027,
    }
}


@transaction.atomic
def apply_template(farm: Any, key: str, user: Any) -> tuple[int, int]:
    """Adds the template's activities. Safe to apply twice: existing items are skipped."""
    template = TEMPLATES.get(key)
    if template is None:
        raise ValidationError({"detail": ["Unknown template."]})
    today = farm_today(farm)
    created = skipped = 0
    for item_key, day, title, cat, priority, description in template["items"]:
        if Activity.objects.filter(template_key=item_key).exists():
            skipped += 1
            continue
        when = date.fromisoformat(day)
        Activity.objects.create(
            farm=farm,
            title=title,
            category=category(farm.pk, cat),
            date=when,
            priority=priority,
            description=description,
            source=ActivitySource.TEMPLATE,
            template_key=item_key,
            reminder_days=[3, 1],
            status=ActivityStatus.OVERDUE if when < today else ActivityStatus.PENDING,
            created_by=user,
            updated_by=user,
        )
        created += 1
    return created, skipped


@transaction.atomic
def delete_with_scope(activity: Activity, scope: str) -> int:
    """Delete one occurrence, or this and the open ones after it."""
    head = series_head(activity)
    if scope != "following" or head is None:
        activity.delete()
        return 1
    later = Activity.objects.filter(
        models.Q(series=head) | models.Q(pk=head.pk),
        date__gte=activity.date,
        status__in=OPEN_STATUSES,
    )
    count = later.count()
    if head.pk != activity.pk:
        head.recurrence_rule = rule_until(head.recurrence_rule, activity.date - timedelta(days=1))
        head.save()
    later.delete()
    return count
