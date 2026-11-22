"""Livestock rules: ID suggestions, ages, default locations, timeline and exports."""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from django.db.models import QuerySet
from django.utils import timezone

from apps.audit.models import AuditLog

from .models import (
    KID_AGE_MONTHS,
    Animal,
    AnimalGroup,
    Location,
    LocationType,
)

# --- IDs and ages ---------------------------------------------------------------------------------


def next_animal_id(farm: Any) -> str:
    """Next free ID with the farm's prefix: YPA-020 exists → YPA-021. Padded to 3 digits."""
    prefix = (farm.animal_id_prefix or "FARM").upper()
    pattern = re.compile(rf"^{re.escape(prefix)}-(\d+)$", re.IGNORECASE)
    highest = 0
    for value in Animal.unscoped.filter(farm=farm, animal_id__istartswith=f"{prefix}-").values_list(
        "animal_id", flat=True
    ):
        match = pattern.match(value)
        if match:
            highest = max(highest, int(match.group(1)))
    return f"{prefix}-{highest + 1:03d}"


def months_before(on: date, months: int) -> date:
    """The same day ``months`` months earlier (clamped to the month's last day)."""
    year, month = divmod(on.year * 12 + on.month - 1 - months, 12)
    month += 1
    for day in (on.day, 30, 29, 28):
        try:
            return date(year, month, day)
        except ValueError:
            continue
    return date(year, month, 28)


def age_band_bounds(band: str, today: date | None = None) -> tuple[date | None, date | None]:
    """Date-of-birth range for an age filter: kid (<6 months), young (6–12), adult (12+)."""
    today = today or timezone.localdate()
    six, twelve = months_before(today, KID_AGE_MONTHS), months_before(today, 12)
    if band == "kid":
        return six + timedelta(days=1), None
    if band == "young":
        return twelve + timedelta(days=1), six
    if band == "adult":
        return None, twelve
    return None, None


# --- Defaults for a new farm -------------------------------------------------------------------------

DEFAULT_LOCATIONS = [
    ("Main Paddock", LocationType.PADDOCK, "Daytime grazing"),
    ("Night Pen", LocationType.PEN, "Night housing"),
    ("Kid Pen", LocationType.PEN, "Kids and their dams"),
    ("Isolation Pen", LocationType.ISOLATION, "Sick animals"),
    ("Quarantine Pen", LocationType.QUARANTINE, "New arrivals and suspected disease"),
]
DEFAULT_GROUPS = [
    ("Breeding Does", "Females for breeding"),
    ("Bucks", "Breeding males"),
    ("Kids", "Under 6 months"),
    ("Growers", "Young stock 6–12 months"),
]


def seed_farm_defaults(farm: Any, created_by: Any = None) -> None:
    for name, kind, description in DEFAULT_LOCATIONS:
        Location.unscoped.get_or_create(
            farm=farm,
            name=name,
            deleted_at=None,
            defaults={"type": kind, "description": description},
        )
    for name, description in DEFAULT_GROUPS:
        AnimalGroup.unscoped.get_or_create(
            farm=farm, name=name, deleted_at=None, defaults={"description": description}
        )


# --- Timeline -----------------------------------------------------------------------------------------


@dataclass
class TimelineEvent:
    at: datetime
    kind: str  # registered | weight | photo | status | location | exit | (later: vaccination…)
    title: str
    detail: str = ""
    by: str | None = None

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["at"] = self.at.astimezone(UTC).isoformat()
        return data


def _as_datetime(day: date) -> datetime:
    return timezone.make_aware(datetime.combine(day, time(12, 0)))


def _who(user: Any) -> str | None:
    return user.full_name if user else None


