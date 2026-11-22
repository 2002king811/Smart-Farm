"""The 15 reports. Each builder returns summary cards, one chart and one or more tables for a
period and filters; the preview, PDF, Excel and CSV all render that same output.

Figures come from metrics.py, the same functions the dashboard uses."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any, ClassVar

from django.db.models import Count, Q, QuerySet
from django.utils import timezone

from apps.accounts.models import FarmMembership, MembershipStatus
from apps.breeding.models import DeathCause
from apps.calendar.models import Activity, ActivityStatus
from apps.health.models import HealthObservation, Severity, TreatmentStatus
from apps.livestock.models import Animal, HealthStatus, Location, Sex

from . import metrics as m
from .metrics import Period

# --- Output ---------------------------------------------------------------------------------------


@dataclass
class Column:
    key: str
    label: str
    type: str = "text"  # text | date | number | percent


@dataclass
class Table:
    key: str
    title: str
    columns: list[Column]
    rows: list[dict[str, Any]]


@dataclass
class Card:
    key: str
    label: str
    value: Any
    unit: str = ""


@dataclass
class Chart:
    type: str  # bar | line
    title: str
    labels: list[str]
    series: list[dict[str, Any]]  # [{"name": str, "values": [numbers]}]
    stacked: bool = False


@dataclass
class ReportData:
    key: str
    title: str
    period: Period
    group: str
    filters: dict[str, str]
    summary: list[Card]
    chart: Chart | None
    tables: list[Table]

    @property
    def row_count(self) -> int:
        return sum(len(t.rows) for t in self.tables)

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "title": self.title,
            "from": self.period.start,
            "to": self.period.end,
            "period_label": self.period.label(),
            "group": self.group,
            "filters": self.filters,
            "summary": [c.__dict__ for c in self.summary],
            "chart": self.chart.__dict__ if self.chart else None,
            "tables": [
                {
                    "key": t.key,
                    "title": t.title,
                    "columns": [c.__dict__ for c in t.columns],
                    "rows": t.rows,
                }
                for t in self.tables
            ],
            "row_count": self.row_count,
        }


# --- Helpers ----------------------------------------------------------------------------------------


def subject(record: Any) -> str:
    if getattr(record, "animal_id", None):
        return str(record.animal.animal_id)
    if getattr(record, "group_id", None):
        return f"Group: {record.group.name}"
    return ""


def label_of(choices: Any, value: str) -> str:
    return dict(choices.choices).get(value, value or "")


def person(user: Any) -> str:
    return user.full_name if user else ""


def percent(part: int, whole: int) -> int:
    return round(part * 100 / whole) if whole else 0


# --- Base -------------------------------------------------------------------------------------------


@dataclass
class Filter:
    key: str
    label: str
    type: str = "select"  # select | animal | member | category
    options: list[tuple[str, str]] = field(default_factory=list)


class Report:
    key: ClassVar[str]
    title: ClassVar[str]
    description: ClassVar[str]
    section: ClassVar[str]
    # How the period defaults when none is given: month | quarter | year | next30 | today
    default_period: ClassVar[str] = "month"
    filters: ClassVar[list[Filter]] = []
    uses_period: ClassVar[bool] = True

    def __init__(self, farm: Any, period: Period, group: str, params: dict[str, str]) -> None:
        self.farm, self.period, self.group = farm, period, group
        self.params = {f.key: params[f.key] for f in self.filters if params.get(f.key)}

    def build(self) -> ReportData:
        summary, chart, tables = self.compute()
        return ReportData(
            self.key, self.title, self.period, self.group, self.params, summary, chart, tables
        )

    def compute(self) -> tuple[list[Card], Chart | None, list[Table]]:
        raise NotImplementedError

    def labels(self) -> list[str]:
        return [
            m.bucket_label(max(b, self.period.start), self.group)
            for b in m.buckets(self.period, self.group)
        ]

    def chart(self, title: str, **series: list[int]) -> Chart:
        return Chart(
            "bar",
            title,
            self.labels(),
            [{"name": k.replace("_", " ").capitalize(), "values": v} for k, v in series.items()],
        )


def default_period(kind: str, today: dt.date) -> Period:
    if kind == "quarter":
        return m.quarter_period(today)
    if kind == "year":
        return m.year_period(today)
    if kind == "next30":
        return Period(today, today + dt.timedelta(days=30))
    if kind == "past30":
        return Period(today - dt.timedelta(days=29), today)
    return m.month_period(today)


SEX_OPTIONS = list(Sex.choices)
STATUS_OPTIONS = list(HealthStatus.choices)


# --- 1. Livestock register ---------------------------------------------------------------------------


class LivestockRegister(Report):
    key, title, section = "livestock_register", "Livestock Register", "Livestock"
    description = "Every animal on the farm now, with its ID, age, location and status."
    uses_period = False
    filters = [
        Filter("sex", "Sex", options=SEX_OPTIONS),
        Filter("health_status", "Health status", options=STATUS_OPTIONS),
        Filter("location", "Location", type="location"),
    ]

    def compute(self) -> tuple[list[Card], Chart | None, list[Table]]:
        herd = m.herd()
        qs = Animal.objects.filter(is_active=True).select_related("location").order_by("animal_id")
        for k in ("sex", "health_status"):
            if k in self.params:
                qs = qs.filter(**{k: self.params[k]})
        if "location" in self.params:
            qs = qs.filter(location_id=self.params["location"])
        rows = [
            {
                "animal_id": a.animal_id,
                "ear_tag": a.ear_tag,
                "name": a.name,
                "breed": a.breed,
                "sex": a.get_sex_display(),
                "date_of_birth": a.date_of_birth,
                "age_months": a.age_in_months(),
                "location": a.location.name if a.location_id else "",
                "health_status": a.get_health_status_display(),
                "breeding_status": a.get_breeding_status_display(),
                "source": a.get_acquisition_source_display(),
            }
            for a in qs
        ]
        counts = m.health_status_counts()
        summary = [
            Card("total", "Total animals", herd["total"]),
            Card("males", "Males", herd["males"]),
            Card("females", "Females", herd["females"]),
            Card("kids", "Kids (under 6 months)", herd["kids"]),
            Card("needing_attention", "Needing attention", herd["needing_attention"]),
            Card("pregnant", "Pregnant", herd["pregnant"]),
        ]
        chart = Chart(
            "bar",
            "Animals by health status",
            [label_of(HealthStatus, s) for s in counts],
            [{"name": "Animals", "values": list(counts.values())}],
        )
        columns = [
            Column("animal_id", "Animal ID"),
            Column("ear_tag", "Ear tag"),
            Column("name", "Name"),
            Column("breed", "Breed"),
            Column("sex", "Sex"),
            Column("date_of_birth", "Date of birth", "date"),
            Column("age_months", "Age (months)", "number"),
            Column("location", "Location"),
            Column("health_status", "Health status"),
            Column("breeding_status", "Breeding status"),
            Column("source", "Source"),
        ]
        return summary, chart, [Table("animals", "Animals", columns, rows)]


# --- 2. Animal health history -----------------------------------------------------------------------


class AnimalHealthHistory(Report):
    key, title, section = "animal_health_history", "Animal Health History", "Health"
    description = "Vaccinations, deworming, treatments and observations, for one animal or all."
    default_period = "year"
    filters = [Filter("animal", "Animal", type="animal")]

    def compute(self) -> tuple[list[Card], Chart | None, list[Table]]:
        p, animal = self.period, self.params.get("animal")

        def scope(qs: QuerySet[Any]) -> QuerySet[Any]:
            return qs.filter(animal_id=animal) if animal else qs

        vac = scope(m.vaccinations(p)).select_related("animal", "group")
        dew = scope(m.dewormings(p)).select_related("animal", "group")
        tre = scope(m.treatments(p)).select_related("animal")
        obs = scope(m.observations(p)).select_related("animal")
        rows: list[dict[str, Any]] = []
        for v in vac:
            rows.append(
                {
                    "date": v.date,
                    "subject": subject(v),
                    "type": "Vaccination",
                    "details": v.vaccine_name or (v.vaccine.name if v.vaccine_id else ""),
                    "by": v.administered_by,
                }
            )
        for d in dew:
            rows.append(
                {
                    "date": d.date,
                    "subject": subject(d),
                    "type": "Deworming",
                    "details": d.product_name,
                    "by": d.administered_by,
                }
            )
        for t in tre:
            rows.append(
                {
                    "date": t.date,
                    "subject": subject(t),
                    "type": "Treatment",
                    "details": f"{t.diagnosis} – {t.get_status_display()}".strip(" –"),
                    "by": t.responsible_person or t.vet_officer,
                }
            )
        for o in obs:
            rows.append(
                {
                    "date": o.date,
                    "subject": subject(o),
                    "type": "Observation",
                    "details": f"{o.get_severity_display()}: {o.symptoms}",
                    "by": o.observed_by,
                }
            )
        rows.sort(key=lambda r: (r["date"], r["type"]), reverse=True)
        summary = [
            Card("vaccinations", "Vaccinations", vac.count()),
            Card("dewormings", "Dewormings", dew.count()),
            Card("treatments", "Treatments", tre.count()),
            Card("observations", "Observations", obs.count()),
        ]
        chart = self.chart(
            "Health records",
            vaccinations=m.series(vac, p, self.group),
            dewormings=m.series(dew, p, self.group),
            treatments=m.series(tre, p, self.group),
            observations=m.series(obs, p, self.group),
        )
        chart.stacked = True
        columns = [
            Column("date", "Date", "date"),
            Column("subject", "Animal / group"),
            Column("type", "Record"),
            Column("details", "Details"),
            Column("by", "By"),
        ]
        return summary, chart, [Table("records", "Health records", columns, rows)]


# --- 3/4. Vaccination and deworming --------------------------------------------------------------------


class VaccinationReport(Report):
    key, title, section = "vaccination", "Vaccination Report", "Health"
    description = "Vaccinations given in the period, missed doses and what is due next."

    def compute(self) -> tuple[list[Card], Chart | None, list[Table]]:
        qs = m.vaccinations(self.period).select_related("animal", "group", "vaccine")
        today = timezone.localdate()
        due = Activity.objects.filter(
            category__key="vaccination",
            status__in=m.OPEN,
            date__range=(today, today + dt.timedelta(days=30)),
        )
        rows = [
            {
                "date": v.date,
                "subject": subject(v),
                "vaccine": v.vaccine_name or (v.vaccine.name if v.vaccine_id else ""),  # type: ignore[union-attr]
                "disease": v.get_disease_category_display(),
                "batch": v.batch_number,
                "dosage": v.dosage,
                "by": v.administered_by,
                "vet": v.vet_officer,
                "next_due": v.next_due_date,
                "status": v.get_status_display(),
            }
            for v in qs.order_by("-date")
        ]
        missed = qs.filter(status="missed").count()
        summary = [
            Card("records", "Vaccinations", qs.count()),
            Card(
                "animals",
                "Animals vaccinated",
                qs.exclude(animal=None).values("animal").distinct().count(),
            ),
            Card("missed", "Missed", missed),
            Card("due_30_days", "Due in the next 30 days", due.count()),
        ]
        chart = self.chart("Vaccinations", vaccinations=m.series(qs, self.period, self.group))
        by_vaccine = [
            {"vaccine": r["vaccine_name"] or "—", "count": r["n"]}
            for r in qs.values("vaccine_name").annotate(n=Count("pk")).order_by("-n")
        ]
        columns = [
            Column("date", "Date", "date"),
            Column("subject", "Animal / group"),
            Column("vaccine", "Vaccine"),
            Column("disease", "Disease"),
            Column("batch", "Batch"),
            Column("dosage", "Dosage"),
            Column("by", "Given by"),
            Column("vet", "Vet officer"),
            Column("next_due", "Next due", "date"),
            Column("status", "Status"),
        ]
        return (
            summary,
            chart,
            [
                Table("vaccinations", "Vaccinations", columns, rows),
                Table(
                    "by_vaccine",
                    "By vaccine",
                    [Column("vaccine", "Vaccine"), Column("count", "Doses", "number")],
                    by_vaccine,
                ),
            ],
        )


class DewormingReport(Report):
    key, title, section = "deworming", "Deworming Report", "Health"
    description = "Deworming done in the period and what is due next."

    def compute(self) -> tuple[list[Card], Chart | None, list[Table]]:
        qs = m.dewormings(self.period).select_related("animal", "group")
        today = timezone.localdate()
        due = Activity.objects.filter(
            category__key="deworming",
            status__in=m.OPEN,
            date__range=(today, today + dt.timedelta(days=30)),
        )
        rows = [
            {
                "date": d.date,
                "subject": subject(d),
                "product": d.product_name,
                "dosage": d.dosage,
                "by": d.administered_by,
                "next_due": d.next_due_date,
                "status": d.get_status_display(),
            }
            for d in qs.order_by("-date")
        ]
        summary = [
            Card("records", "Dewormings", qs.count()),
            Card(
                "animals",
                "Animals dewormed",
                qs.exclude(animal=None).values("animal").distinct().count(),
            ),
            Card("missed", "Missed", qs.filter(status="missed").count()),
            Card("due_30_days", "Due in the next 30 days", due.count()),
        ]
        chart = self.chart("Dewormings", dewormings=m.series(qs, self.period, self.group))
        columns = [
            Column("date", "Date", "date"),
            Column("subject", "Animal / group"),
            Column("product", "Product"),
            Column("dosage", "Dosage"),
            Column("by", "Given by"),
            Column("next_due", "Next due", "date"),
            Column("status", "Status"),
        ]
        return summary, chart, [Table("dewormings", "Dewormings", columns, rows)]


# --- 5. Treatment --------------------------------------------------------------------------------------


class TreatmentReport(Report):
    key, title, section = "treatment", "Treatment Report", "Health"
    description = "Treatments started in the period, outcomes and withdrawal periods."

    def compute(self) -> tuple[list[Card], Chart | None, list[Table]]:
        qs = m.treatments(self.period).select_related("animal")
        today = timezone.localdate()
        rows = [
            {
                "date": t.date,
                "animal": subject(t),
                "diagnosis": t.diagnosis,
                "medication": t.medication_name,
                "dosage": t.dosage,
                "by": t.responsible_person or t.vet_officer,
                "status": t.get_status_display(),
                "resolved": t.resolved_date,
                "withdrawal_until": t.withdrawal_until,
            }
            for t in qs.order_by("-date")
        ]
        summary = [
            Card("records", "Treatments", qs.count()),
            Card("ongoing", "Ongoing", qs.filter(status=TreatmentStatus.ONGOING).count()),
            Card("resolved", "Resolved", qs.filter(status=TreatmentStatus.RESOLVED).count()),
            Card(
                "withdrawal",
                "Under withdrawal today",
                qs.filter(withdrawal_until__gte=today).values("animal").distinct().count(),
            ),
        ]
        chart = self.chart("Treatments", treatments=m.series(qs, self.period, self.group))
        by_diagnosis = [
            {"diagnosis": r["diagnosis"] or "—", "count": r["n"]}
            for r in qs.values("diagnosis").annotate(n=Count("pk")).order_by("-n")
        ]
        columns = [
            Column("date", "Date", "date"),
            Column("animal", "Animal"),
            Column("diagnosis", "Diagnosis"),
            Column("medication", "Medication"),
            Column("dosage", "Dosage"),
            Column("by", "Responsible"),
            Column("status", "Status"),
            Column("resolved", "Resolved", "date"),
            Column("withdrawal_until", "Withdrawal until", "date"),
        ]
        return (
            summary,
            chart,
            [
                Table("treatments", "Treatments", columns, rows),
                Table(
                    "by_diagnosis",
                    "By diagnosis",
                    [Column("diagnosis", "Diagnosis"), Column("count", "Cases", "number")],
                    by_diagnosis,
                ),
            ],
        )


# --- 6. Disease surveillance ------------------------------------------------------------------------------


class DiseaseSurveillance(Report):
    key, title, section = "disease_surveillance", "Disease Surveillance", "Health"
    description = "What staff observed: symptoms, fever, severity and suspected diseases."

    def compute(self) -> tuple[list[Card], Chart | None, list[Table]]:
        qs = m.observations(self.period).select_related("animal")
        fever = Q(temperature_c__gte=HealthObservation.FEVER_C)
        rows = [
            {
                "date": o.date,
                "animal": subject(o),
                "symptoms": o.symptoms,
                "temperature": float(o.temperature_c) if o.temperature_c is not None else None,
                "severity": o.get_severity_display(),
                "suspected": o.suspected_disease,
                "action": o.action_taken,
                "by": o.observed_by,
            }
            for o in qs.order_by("-date")
        ]
        summary = [
            Card("observations", "Observations", qs.count()),
            Card("animals", "Animals affected", qs.values("animal").distinct().count()),
            Card("severe", "Severe", qs.filter(severity=Severity.SEVERE).count()),
            Card("fever", "Fever (≥ 40.5 °C)", qs.filter(fever).count()),
        ]
        chart = self.chart(
            "Observations by severity",
            mild=m.series(qs.filter(severity=Severity.MILD), self.period, self.group),
            moderate=m.series(qs.filter(severity=Severity.MODERATE), self.period, self.group),
            severe=m.series(qs.filter(severity=Severity.SEVERE), self.period, self.group),
        )
        chart.stacked = True
        suspected = [
            {"disease": r["suspected_disease"] or "Not given", "count": r["n"]}
            for r in qs.values("suspected_disease").annotate(n=Count("pk")).order_by("-n")
        ]
        columns = [
            Column("date", "Date", "date"),
            Column("animal", "Animal"),
            Column("symptoms", "Symptoms"),
            Column("temperature", "Temp (°C)", "number"),
            Column("severity", "Severity"),
            Column("suspected", "Suspected disease"),
            Column("action", "Action taken"),
            Column("by", "Observed by"),
        ]
        return (
            summary,
            chart,
            [
                Table("observations", "Observations", columns, rows),
                Table(
                    "suspected",
                    "Suspected diseases",
                    [Column("disease", "Disease"), Column("count", "Cases", "number")],
                    suspected,
                ),
            ],
        )


# --- 7. Births -------------------------------------------------------------------------------------------


class BirthReport(Report):
    key, title, section = "birth", "Birth Report", "Breeding"
    description = "Kiddings in the period: kids born alive, stillbirths and birth types."

    def compute(self) -> tuple[list[Card], Chart | None, list[Table]]:
        qs = m.births(self.period).select_related("dam", "sire").prefetch_related("kids")
        rows = [
            {
                "date": b.date,
                "dam": b.dam.animal_id if b.dam_id else "",
                "sire": b.sire.animal_id if b.sire_id else "",  # type: ignore[union-attr]
                "type": b.get_birth_type_display(),
                "alive": len(b.kids.all()),
                "stillborn": b.stillborn_count,
                "condition": b.get_condition_display(),
                "kids": ", ".join(k.animal_id for k in b.kids.all()),
            }
            for b in qs.order_by("-date")
        ]
        alive, still = m.kids_born_alive(self.period), m.stillborn(self.period)
        multiple = qs.exclude(birth_type="single").count()
        summary = [
            Card("births", "Births", qs.count()),
            Card("kids_born", "Kids born alive", alive),
            Card("stillborn", "Stillborn", still),
            Card("multiple", "Twins or more", percent(multiple, qs.count()), "%"),
        ]
        chart = self.chart("Kids born alive", kids_born=m.kids_series(self.period, self.group))
        columns = [
            Column("date", "Date", "date"),
            Column("dam", "Dam"),
            Column("sire", "Sire"),
            Column("type", "Birth type"),
            Column("alive", "Born alive", "number"),
            Column("stillborn", "Stillborn", "number"),
            Column("condition", "Condition"),
            Column("kids", "Kid IDs"),
        ]
        return summary, chart, [Table("births", "Births", columns, rows)]


# --- 8. Mortality ----------------------------------------------------------------------------------------


class MortalityReport(Report):
    key, title, section = "mortality", "Mortality Report", "Breeding"
    description = "Deaths in the period, causes and the mortality rate."

    def compute(self) -> tuple[list[Card], Chart | None, list[Table]]:
        qs = m.deaths(self.period).select_related("animal")
        rows = [
            {
                "date": d.date,
                "animal": d.animal.animal_id,
                "sex": d.animal.get_sex_display(),
                "age_months": d.age_at_death_months,
                "cause_category": d.get_cause_category_display(),
                "cause": d.cause,
                "disposal": d.get_disposal_display(),
                "by": d.recorded_by,
            }
            for d in qs.order_by("-date")
        ]
        at_start = m.herd_size_on(self.period.start - dt.timedelta(days=1))
        kid_deaths = qs.filter(age_at_death_months__lt=6).count()
        summary = [
            Card("deaths", "Deaths", qs.count()),
            Card("kid_deaths", "Kids (under 6 months)", kid_deaths),
            Card("herd_at_start", "Herd at start", at_start),
            Card("mortality_rate", "Mortality rate", percent(qs.count(), at_start), "%"),
        ]
        chart = self.chart("Deaths", deaths=m.series(qs, self.period, self.group))
        by_cause = [
            {"cause": label_of(DeathCause, r["cause_category"]), "count": r["n"]}
            for r in qs.values("cause_category").annotate(n=Count("pk")).order_by("-n")
        ]
        columns = [
            Column("date", "Date", "date"),
            Column("animal", "Animal"),
            Column("sex", "Sex"),
            Column("age_months", "Age (months)", "number"),
            Column("cause_category", "Cause"),
            Column("cause", "Details"),
            Column("disposal", "Disposal"),
            Column("by", "Recorded by"),
        ]
        return (
            summary,
            chart,
            [
                Table("deaths", "Deaths", columns, rows),
                Table(
                    "by_cause",
                    "By cause",
                    [Column("cause", "Cause"), Column("count", "Deaths", "number")],
                    by_cause,
                ),
            ],
        )


# --- 9. Breeding -----------------------------------------------------------------------------------------


class BreedingReport(Report):
    key, title, section = "breeding", "Breeding Report", "Breeding"
    description = "Matings in the period, scans, conception rate and expected kiddings."

    def compute(self) -> tuple[list[Card], Chart | None, list[Table]]:
        qs = m.matings(self.period).select_related("doe", "buck")
        counts = m.breeding_counts(self.period)
        rows = [
            {
                "date": x.date,
                "doe": x.doe.animal_id,
                "buck": x.buck.animal_id if x.buck_id else (x.ai_straw or ""),  # type: ignore[union-attr]
                "method": x.get_method_display(),
                "pregnancy": x.get_pregnancy_status_display(),
                "expected": x.expected_kidding_date,
                "kidded": x.actual_kidding_date,
                "kids": x.kids_count,
                "status": x.get_status_display(),
            }
            for x in qs.order_by("-date")
        ]
        summary = [
            Card("matings", "Matings", counts["matings"]),
            Card("confirmed", "Confirmed pregnant", counts["confirmed"]),
            Card("kidded", "Kidded", counts["kidded"]),
            Card("conception_rate", "Conception rate", counts["conception_rate"], "%"),
        ]
        chart = self.chart("Matings", matings=m.series(qs, self.period, self.group))
        columns = [
            Column("date", "Mating date", "date"),
            Column("doe", "Doe"),
            Column("buck", "Buck / AI"),
            Column("method", "Method"),
            Column("pregnancy", "Pregnancy"),
            Column("expected", "Expected kidding", "date"),
            Column("kidded", "Kidded on", "date"),
            Column("kids", "Kids", "number"),
            Column("status", "Status"),
        ]
        return summary, chart, [Table("matings", "Matings", columns, rows)]


# --- Activities ------------------------------------------------------------------------------------------


ACTIVITY_COLUMNS = [
    Column("date", "Date", "date"),
    Column("title", "Activity"),
    Column("category", "Category"),
    Column("assigned_to", "Assigned to"),
    Column("priority", "Priority"),
    Column("status", "Status"),
]


def activity_row(a: Activity, today: dt.date | None = None) -> dict[str, Any]:
    row = {
        "date": a.date,
        "title": a.title,
        "category": a.category.name if a.category_id else "",  # type: ignore[union-attr]
        "assigned_to": person(a.assigned_to),
        "priority": a.get_priority_display(),
        "status": a.get_status_display(),
    }
    if today is not None:
        row["days_overdue"] = (today - a.date).days
    return row


def activity_filters(report: Report, qs: QuerySet[Activity]) -> QuerySet[Activity]:
    if "category" in report.params:
        qs = qs.filter(category_id=report.params["category"])  # type: ignore[misc]
    if "assignee" in report.params:
        qs = qs.filter(assigned_to_id=report.params["assignee"])  # type: ignore[misc]
    return qs


ACTIVITY_FILTERS = [
    Filter("category", "Category", type="category"),
    Filter("assignee", "Assigned to", type="member"),
]


class MonthlyActivities(Report):
    key, title, section = "monthly_activities", "Monthly Farm Activities", "Activities"
    description = "Everything planned for the month and how much got done, by category."
    filters = ACTIVITY_FILTERS

    def compute(self) -> tuple[list[Card], Chart | None, list[Table]]:
        qs = activity_filters(self, m.activities(self.period)).select_related(
            "category", "assigned_to"
        )
        counts = m.activity_counts(self.period, qs)
        rows = [activity_row(a) for a in qs.order_by("date", "title")]
        by_cat = (
            qs.values("category__name")
            .annotate(
                total=Count("pk"),
                completed=Count("pk", filter=Q(status=ActivityStatus.COMPLETED)),
                overdue=Count("pk", filter=Q(status=ActivityStatus.OVERDUE)),
            )
            .order_by("-total")
        )
        cat_rows = [
            {
                "category": r["category__name"] or "Other",
                "total": r["total"],
                "completed": r["completed"],
                "overdue": r["overdue"],
            }
            for r in by_cat
        ]
        summary = [
            Card("total", "Activities", counts["total"]),
            Card("completed", "Completed", counts["completed"]),
            Card("pending", "Pending", counts["pending"]),
            Card("overdue", "Overdue", counts["overdue"]),
            Card("completion_rate", "Completion rate", counts["completion_rate"], "%"),
        ]
        chart = Chart(
            "bar",
            "Activities by category",
            [r["category"] for r in cat_rows],
            [
                {"name": "Completed", "values": [r["completed"] for r in cat_rows]},
                {
                    "name": "Not completed",
                    "values": [r["total"] - r["completed"] for r in cat_rows],
                },
            ],
            stacked=True,
        )
        return (
            summary,
            chart,
            [
                Table("activities", "Activities", ACTIVITY_COLUMNS, rows),
                Table(
                    "by_category",
                    "By category",
                    [
                        Column("category", "Category"),
                        Column("total", "Total", "number"),
                        Column("completed", "Completed", "number"),
                        Column("overdue", "Overdue", "number"),
                    ],
                    cat_rows,
                ),
            ],
        )


class PendingActivities(Report):
    key, title, section = "pending_activities", "Pending Activities", "Activities"
    description = "Open activities (pending or in progress) in the period, soonest first."
    default_period = "next30"
    filters = ACTIVITY_FILTERS

    def compute(self) -> tuple[list[Card], Chart | None, list[Table]]:
        qs = activity_filters(
            self, m.activities(self.period).filter(status__in=m.OPEN)
        ).select_related("category", "assigned_to")
        rows = [activity_row(a) for a in qs.order_by("date", "title")]
        summary = [
            Card("pending", "Pending", qs.count()),
            Card("high", "High priority", qs.filter(priority="high").count()),
            Card("unassigned", "Not assigned", qs.filter(assigned_to=None).count()),
            Card(
                "in_progress", "In progress", qs.filter(status=ActivityStatus.IN_PROGRESS).count()
            ),
        ]
        chart = self.chart(
            "Pending activities by date", pending=m.series(qs, self.period, self.group)
        )
        return summary, chart, [Table("activities", "Pending activities", ACTIVITY_COLUMNS, rows)]


class OverdueActivities(Report):
    key, title, section = "overdue_activities", "Overdue Activities", "Activities"
    description = "Activities that passed their date without being completed."
    default_period = "year"
    filters = ACTIVITY_FILTERS

    def compute(self) -> tuple[list[Card], Chart | None, list[Table]]:
        today = timezone.localdate()
        qs = activity_filters(
            self, m.activities(self.period).filter(status=ActivityStatus.OVERDUE)
        ).select_related("category", "assigned_to")
        rows = [activity_row(a, today) for a in qs.order_by("date")]
        days = [r["days_overdue"] for r in rows]
        by_person = [
            {
                "person": (
                    f"{r['assigned_to__first_name']} {r['assigned_to__last_name']}".strip()
                    or "Not assigned"
                ),
                "count": r["n"],
            }
            for r in qs.values("assigned_to__first_name", "assigned_to__last_name")
            .annotate(n=Count("pk"))
            .order_by("-n")
        ]
        summary = [
            Card("overdue", "Overdue", len(rows)),
            Card("high", "High priority", qs.filter(priority="high").count()),
            Card("average_days", "Average days late", round(sum(days) / len(days)) if days else 0),
            Card("unassigned", "Not assigned", qs.filter(assigned_to=None).count()),
        ]
        chart = Chart(
            "bar",
            "Overdue by person",
            [r["person"] for r in by_person],
            [{"name": "Overdue", "values": [r["count"] for r in by_person]}],
        )
        return (
            summary,
            chart,
            [
                Table(
                    "activities",
                    "Overdue activities",
                    [*ACTIVITY_COLUMNS, Column("days_overdue", "Days late", "number")],
                    rows,
                ),
                Table(
                    "by_person",
                    "By person",
                    [Column("person", "Person"), Column("count", "Overdue", "number")],
                    by_person,
                ),
            ],
        )


# --- 11/12. Quarterly and annual health -----------------------------------------------------------------


HEALTH_LABELS = {
    "vaccinations": "Vaccinations",
    "dewormings": "Dewormings",
    "treatments": "Treatments",
    "observations": "Observations",
    "severe_cases": "Severe cases",
    "vet_visits": "Vet visits",
    "births": "Births",
    "kids_born": "Kids born",
    "deaths": "Deaths",
}


class PeriodHealth(Report):
    section = "Health"

    def compute(self) -> tuple[list[Card], Chart | None, list[Table]]:
        totals = m.health_counts(self.period)
        months = m.buckets(self.period, "month")
        month_rows = []
        for start in months:
            mp = m.month_period(start)
            mp = Period(max(mp.start, self.period.start), min(mp.end, self.period.end))
            month_rows.append({"month": f"{start:%b %Y}", **m.health_counts(mp)})
        herd = m.herd()
        summary = [
            Card(k, HEALTH_LABELS[k], totals[k])
            for k in (
                "vaccinations",
                "dewormings",
                "treatments",
                "observations",
                "births",
                "deaths",
            )
        ]
        summary.append(Card("herd", "Animals now", herd["total"]))
        chart = Chart(
            "bar",
            "Health work per month",
            [r["month"] for r in month_rows],  # type: ignore[misc]
            [
                {"name": HEALTH_LABELS[k], "values": [r[k] for r in month_rows]}
                for k in ("vaccinations", "dewormings", "treatments", "observations")
            ],
        )
        cols = [
            Column("month", "Month"),
            *[Column(k, v, "number") for k, v in HEALTH_LABELS.items()],
        ]
        totals_row = [{"measure": HEALTH_LABELS[k], "total": v} for k, v in totals.items()]
        return (
            summary,
            chart,
            [
                Table("by_month", "By month", cols, month_rows),
                Table(
                    "totals",
                    "Totals",
                    [Column("measure", "Measure"), Column("total", "Total", "number")],
                    totals_row,
                ),
            ],
        )


class QuarterlyHealth(PeriodHealth):
    key, title = "quarterly_health", "Quarterly Health Report"
    description = "Health work, births and deaths for the quarter, month by month."
    default_period = "quarter"


class AnnualHealth(PeriodHealth):
    key, title = "annual_health", "Annual Health Report"
    description = "Health work, births and deaths for the year, month by month."
    default_period = "year"


# --- 15. Staff activity ---------------------------------------------------------------------------------


class StaffActivity(Report):
    key, title, section = "staff_activity", "Staff Activity", "Activities"
    description = "Per person: tasks assigned, completed, overdue, on time, and records entered."

    def compute(self) -> tuple[list[Card], Chart | None, list[Table]]:
        from apps.health import models as hm

        p = self.period
        members = (
            FarmMembership.objects.filter(farm=self.farm)
            .select_related("user")
            .order_by("user__first_name")
        )
        acts = m.activities(p)
        rows = []
        start_dt = dt.datetime.combine(p.start, dt.time.min, tzinfo=timezone.get_current_timezone())
        end_dt = dt.datetime.combine(
            p.end + dt.timedelta(days=1), dt.time.min, tzinfo=timezone.get_current_timezone()
        )
        for ms in members:
            u = ms.user
            mine = acts.filter(assigned_to=u)
            done = mine.filter(status=ActivityStatus.COMPLETED)
            on_time = sum(
                1
                for a in done.only("date", "completed_at")
                if a.completed_at and a.completed_at.date() <= a.date
            )
            records = sum(
                model.objects.filter(
                    created_by=u, created_at__gte=start_dt, created_at__lt=end_dt
                ).count()
                for model in (
                    hm.Vaccination,
                    hm.Deworming,
                    hm.Treatment,
                    hm.HealthObservation,
                    hm.HealthInspection,
                    hm.ParasiteControl,
                )
            )
            rows.append(
                {
                    "person": u.full_name,
                    "role": ms.get_role_display(),
                    "status": "Active" if ms.status == MembershipStatus.ACTIVE else "Inactive",
                    "assigned": mine.count(),
                    "completed": done.count(),
                    "overdue": mine.filter(status=ActivityStatus.OVERDUE).count(),
                    "on_time": percent(on_time, done.count()),
                    "records": records,
                }
            )
        total_done = sum(r["completed"] for r in rows)
        summary = [
            Card("staff", "Staff", sum(1 for r in rows if r["status"] == "Active")),
            Card("assigned", "Tasks assigned", sum(r["assigned"] for r in rows)),
            Card("completed", "Completed", total_done),
            Card("records", "Health records entered", sum(r["records"] for r in rows)),
        ]
        chart = Chart(
            "bar",
            "Tasks per person",
            [r["person"] for r in rows],
            [
                {"name": "Completed", "values": [r["completed"] for r in rows]},
                {"name": "Overdue", "values": [r["overdue"] for r in rows]},
            ],
        )
        cols = [
            Column("person", "Person"),
            Column("role", "Role"),
            Column("status", "Status"),
            Column("assigned", "Assigned", "number"),
            Column("completed", "Completed", "number"),
            Column("overdue", "Overdue", "number"),
            Column("on_time", "On time", "percent"),
            Column("records", "Records entered", "number"),
        ]
        return summary, chart, [Table("staff", "Staff", cols, rows)]


REPORTS: dict[str, type[Report]] = {
    r.key: r
    for r in (
        LivestockRegister,
        AnimalHealthHistory,
        VaccinationReport,
        DewormingReport,
        TreatmentReport,
        DiseaseSurveillance,
        BirthReport,
        MortalityReport,
        BreedingReport,
        MonthlyActivities,
        QuarterlyHealth,
        AnnualHealth,
        PendingActivities,
        OverdueActivities,
        StaffActivity,
    )
}


def catalog() -> list[dict[str, Any]]:
    return [
        {
            "key": r.key,
            "title": r.title,
            "description": r.description,
            "section": r.section,
            "default_period": r.default_period,
            "uses_period": r.uses_period,
            "filters": [
                {
                    "key": f.key,
                    "label": f.label,
                    "type": f.type,
                    "options": [{"value": v, "label": lbl} for v, lbl in f.options],
                }
                for f in r.filters
            ],
        }
        for r in REPORTS.values()
    ]


def location_name(pk: str) -> str:
    loc = Location.objects.filter(pk=pk).first()
    return loc.name if loc else ""


__all__ = ["REPORTS", "ReportData", "catalog", "default_period"]
