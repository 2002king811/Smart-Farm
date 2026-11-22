"""Health rules: catalogs, treatment status rules, withdrawal periods, linked calendar
activities, health alerts and the animal timeline."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import timedelta
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.calendar.services import sync_linked_activity
from apps.livestock.models import Animal, BreedingStatus, HealthStatus
from apps.livestock.services import TIMELINE_SOURCES, TimelineEvent, _as_datetime
from apps.notifications.events import emit

from .models import (
    Deworming,
    DiseaseCategory,
    HealthInspection,
    HealthObservation,
    Medicine,
    MedicineType,
    ParasiteControl,
    Route,
    Severity,
    Treatment,
    TreatmentStatus,
    Vaccination,
    Vaccine,
    VetVisit,
)

# --- Starter catalogs ---------------------------------------------------------------------------------

DEFAULT_VACCINES = [
    # name, disease, route, default dose, withdrawal days, booster interval days
    (
        "Enterotoxaemia (Clostridial) vaccine",
        DiseaseCategory.CLOSTRIDIAL,
        Route.SUBCUTANEOUS,
        "2 ml",
        21,
        365,
    ),
    ("PPR vaccine", DiseaseCategory.PPR, Route.SUBCUTANEOUS, "1 ml", 21, 1095),
    ("Goat pox vaccine", DiseaseCategory.GOAT_POX, Route.SUBCUTANEOUS, "1 ml", 21, 365),
    ("Brucella Rev-1 vaccine", DiseaseCategory.BRUCELLOSIS, Route.SUBCUTANEOUS, "1 ml", 21, None),
    ("Anthrax spore vaccine", DiseaseCategory.ANTHRAX, Route.SUBCUTANEOUS, "1 ml", 42, 365),
    ("CCPP vaccine", DiseaseCategory.CCPP, Route.SUBCUTANEOUS, "1 ml", 21, 365),
    ("FMD vaccine", DiseaseCategory.FMD, Route.SUBCUTANEOUS, "2 ml", 21, 180),
]
DEFAULT_MEDICINES = [
    # name, type, route, default dose, withdrawal days
    ("Albendazole", MedicineType.DEWORMER, Route.ORAL, "1 ml / 10 kg", 10),
    ("Ivermectin", MedicineType.DEWORMER, Route.SUBCUTANEOUS, "1 ml / 50 kg", 35),
    ("Levamisole", MedicineType.DEWORMER, Route.ORAL, "1 ml / 10 kg", 10),
    ("Oxytetracycline LA", MedicineType.ANTIBIOTIC, Route.INTRAMUSCULAR, "1 ml / 10 kg", 28),
    ("Penicillin-Streptomycin", MedicineType.ANTIBIOTIC, Route.INTRAMUSCULAR, "1 ml / 25 kg", 30),
    ("Flunixin", MedicineType.ANTI_INFLAMMATORY, Route.INTRAMUSCULAR, "1 ml / 45 kg", 10),
    ("Multivitamin injection", MedicineType.VITAMIN, Route.INTRAMUSCULAR, "2 ml", 0),
    ("Amitraz (acaricide)", MedicineType.ACARICIDE, Route.TOPICAL, "2 ml / litre", 7),
]


def seed_catalogs(farm: Any) -> None:
    for name, disease, route, dose, withdrawal, booster in DEFAULT_VACCINES:
        Vaccine.unscoped.get_or_create(
            farm=farm,
            name=name,
            deleted_at=None,
            defaults={
                "disease_category": disease,
                "route": route,
                "default_dose": dose,
                "withdrawal_days": withdrawal,
                "booster_interval_days": booster,
            },
        )
    for name, kind, route, dose, withdrawal in DEFAULT_MEDICINES:
        Medicine.unscoped.get_or_create(
            farm=farm,
            name=name,
            deleted_at=None,
            defaults={
                "type": kind,
                "route": route,
                "default_dose": dose,
                "withdrawal_days": withdrawal,
            },
        )


# --- After a record is saved or deleted ------------------------------------------------------------------


def _subject(record: Any) -> str:
    animal = getattr(record, "animal", None)
    if animal is not None:
        return animal.animal_id
    group = getattr(record, "group", None)
    if group is not None:
        return group.name
    return "whole herd"


def activity_title(record: Any) -> str:
    if isinstance(record, Vaccination):
        name = (
            record.vaccine.name
            if record.vaccine
            else (record.vaccine_name or record.get_disease_category_display())
        )
        return f"Vaccination due: {name} – {_subject(record)}"
    if isinstance(record, Deworming):
        return f"Deworming due – {_subject(record)}"
    if isinstance(record, ParasiteControl):
        return f"{record.get_method_display()} due ({record.target}) – {_subject(record)}"
    if isinstance(record, Treatment):
        return f"Treatment follow-up: {record.diagnosis} – {record.animal.animal_id}"
    if isinstance(record, VetVisit):
        return f"Vet visit – {record.vet_name}"
    if isinstance(record, HealthInspection):
        return "Health inspection"
    return str(record)


def _activity_animals(record: Any) -> list[Any] | None:
    animal = getattr(record, "animal", None)
    if animal is not None:
        return [animal]
    if hasattr(record, "animals"):
        return list(record.animals.all())
    return None


def after_save(record: Any, created: bool) -> None:
    if record.NEXT_DATE_FIELD:
        sync_linked_activity(
            record,
            activity_title(record),
            _activity_animals(record),
            getattr(record, "group", None),
        )
    if isinstance(record, Treatment):
        refresh_treatment_status(record.animal)
    if isinstance(record, HealthObservation) and created:
        fever = (
            record.temperature_c is not None and record.temperature_c >= HealthObservation.FEVER_C
        )
        if record.severity == Severity.SEVERE or fever:
            emit(
                "health.alert",
                record.farm_id,
                urgent=True,
                animal_id=str(record.animal_id),
                title=f"Health alert: {record.animal.animal_id}",
                message=f"{record.get_severity_display()} – {record.symptoms[:120]}"
                + (f" (temperature {record.temperature_c} °C)" if record.temperature_c else ""),
            )


def after_delete(record: Any) -> None:
    if record.NEXT_DATE_FIELD:
        sync_linked_activity(record, activity_title(record))
    if isinstance(record, Treatment):
        refresh_treatment_status(record.animal)


def prepare_treatment(data: dict[str, Any], instance: Treatment | None = None) -> dict[str, Any]:
    """Fill in the withdrawal date from the medicine, and the resolved date when resolving."""
    medication = data.get("medication", getattr(instance, "medication", None))
    day = data.get("date", getattr(instance, "date", None)) or timezone.localdate()
    if (
        "withdrawal_until" not in data
        and medication
        and medication.withdrawal_days
        and (instance is None or "medication" in data or "date" in data)
    ):
        data["withdrawal_until"] = day + timedelta(days=medication.withdrawal_days)
    status = data.get("status", getattr(instance, "status", TreatmentStatus.ONGOING))
    if (
        status == TreatmentStatus.RESOLVED
        and not data.get("resolved_date")
        and not getattr(instance, "resolved_date", None)
    ):
        data["resolved_date"] = timezone.localdate()
    if status == TreatmentStatus.ONGOING:
        data["resolved_date"] = None
    return data


@transaction.atomic
def refresh_treatment_status(animal: Animal) -> None:
    """Recording a treatment sets Under Treatment. When the last open treatment is resolved the
    animal returns to Healthy, or to Pregnant if it is pregnant."""
    animal = Animal.objects.select_for_update().get(pk=animal.pk)
    ongoing = Treatment.objects.filter(animal=animal, status=TreatmentStatus.ONGOING).exists()
    if ongoing and animal.health_status != HealthStatus.UNDER_TREATMENT:
        animal.health_status = HealthStatus.UNDER_TREATMENT
        animal.save()
    elif not ongoing and animal.health_status == HealthStatus.UNDER_TREATMENT:
        animal.health_status = (
            HealthStatus.PREGNANT
            if animal.breeding_status == BreedingStatus.PREGNANT
            else HealthStatus.HEALTHY
        )
        animal.save()


def withdrawal_until(animal: Animal) -> Any:
    """Latest withdrawal date still in the future, from treatments and vaccinations."""
    today = timezone.localdate()
    dates = list(
        Treatment.objects.filter(animal=animal, withdrawal_until__gte=today).values_list(
            "withdrawal_until", flat=True
        )
    )
    for v in Vaccination.objects.filter(animal=animal).select_related("vaccine"):
        if v.vaccine and v.vaccine.withdrawal_days:
            until = v.date + timedelta(days=v.vaccine.withdrawal_days)
            if until >= today:
                dates.append(until)
    return max(dates) if dates else None


# --- Timeline -------------------------------------------------------------------------------------------


def _health_events(animal: Animal) -> Iterable[TimelineEvent]:
    def who(user: Any) -> str | None:
        return user.full_name if user else None

    for v in Vaccination.objects.filter(animal=animal).select_related("vaccine", "created_by"):
        name = v.vaccine.name if v.vaccine else (v.vaccine_name or v.get_disease_category_display())
        due = f"Next due {v.next_due_date:%d %b %Y}" if v.next_due_date else ""
        yield TimelineEvent(
            _as_datetime(v.date), "vaccination", f"Vaccinated: {name}", due, who(v.created_by)
        )
    for d in Deworming.objects.filter(animal=animal).select_related("product", "created_by"):
        product = d.product.name if d.product else d.product_name
        yield TimelineEvent(
            _as_datetime(d.date), "deworming", "Dewormed", product, who(d.created_by)
        )
    for t in Treatment.objects.filter(animal=animal).select_related("created_by"):
        yield TimelineEvent(
            _as_datetime(t.date),
            "treatment",
            f"Treatment: {t.diagnosis}",
            t.treatment[:120],
            who(t.created_by),
        )
        if t.status == TreatmentStatus.RESOLVED and t.resolved_date:
            yield TimelineEvent(
                _as_datetime(t.resolved_date), "treatment", f"Recovered: {t.diagnosis}", "", None
            )
    for o in HealthObservation.objects.filter(animal=animal).select_related("created_by"):
        temp = f" · {o.temperature_c} °C" if o.temperature_c else ""
        yield TimelineEvent(
            _as_datetime(o.date),
            "observation",
            f"Observed ({o.get_severity_display()})",
            f"{o.symptoms[:100]}{temp}",
            who(o.created_by),
        )
    for vv in VetVisit.objects.filter(animals=animal):
        yield TimelineEvent(
            _as_datetime(vv.date), "vet_visit", f"Vet visit: {vv.vet_name}", vv.reason, None
        )


TIMELINE_SOURCES.append(_health_events)
