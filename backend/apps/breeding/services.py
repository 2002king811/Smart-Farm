"""Breeding rules: matings and their calendar tasks, pregnancy results, births that create kids,
deaths, derived pregnancy progress, kid growth and the animal timeline."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.calendar.models import (
    OPEN_STATUSES,
    Activity,
    ActivitySource,
    ActivityStatus,
    CategoryKey,
    Priority,
)
from apps.calendar.services import category, farm_today, set_status
from apps.livestock.models import (
    KID_AGE_MONTHS,
    AcquisitionSource,
    Animal,
    AnimalGroup,
    BreedingStatus,
    ExitReason,
    HealthStatus,
    Sex,
    WeightRecord,
)
from apps.livestock.services import TIMELINE_SOURCES, TimelineEvent, _as_datetime, next_animal_id
from apps.notifications.events import emit

from .models import (
    GESTATION_DAYS,
    Birth,
    BirthType,
    Mating,
    MatingStatus,
    Mortality,
    PregnancyStatus,
)

SCAN_AFTER_DAYS = 35

# --- Calendar tasks for a mating ---------------------------------------------------------------------


def _mating_task(mating: Mating, kind: str) -> Activity | None:
    ct = ContentType.objects.get_for_model(Mating)
    return Activity.objects.filter(
        source_type=ct, source_id=str(mating.pk), template_key=kind
    ).first()


def _sync_task(
    mating: Mating, kind: str, due: date | None, title: str, reminders: list[int]
) -> None:
    task = _mating_task(mating, kind)
    if due is None:
        if task and task.status in OPEN_STATUSES:
            task.delete()
        return
    status = ActivityStatus.OVERDUE if due < farm_today(mating.farm) else ActivityStatus.PENDING
    if task is None:
        task = Activity.objects.create(
            farm_id=mating.farm_id,
            title=title,
            category=category(mating.farm_id, CategoryKey.BREEDING),
            date=due,
            priority=Priority.HIGH if kind == "kidding" else Priority.MEDIUM,
            status=status,
            reminder_days=reminders,
            source=ActivitySource.BREEDING,
            source_type=ContentType.objects.get_for_model(Mating),
            source_id=str(mating.pk),
            template_key=kind,
            created_by_id=mating.created_by_id,
            updated_by_id=mating.created_by_id,
        )
        task.animals.set([mating.doe])
    elif task.status in OPEN_STATUSES:
        task.title, task.date = title, due
        if task.status != ActivityStatus.IN_PROGRESS:
            task.status = status
        task.save()


def _complete_task(mating: Mating, kind: str, user: Any, note: str) -> None:
    task = _mating_task(mating, kind)
    if task and task.status in OPEN_STATUSES:
        set_status(task, ActivityStatus.COMPLETED, user, note)


def sync_mating_tasks(mating: Mating) -> None:
    doe = mating.doe.animal_id
    scan_due = (
        mating.date + timedelta(days=SCAN_AFTER_DAYS)
        if mating.pregnancy_status == PregnancyStatus.AWAITING_SCAN
        and mating.status == MatingStatus.ACTIVE
        else None
    )
    _sync_task(mating, "scan", scan_due, f"Pregnancy scan – {doe}", [3, 1])
    kidding_due = (
        mating.expected_kidding_date
        if mating.status == MatingStatus.ACTIVE
        and mating.pregnancy_status != PregnancyStatus.NOT_PREGNANT
        else None
    )
    _sync_task(mating, "kidding", kidding_due, f"Expected kidding – {doe}", [7, 1])


# --- Mating lifecycle --------------------------------------------------------------------------------


def validate_pair(doe: Animal, buck: Animal | None, ai_straw: str) -> None:
    errors: dict[str, str] = {}
    if doe.sex != Sex.FEMALE:
        errors["doe"] = "Choose a female."
    elif not doe.is_active:
        errors["doe"] = "This animal is no longer in the herd."
    if buck is not None:
        if buck.sex != Sex.MALE:
            errors["buck"] = "Choose a male."
        elif buck.species != doe.species:
            errors["buck"] = "The buck must be the same species."
    elif not ai_straw:
        errors["buck"] = "Choose the buck, or give the AI straw details."
    if errors:
        raise ValidationError(errors)


@transaction.atomic
def after_mating_saved(
    mating: Mating, created: bool, previous: dict[str, Any] | None, user: Any
) -> None:
    doe = Animal.objects.select_for_update().get(pk=mating.doe_id)
    before = previous or {}
    changed = lambda f: before.get(f) != getattr(mating, f)  # noqa: E731

    if (
        created
        and mating.status == MatingStatus.ACTIVE
        and doe.breeding_status
        in (BreedingStatus.OPEN, BreedingStatus.DRY, BreedingStatus.LACTATING)
    ):
        doe.breeding_status = BreedingStatus.SERVED
    if changed("pregnancy_status") or created:
        if mating.pregnancy_status == PregnancyStatus.CONFIRMED:
            if mating.scan_date is None:
                Mating.objects.filter(pk=mating.pk).update(scan_date=timezone.localdate())
            doe.breeding_status = BreedingStatus.PREGNANT
            if doe.health_status == HealthStatus.HEALTHY:
                doe.health_status = HealthStatus.PREGNANT
            _complete_task(mating, "scan", user, "Pregnancy confirmed")
        elif mating.pregnancy_status == PregnancyStatus.NOT_PREGNANT:
            if mating.status == MatingStatus.ACTIVE:
                Mating.objects.filter(pk=mating.pk).update(status=MatingStatus.FAILED)
                mating.status = MatingStatus.FAILED
            _reset_doe(doe)
            _complete_task(mating, "scan", user, "Not pregnant")
    if changed("status") and mating.status in (MatingStatus.ABORTED, MatingStatus.FAILED):
        _reset_doe(doe)
    doe.save()
    sync_mating_tasks(mating)


def _reset_doe(doe: Animal) -> None:
    doe.breeding_status = BreedingStatus.OPEN
    if doe.health_status == HealthStatus.PREGNANT:
        doe.health_status = HealthStatus.HEALTHY


# --- Births ------------------------------------------------------------------------------------------

BIRTH_TYPES = {
    1: BirthType.SINGLE,
    2: BirthType.TWINS,
    3: BirthType.TRIPLETS,
    4: BirthType.QUADRUPLETS,
}


@transaction.atomic
def record_birth(farm: Any, user: Any, data: dict[str, Any], kids: list[dict[str, Any]]) -> Birth:
    """Creates the birth, one Animal per live kid (with its first weight), and closes the mating."""
    dam: Animal = data["dam"]
    mating: Mating | None = data.get("mating")
    if dam.sex != Sex.FEMALE:
        raise ValidationError({"dam": ["Choose a female."]})
    if not kids:
        raise ValidationError({"kids": ["Add at least one kid."]})
    if mating is not None:
        if mating.doe_id != dam.pk:
            raise ValidationError({"mating": ["This mating is for another doe."]})
        if mating.status != MatingStatus.ACTIVE:
            raise ValidationError({"mating": ["This mating is already closed."]})
    if mating is None:
        mating = (
            Mating.objects.filter(doe=dam, status=MatingStatus.ACTIVE).order_by("-date").first()
        )
    sire = data.get("sire") or (mating.buck if mating else None)
    day: date = data.get("date") or timezone.localdate()

    birth = Birth.objects.create(
        farm=farm,
        mating=mating,
        dam=dam,
        sire=sire,
        date=day,
        birth_type=data.get("birth_type") or BIRTH_TYPES.get(len(kids), BirthType.QUADRUPLETS),
        condition=data.get("condition", "normal"),
        notes=data.get("notes", ""),
        created_by=user,
        updated_by=user,
    )
    kids_group = AnimalGroup.objects.filter(name__iexact="Kids").first()
    live = []
    for kid in kids:
        if not kid.get("alive", True):
            birth.stillborn_count += 1
            continue
        animal_id = (kid.get("animal_id") or "").strip().upper() or next_animal_id(farm)
        if Animal.objects.filter(animal_id__iexact=animal_id).exists():
            raise ValidationError(
                {"kids": [f"The animal ID {animal_id} is already used on this farm."]}
            )
        tag = (kid.get("ear_tag") or "").strip().upper()
        if tag and Animal.objects.filter(ear_tag__iexact=tag).exists():
            raise ValidationError({"kids": [f"The ear tag {tag} is already used on this farm."]})
        animal = Animal.objects.create(
            farm=farm,
            animal_id=animal_id,
            ear_tag=tag,
            name=kid.get("name", ""),
            sex=kid["sex"],
            species=dam.species,
            breed=dam.breed if not sire or sire.breed == dam.breed else "Crossbreed",
            date_of_birth=day,
            acquisition_date=day,
            acquisition_source=AcquisitionSource.BORN_ON_FARM,
            dam=dam,
            sire=sire,
            sire_details=(mating.ai_straw if mating and not sire else ""),
            location=dam.location,
            group=kids_group,
            breeding_status=BreedingStatus.TOO_YOUNG,
            colour_markings=kid.get("colour", ""),
            created_by=user,
            updated_by=user,
        )
        if kid.get("birth_weight_kg"):
            WeightRecord.objects.create(
                farm=farm,
                animal=animal,
                date=day,
                weight_kg=Decimal(str(kid["birth_weight_kg"])),
                notes="Birth weight",
                created_by=user,
                updated_by=user,
            )
        live.append(animal)
    birth.save()
    birth.kids.set(live)

    if mating is not None:
        mating.status = MatingStatus.KIDDED
        mating.pregnancy_status = PregnancyStatus.CONFIRMED
        mating.actual_kidding_date = day
        mating.kids_count = len(live)
        mating.save()
        _complete_task(mating, "scan", user, "Kidded")
        _complete_task(mating, "kidding", user, f"{len(live)} kid(s) born")
    dam = Animal.objects.select_for_update().get(pk=dam.pk)
    dam.breeding_status = BreedingStatus.LACTATING
    if dam.health_status == HealthStatus.PREGNANT:
        dam.health_status = HealthStatus.HEALTHY
    dam.save()
    return birth


# --- Deaths ------------------------------------------------------------------------------------------


@transaction.atomic
def record_death(mortality: Mortality) -> None:
    animal = Animal.objects.select_for_update().get(pk=mortality.animal_id)
    if mortality.age_at_death_months is None:
        months = animal.age_in_months(mortality.date)
        if months is not None:
            Mortality.objects.filter(pk=mortality.pk).update(age_at_death_months=months)
            mortality.age_at_death_months = months
    animal.is_active = False
    animal.exit_reason, animal.exit_date = ExitReason.DIED, mortality.date
    animal.exit_notes = (mortality.cause or mortality.get_cause_category_display())[:200]
    animal.save()
    # Open matings of a doe that died end here.
    for m in Mating.objects.filter(doe=animal, status=MatingStatus.ACTIVE):
        m.status = MatingStatus.FAILED
        m.save()
        sync_mating_tasks(m)
    emit(
        "health.alert",
        mortality.farm_id,
        urgent=True,
        animal_id=str(animal.pk),
        title=f"Death recorded: {animal.animal_id}",
        message=f"{animal} died on {mortality.date:%d %b %Y}. Cause: {mortality.cause or mortality.get_cause_category_display()}.",
    )


@transaction.atomic
def undo_death(mortality: Mortality) -> None:
    animal = Animal.objects.select_for_update().get(pk=mortality.animal_id)
    if animal.exit_reason == ExitReason.DIED:
        animal.is_active, animal.exit_reason, animal.exit_date, animal.exit_notes = (
            True,
            "",
            None,
            "",
        )
        animal.save()


# --- Derived views -------------------------------------------------------------------------------------


def pregnancy_progress(mating: Mating, today: date | None = None) -> dict[str, Any]:
    today = today or timezone.localdate()
    expected = mating.expected_kidding_date or mating.date + timedelta(days=GESTATION_DAYS)
    total = max((expected - mating.date).days, 1)
    days = (today - mating.date).days
    return {
        "days_pregnant": max(days, 0),
        "days_remaining": (expected - today).days,
        "progress_percent": max(0, min(100, round(days * 100 / total))),
        "trimester": 1 if days < total / 3 else 2 if days < 2 * total / 3 else 3,
    }


def kid_growth(animal: Animal) -> dict[str, Any]:
    weights = list(animal.weights.order_by("date", "created_at").values("date", "weight_kg"))
    birth = next(
        (w for w in weights if w["date"] == animal.date_of_birth), weights[0] if weights else None
    )
    latest = weights[-1] if weights else None
    adg = None
    if birth and latest and latest["date"] > birth["date"]:
        adg = round(
            float(latest["weight_kg"] - birth["weight_kg"])
            * 1000
            / (latest["date"] - birth["date"]).days
        )
    kg = lambda v: f"{v:.2f}" if v is not None else None  # noqa: E731
    return {
        "birth_weight_kg": kg(birth["weight_kg"]) if birth else None,
        "latest_weight_kg": kg(latest["weight_kg"]) if latest else None,
        "latest_weight_date": latest["date"] if latest else None,
        "average_daily_gain_g": adg,
        "weights": [{"date": w["date"], "weight_kg": kg(w["weight_kg"])} for w in weights],
    }


def kids_queryset(qs: Any) -> Any:
    from apps.livestock.services import age_band_bounds

    born_after, _ = age_band_bounds("kid")
    return qs.filter(is_active=True, date_of_birth__gte=born_after)


KID_MONTHS = KID_AGE_MONTHS


# --- Timeline ----------------------------------------------------------------------------------------


def _breeding_events(animal: Animal) -> Iterable[TimelineEvent]:
    for m in Mating.objects.filter(doe=animal).select_related("buck"):
        sire = m.buck.animal_id if m.buck else (m.ai_straw or "AI")
        yield TimelineEvent(
            _as_datetime(m.date),
            "breeding",
            f"Mated with {sire}",
            (
                f"Expected kidding {m.expected_kidding_date:%d %b %Y}"
                if m.expected_kidding_date
                else ""
            ),
        )
        if m.scan_date and m.pregnancy_status != PregnancyStatus.AWAITING_SCAN:
            yield TimelineEvent(
                _as_datetime(m.scan_date),
                "breeding",
                f"Pregnancy scan: {m.get_pregnancy_status_display()}",
            )
    for m in Mating.objects.filter(buck=animal).select_related("doe"):
        yield TimelineEvent(_as_datetime(m.date), "breeding", f"Served {m.doe.animal_id}")
    for b in Birth.objects.filter(dam=animal).prefetch_related("kids"):
        ids = ", ".join(k.animal_id for k in b.kids.all())
        still = f", {b.stillborn_count} stillborn" if b.stillborn_count else ""
        yield TimelineEvent(
            _as_datetime(b.date),
            "birth",
            f"Gave birth ({b.get_birth_type_display()})",
            f"{ids}{still}",
        )
    for b in Birth.objects.filter(kids=animal).select_related("dam"):
        yield TimelineEvent(
            _as_datetime(b.date), "birth", f"Born to {b.dam.animal_id}", b.get_condition_display()
        )
    mortality = Mortality.objects.filter(animal=animal).first()
    if mortality:
        yield TimelineEvent(
            _as_datetime(mortality.date),
            "death",
            "Died",
            mortality.cause or mortality.get_cause_category_display(),
        )


TIMELINE_SOURCES.append(_breeding_events)