def _core_events(animal: Animal) -> Iterable[TimelineEvent]:
    yield TimelineEvent(
        animal.created_at, "registered", "Registered", str(animal), _who(animal.created_by)
    )
    for w in animal.weights.select_related("created_by"):
        bcs = f", body condition {w.body_condition_score}" if w.body_condition_score else ""
        yield TimelineEvent(
            _as_datetime(w.date),
            "weight",
            f"Weighed {w.weight_kg} kg",
            f"{w.notes}{bcs}".strip(", "),
            _who(w.created_by),
        )
    for p in animal.photos.select_related("created_by"):
        yield TimelineEvent(p.created_at, "photo", "Photo added", p.caption, _who(p.created_by))
    labels = {
        "health_status": ("status", "Health status", dict(Animal._meta.get_field("health_status").choices)),  # type: ignore[arg-type]
        "breeding_status": ("status", "Breeding status", dict(Animal._meta.get_field("breeding_status").choices)),  # type: ignore[arg-type]
    }
    entries = AuditLog.unscoped.filter(
        farm_id=animal.farm_id, object_id=str(animal.pk), action__in=["status_change", "update"]
    ).select_related("user")
    location_names = dict(
        Location.unscoped.filter(farm_id=animal.farm_id).values_list("id", "name")
    )
    for entry in entries:
        before, after = entry.before or {}, entry.after or {}
        for field, (kind, label, names) in labels.items():
            if field in after:
                old, new = names.get(before.get(field), before.get(field)), names.get(
                    after[field], after[field]
                )
                yield TimelineEvent(
                    entry.at, kind, f"{label}: {new}", f"Was {old}", _who(entry.user)
                )
        if "location_id" in after:
            new_loc = location_names.get(_uuid(after["location_id"]), "no location")
            old_loc = location_names.get(_uuid(before.get("location_id")), "no location")
            yield TimelineEvent(
                entry.at, "location", f"Moved to {new_loc}", f"From {old_loc}", _who(entry.user)
            )
    if not animal.is_active and animal.exit_date:
        yield TimelineEvent(
            _as_datetime(animal.exit_date),
            "exit",
            f"Left the herd: {animal.get_exit_reason_display()}",
            animal.exit_notes,
        )


def _uuid(value: Any) -> Any:
    import uuid

    try:
        return uuid.UUID(str(value)) if value else None
    except ValueError:
        return None


# Later phases append functions that yield TimelineEvents (vaccinations, treatments, matings…).
TIMELINE_SOURCES: list[Callable[[Animal], Iterable[TimelineEvent]]] = [_core_events]


def timeline(animal: Animal) -> list[dict[str, Any]]:
    events = [e for source in TIMELINE_SOURCES for e in source(animal)]
    events.sort(key=lambda e: e.at, reverse=True)
    return [e.as_dict() for e in events]


# --- Export -------------------------------------------------------------------------------------------

EXPORT_COLUMNS = [
    ("Animal ID", lambda a: a.animal_id),
    ("Ear tag", lambda a: a.ear_tag),
    ("Name", lambda a: a.name),
    ("Species", lambda a: a.get_species_display()),
    ("Breed", lambda a: a.breed),
    ("Sex", lambda a: a.get_sex_display()),
    ("Date of birth", lambda a: a.date_of_birth),
    ("Birth date estimated", lambda a: "Yes" if a.dob_estimated else "No"),
    ("Age (months)", lambda a: a.age_in_months()),
    ("Health status", lambda a: a.get_health_status_display()),
    ("Breeding status", lambda a: a.get_breeding_status_display()),
    ("Location", lambda a: a.location.name if a.location else ""),
    ("Group", lambda a: a.group.name if a.group else ""),
    ("Dam", lambda a: a.dam.animal_id if a.dam else ""),
    ("Sire", lambda a: a.sire.animal_id if a.sire else a.sire_details),
    (
        "Latest weight (kg)",
        lambda a: float(a.latest_weight_kg) if a.latest_weight_kg is not None else None,
    ),
    ("Acquired", lambda a: a.acquisition_date),
    ("Source", lambda a: a.get_acquisition_source_display()),
    ("Active", lambda a: "Yes" if a.is_active else f"No ({a.get_exit_reason_display()})"),
]


def export_csv(animals: QuerySet[Animal]) -> bytes:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow([c for c, _ in EXPORT_COLUMNS])
    for a in animals:
        writer.writerow(["" if (v := f(a)) is None else v for _, f in EXPORT_COLUMNS])
    return ("﻿" + out.getvalue()).encode("utf-8")  # BOM so Excel reads UTF-8


def export_xlsx(animals: QuerySet[Animal], farm_name: str) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = "Livestock register"
    ws.append([c for c, _ in EXPORT_COLUMNS])
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1B5E20")
    for a in animals:
        ws.append([f(a) for _, f in EXPORT_COLUMNS])
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            if isinstance(cell.value, date):
                cell.number_format = "DD MMM YYYY"
    ws.freeze_panes = "A2"
    for col in ws.columns:
        width = max(len(str(c.value or "")) for c in col)
        ws.column_dimensions[col[0].column_letter].width = min(max(width + 2, 10), 40)
    ws.oddFooter.center.text = f"{farm_name} — exported {timezone.localdate():%d %b %Y}"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
