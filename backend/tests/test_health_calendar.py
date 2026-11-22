"""Phase 4: health records, their rules, the calendar, activities, recurrence and the overdue job."""

from datetime import date, timedelta

import pytest
from django.utils import timezone

from apps.accounts.models import Role
from apps.calendar import services as cal
from apps.calendar.models import Activity, ActivityStatus
from apps.calendar.views import calendar_range
from apps.health.services import seed_catalogs
from apps.notifications.events import domain_event
from tests.factories import ActivityFactory, AnimalFactory, MedicineFactory, VaccineFactory

pytestmark = pytest.mark.django_db
TODAY = timezone.localdate


@pytest.fixture
def farm(farm_a):  # type: ignore[no-untyped-def]
    cal.seed_categories(farm_a)
    seed_catalogs(farm_a)
    return farm_a


@pytest.fixture
def admin(farm, admin_a, client_for):  # type: ignore[no-untyped-def]
    return client_for(admin_a, farm)


@pytest.fixture
def events():  # type: ignore[no-untyped-def]
    seen = []

    def receiver(sender, event_type, farm_id, **payload):  # type: ignore[no-untyped-def]
        seen.append((event_type, payload))

    domain_event.connect(receiver)
    yield seen
    domain_event.disconnect(receiver)


def iso(d: date) -> str:
    return d.isoformat()


# --- The phase 4 "done when" ----------------------------------------------------------------------------


def test_vaccination_due_date_appears_on_calendar_and_turns_overdue(
    farm, admin, monkeypatch, events
):  # type: ignore[no-untyped-def]
    goat = AnimalFactory(farm=farm, animal_id="YPA-001")
    due = TODAY() + timedelta(days=5)
    res = admin.post(
        "/api/v1/vaccinations",
        {
            "animal": str(goat.pk),
            "vaccine_name": "PPR vaccine",
            "disease_category": "ppr",
            "next_due_date": iso(due),
        },
        format="json",
    )
    assert res.status_code == 201, res.content

    month = admin.get(f"/api/v1/activities/calendar?view=month&date={iso(due)}").json()
    [activity] = [a for a in month["activities"] if a["source"] == "vaccination"]
    assert activity["title"] == "Vaccination due: PPR vaccine – YPA-001"
    assert activity["date"] == iso(due) and activity["status"] == "pending"
    assert activity["category"]["key"] == "vaccination" and activity["reminder_days"] == [7, 1]
    assert activity["animals"][0]["animal_id"] == "YPA-001"
    assert activity["source_record"] == {"type": "vaccination", "id": res.json()["id"]}

    # The day after the due date, the 00:05 job marks it Overdue and emits the event.
    monkeypatch.setattr(cal, "farm_today", lambda farm: due + timedelta(days=1))
    assert cal.mark_overdue(farm) == 1
    assert cal.mark_overdue(farm) == 0  # idempotent
    detail = admin.get(f"/api/v1/activities/{activity['id']}").json()
    assert detail["status"] == "overdue"
    history = admin.get(f"/api/v1/activities/{activity['id']}/history").json()
    assert [(h["from_status"], h["to_status"]) for h in history] == [("pending", "overdue")]
    assert history[0]["by"] == "Smart Farm"
    assert [e for e, _ in events] == []


def test_overdue_task_runs_for_every_farm(farm, farm_b, monkeypatch):  # type: ignore[no-untyped-def]
    from apps.calendar.tasks import mark_overdue_all

    ActivityFactory(farm=farm, date=TODAY() - timedelta(days=1))
    ActivityFactory(farm=farm_b, date=TODAY() - timedelta(days=2), status="in_progress")
    ActivityFactory(farm=farm, date=TODAY() - timedelta(days=1), status="completed")
    ActivityFactory(farm=farm, date=TODAY())
    assert mark_overdue_all() == 2
    assert Activity.unscoped.filter(status="overdue").count() == 2


def test_farm_timezone_decides_the_day(farm, monkeypatch):  # type: ignore[no-untyped-def]
    from datetime import UTC, datetime

    # 22:30 UTC on 1 March is already 2 March in Nairobi (UTC+3).
    monkeypatch.setattr(timezone, "now", lambda: datetime(2027, 3, 1, 22, 30, tzinfo=UTC))
    farm.timezone = "Africa/Nairobi"
    assert cal.farm_today(farm) == date(2027, 3, 2)
    farm.timezone = "America/Lima"
    assert cal.farm_today(farm) == date(2027, 3, 1)
    farm.timezone = "Not/AZone"
    assert cal.farm_today(farm)  # falls back without crashing


# --- Linked activities follow their record -----------------------------------------------------------------


def test_linked_activity_moves_clears_and_is_removed(farm, admin):  # type: ignore[no-untyped-def]
    goat = AnimalFactory(farm=farm)
    vid = admin.post(
        "/api/v1/dewormings",
        {
            "animal": str(goat.pk),
            "product_name": "Albendazole",
            "next_due_date": iso(TODAY() + timedelta(days=30)),
        },
        format="json",
    ).json()["id"]
    linked = lambda: Activity.objects.filter(source="deworming")  # noqa: E731
    assert linked().get().date == TODAY() + timedelta(days=30)
    admin.patch(
        f"/api/v1/dewormings/{vid}",
        {"next_due_date": iso(TODAY() + timedelta(days=40))},
        format="json",
    )
    assert linked().get().date == TODAY() + timedelta(days=40)
    admin.patch(f"/api/v1/dewormings/{vid}", {"next_due_date": None}, format="json")
    assert not linked().exists()
    admin.patch(
        f"/api/v1/dewormings/{vid}",
        {"next_due_date": iso(TODAY() + timedelta(days=10))},
        format="json",
    )
    act = linked().get()
    admin.post(f"/api/v1/activities/{act.pk}/complete")
    # A completed activity stays as history when the record changes or goes.
    admin.patch(
        f"/api/v1/dewormings/{vid}",
        {"next_due_date": iso(TODAY() + timedelta(days=20))},
        format="json",
    )
    assert linked().count() == 2
    assert admin.delete(f"/api/v1/dewormings/{vid}").status_code == 204
    assert list(linked().values_list("status", flat=True)) == ["completed"]


def test_every_health_record_type_with_a_next_date_links_an_activity(farm, admin):  # type: ignore[no-untyped-def]
    goat = AnimalFactory(farm=farm, animal_id="YPA-007")
    later = iso(TODAY() + timedelta(days=14))
    posts = {
        "treatments": {"animal": str(goat.pk), "diagnosis": "Foot rot", "follow_up_date": later},
        "vet-visits": {
            "vet_name": "Dr. Samuel Mutua",
            "reason": "Review",
            "animals": [str(goat.pk)],
            "next_visit_date": later,
        },
        "inspections": {
            "inspector": "Grace",
            "result": "good",
            "score": 8,
            "next_inspection_date": later,
        },
        "parasite-control": {
            "method": "spraying",
            "target": "Ticks",
            "product_name": "Amitraz",
            "next_due_date": later,
        },
    }
    for url, body in posts.items():
        assert admin.post(f"/api/v1/{url}", body, format="json").status_code == 201, url
    titles = sorted(Activity.objects.values_list("title", flat=True))
    assert titles == [
        "Health inspection",
        "Spraying due (Ticks) – whole herd",
        "Treatment follow-up: Foot rot – YPA-007",
        "Vet visit – Dr. Samuel Mutua",
    ]


def test_health_record_validation(farm, admin):  # type: ignore[no-untyped-def]
    goat = AnimalFactory(farm=farm)
    group = goat.group
    tomorrow = iso(TODAY() + timedelta(days=1))
    res = admin.post(
        "/api/v1/vaccinations",
        {"animal": str(goat.pk), "date": tomorrow, "next_due_date": iso(TODAY())},
        format="json",
    )
    errors = res.json()["errors"]
    assert "date" in errors and "next_due_date" in errors
    missing = admin.post("/api/v1/vaccinations", {"animal": str(goat.pk)}, format="json").json()[
        "errors"
    ]
    assert "disease_category" in missing or "vaccine" in missing
    assert group is None
    from tests.factories import AnimalGroupFactory

    both = admin.post(
        "/api/v1/dewormings",
        {
            "animal": str(goat.pk),
            "group": str(AnimalGroupFactory(farm=farm).pk),
            "product_name": "X",
        },
        format="json",
    )
    assert both.json()["errors"]["group"] == ["Choose one animal or one group, not both."]


def test_vaccine_from_catalog_fills_details(farm, admin):  # type: ignore[no-untyped-def]
    vaccine = VaccineFactory(
        farm=farm,
        name="CCPP vaccine (Kevevapi)",
        disease_category="ccpp",
        default_dose="1 ml",
        route="sc",
    )
    res = admin.post("/api/v1/vaccinations", {"vaccine": str(vaccine.pk)}, format="json")
    assert res.status_code == 201
    body = res.json()
    assert body["disease_category"] == "ccpp" and body["dosage"] == "1 ml" and body["route"] == "sc"
    assert body["vaccine_label"] == "CCPP vaccine (Kevevapi)" and body["group_label"] is None


# --- Treatment rules and withdrawal -----------------------------------------------------------------------


def test_treatment_sets_and_clears_under_treatment(farm, admin):  # type: ignore[no-untyped-def]
    goat = AnimalFactory(farm=farm)
    first = admin.post(
        "/api/v1/treatments", {"animal": str(goat.pk), "diagnosis": "Pneumonia"}, format="json"
    ).json()
    second = admin.post(
        "/api/v1/treatments", {"animal": str(goat.pk), "diagnosis": "Wound"}, format="json"
    ).json()
    goat.refresh_from_db()
    assert goat.health_status == "under_treatment"
    admin.post(
        f"/api/v1/treatments/{first['id']}/resolve", {"notes": "Recovered well"}, format="json"
    )
    goat.refresh_from_db()
    assert goat.health_status == "under_treatment"  # the wound is still open
    resolved = admin.post(f"/api/v1/treatments/{second['id']}/resolve", {}, format="json").json()
    assert resolved["status"] == "resolved" and resolved["resolved_date"] == iso(TODAY())
    goat.refresh_from_db()
    assert goat.health_status == "healthy"


def test_resolved_pregnant_doe_returns_to_pregnant(farm, admin):  # type: ignore[no-untyped-def]
    doe = AnimalFactory(farm=farm, breeding_status="pregnant", health_status="pregnant")
    t = admin.post(
        "/api/v1/treatments", {"animal": str(doe.pk), "diagnosis": "Mastitis"}, format="json"
    ).json()
    admin.post(f"/api/v1/treatments/{t['id']}/resolve", {}, format="json")
    doe.refresh_from_db()
    assert doe.health_status == "pregnant"


def test_deleting_open_treatment_reevaluates_status(farm, admin):  # type: ignore[no-untyped-def]
    goat = AnimalFactory(farm=farm)
    t = admin.post(
        "/api/v1/treatments", {"animal": str(goat.pk), "diagnosis": "Bloat"}, format="json"
    ).json()
    admin.delete(f"/api/v1/treatments/{t['id']}")
    goat.refresh_from_db()
    assert goat.health_status == "healthy"


def test_withdrawal_period_flags_animal(farm, admin):  # type: ignore[no-untyped-def]
    goat = AnimalFactory(farm=farm)
    drug = MedicineFactory(farm=farm, name="Oxytet LA", withdrawal_days=28)
    t = admin.post(
        "/api/v1/treatments",
        {"animal": str(goat.pk), "diagnosis": "Pneumonia", "medication": str(drug.pk)},
        format="json",
    ).json()
    assert t["withdrawal_until"] == iso(TODAY() + timedelta(days=28))
    assert admin.get(f"/api/v1/animals/{goat.pk}").json()["withdrawal_until"] == iso(
        TODAY() + timedelta(days=28)
    )
    assert admin.get("/api/v1/health/summary").json()["under_withdrawal"] == 1
    # A manual date wins.
    t2 = admin.patch(
        f"/api/v1/treatments/{t['id']}",
        {"withdrawal_until": iso(TODAY() - timedelta(days=1))},
        format="json",
    ).json()
    assert t2["withdrawal_until"] == iso(TODAY() - timedelta(days=1))
    assert admin.get(f"/api/v1/animals/{goat.pk}").json()["withdrawal_until"] is None


def test_severe_observation_raises_health_alert(farm, admin, events):  # type: ignore[no-untyped-def]
    goat = AnimalFactory(farm=farm, animal_id="YPA-003")
    admin.post(
        "/api/v1/observations",
        {"animal": str(goat.pk), "symptoms": "Slight limp", "severity": "mild"},
        format="json",
    )
    assert events == []
    admin.post(
        "/api/v1/observations",
        {"animal": str(goat.pk), "symptoms": "Off feed", "temperature_c": "41.2"},
        format="json",
    )
    [(name, payload)] = events
    assert name == "health.alert" and payload["urgent"] is True and "41.2" in payload["message"]
    bad = admin.post(
        "/api/v1/observations",
        {"animal": str(goat.pk), "symptoms": "x", "temperature_c": "55"},
        format="json",
    )
    assert "temperature_c" in bad.json()["errors"]


def test_health_events_on_animal_timeline(farm, admin):  # type: ignore[no-untyped-def]
    goat = AnimalFactory(farm=farm)
    admin.post(
        "/api/v1/vaccinations",
        {"animal": str(goat.pk), "vaccine_name": "PPR", "disease_category": "ppr"},
        format="json",
    )
    t = admin.post(
        "/api/v1/treatments", {"animal": str(goat.pk), "diagnosis": "Pneumonia"}, format="json"
    ).json()
    admin.post(f"/api/v1/treatments/{t['id']}/resolve", {}, format="json")
    admin.post(
        "/api/v1/vet-visits",
        {"vet_name": "Dr. Mutua", "reason": "Check", "animals": [str(goat.pk)]},
        format="json",
    )
    titles = {e["title"] for e in admin.get(f"/api/v1/animals/{goat.pk}/timeline").json()}
    assert {
        "Vaccinated: PPR",
        "Treatment: Pneumonia",
        "Recovered: Pneumonia",
        "Vet visit: Dr. Mutua",
        "Health status: Under Treatment",
    } <= titles


def test_health_summary(farm, admin):  # type: ignore[no-untyped-def]
    AnimalFactory(farm=farm, health_status="sick")
    AnimalFactory(farm=farm)
    ActivityFactory(
        farm=farm, category=cal.category(farm.pk, "vaccination"), date=TODAY() + timedelta(days=10)
    )
    ActivityFactory(
        farm=farm,
        category=cal.category(farm.pk, "deworming"),
        date=TODAY() - timedelta(days=1),
        status="overdue",
    )
    body = admin.get("/api/v1/health/summary").json()
    assert body["status_counts"] == {"sick": 1, "healthy": 1}
    assert body["vaccinations_due_30_days"] == 1 and body["overdue_health_activities"] == 1


# --- Roles ------------------------------------------------------------------------------------------------


def test_attendant_records_health_but_cannot_delete_or_edit_catalogs(farm, member, client_for):  # type: ignore[no-untyped-def]
    attendant = client_for(member(farm, Role.LIVESTOCK_ATTENDANT), farm)
    goat = AnimalFactory(farm=farm)
    obs = attendant.post(
        "/api/v1/observations", {"animal": str(goat.pk), "symptoms": "Coughing"}, format="json"
    )
    assert obs.status_code == 201
    assert (
        attendant.patch(
            f"/api/v1/observations/{obs.json()['id']}",
            {"symptoms": "Coughing a lot"},
            format="json",
        ).status_code
        == 200
    )
    assert attendant.delete(f"/api/v1/observations/{obs.json()['id']}").status_code == 403
    assert len(attendant.get("/api/v1/vaccines").json()) == 7
    assert (
        attendant.post("/api/v1/vaccines", {"name": "X", "disease_category": "ppr"}).status_code
        == 403
    )


def test_attendant_sees_and_works_only_own_tasks(farm, admin, member, client_for):  # type: ignore[no-untyped-def]
    peter = member(farm, Role.LIVESTOCK_ATTENDANT)
    attendant = client_for(peter, farm)
    mine = ActivityFactory(farm=farm, assigned_to=peter, title="Dip the herd")
    ActivityFactory(farm=farm, title="Someone else's")
    assert [a["title"] for a in attendant.get("/api/v1/activities").json()["results"]] == [
        "Dip the herd"
    ]
    # The calendar still shows the whole farm (view only).
    assert len(attendant.get("/api/v1/activities/calendar?view=agenda").json()["activities"]) == 2
    assert attendant.post(f"/api/v1/activities/{mine.pk}/start").json()["status"] == "in_progress"
    assert (
        attendant.post(f"/api/v1/activities/{mine.pk}/notes", {"text": "Half done"}).status_code
        == 201
    )
    done = attendant.post(f"/api/v1/activities/{mine.pk}/complete", {"note": "All 20 dipped"})
    assert (
        done.json()["status"] == "completed" and done.json()["completed_by_name"] == peter.full_name
    )
    assert attendant.post(f"/api/v1/activities/{mine.pk}/cancel").status_code == 403
    assert (
        attendant.post("/api/v1/activities", {"title": "x", "date": iso(TODAY())}).status_code
        == 403
    )
    assert (
        attendant.post("/api/v1/activity-templates/health-calendar-2027/apply").status_code == 403
    )
    other = Activity.objects.exclude(pk=mine.pk).get()
    assert attendant.post(f"/api/v1/activities/{other.pk}/complete").status_code == 404
    hist = admin.get(f"/api/v1/activities/{mine.pk}/history").json()
    assert [h["to_status"] for h in hist] == ["in_progress", "completed"]
    assert hist[1]["note"] == "All 20 dipped"


# --- Activities -------------------------------------------------------------------------------------------


def test_create_assign_filter_and_transitions(farm, admin, member, events):  # type: ignore[no-untyped-def]
    grace = member(farm, Role.FARM_MANAGER)
    stranger = member(farm_b := AnimalFactory().farm, Role.FARM_MANAGER)
    goat = AnimalFactory(farm=farm)
    vacc = cal.category(farm.pk, "vaccination")
    res = admin.post(
        "/api/v1/activities",
        {
            "title": "Vaccinate kids",
            "date": iso(TODAY() + timedelta(days=2)),
            "category": str(vacc.pk),
            "priority": "high",
            "assigned_to": str(grace.pk),
            "animals": [str(goat.pk)],
            "start_time": "08:00",
            "end_time": "09:30",
            "reminder_days": [3, 1],
        },
        format="json",
    )
    assert res.status_code == 201, res.content
    body = res.json()
    assert body["assigned_to"]["name"] == grace.full_name and body["all_day"] is False
    assert events[-1][0] == "task.assigned"
    bad = admin.post(
        "/api/v1/activities",
        {"title": "x", "date": iso(TODAY()), "assigned_to": str(stranger.pk)},
        format="json",
    )
    assert "assigned_to" in bad.json()["errors"]  # not a member of this farm
    times = admin.post(
        "/api/v1/activities",
        {"title": "x", "date": iso(TODAY()), "start_time": "10:00", "end_time": "09:00"},
        format="json",
    )
    assert times.json()["errors"]["end_time"] == ["The end time must be after the start time."]
    assert farm_b != farm

    past = admin.post(
        "/api/v1/activities",
        {"title": "Late", "date": iso(TODAY() - timedelta(days=3))},
        format="json",
    ).json()
    assert past["status"] == "overdue"
    assert admin.get("/api/v1/activities?status=overdue").json()["count"] == 1
    assert admin.get("/api/v1/activities?category=vaccination&priority=high").json()["count"] == 1
    assert admin.get(f"/api/v1/activities?assignee={grace.pk}").json()["count"] == 1
    assert admin.get("/api/v1/activities?assignee=none").json()["count"] == 1
    assert (
        admin.get(
            f"/api/v1/activities?from={iso(TODAY())}&to={iso(TODAY() + timedelta(days=5))}"
        ).json()["count"]
        == 1
    )

    # Rescheduling an overdue task into the future makes it pending again.
    moved = admin.patch(
        f"/api/v1/activities/{past['id']}",
        {"date": iso(TODAY() + timedelta(days=1))},
        format="json",
    ).json()
    assert moved["status"] == "pending"
    admin.post(f"/api/v1/activities/{past['id']}/cancel", {"note": "Not needed"}, format="json")
    again = admin.post(f"/api/v1/activities/{past['id']}/cancel")
    assert again.status_code == 400 and "cannot be cancel" in again.json()["errors"]["detail"][0]
    assert admin.post(f"/api/v1/activities/{past['id']}/reopen").json()["status"] == "pending"
    unassigned = admin.post(
        f"/api/v1/activities/{body['id']}/assign", {"assigned_to": None}, format="json"
    ).json()
    assert unassigned["assigned_to"] is None


def test_reopening_a_past_task_makes_it_overdue(farm, admin):  # type: ignore[no-untyped-def]
    task = ActivityFactory(farm=farm, date=TODAY() - timedelta(days=2), status="completed")
    assert admin.post(f"/api/v1/activities/{task.pk}/reopen").json()["status"] == "overdue"


# --- Recurrence -------------------------------------------------------------------------------------------


def _series(farm):  # type: ignore[no-untyped-def]
    return list(Activity.objects.filter(title="Weigh kids").order_by("date"))


def test_monthly_series_generated_twelve_months_ahead(farm, admin):  # type: ignore[no-untyped-def]
    start = TODAY() + timedelta(days=1)
    res = admin.post(
        "/api/v1/activities",
        {"title": "Weigh kids", "date": iso(start), "repeat": "monthly"},
        format="json",
    )
    assert res.json()["recurrence_rule"] == "FREQ=MONTHLY" and res.json()["is_recurring"] is True
    occurrences = _series(farm)
    assert 12 <= len(occurrences) <= 13
    assert occurrences[-1].date <= start + timedelta(days=366)
    head = occurrences[0]
    assert cal.extend_series(head) == 0  # already up to the horizon


def test_quarterly_until_and_bad_rule(farm, admin):  # type: ignore[no-untyped-def]
    start = TODAY() + timedelta(days=1)
    admin.post(
        "/api/v1/activities",
        {
            "title": "Weigh kids",
            "date": iso(start),
            "repeat": "quarterly",
            "repeat_until": iso(start + timedelta(days=200)),
        },
        format="json",
    )
    assert len(_series(farm)) == 3
    bad = admin.post(
        "/api/v1/activities",
        {"title": "x", "date": iso(start), "recurrence_rule": "EVERY TUESDAY"},
        format="json",
    )
    assert bad.json()["errors"]["recurrence_rule"] == ["This repeat rule is not valid."]


def test_edit_this_or_following(farm, admin):  # type: ignore[no-untyped-def]
    start = TODAY() + timedelta(days=1)
    admin.post(
        "/api/v1/activities",
        {"title": "Weigh kids", "date": iso(start), "repeat": "weekly"},
        format="json",
    )
    occ = _series(farm)
    third = occ[2]
    # This one only.
    admin.patch(
        f"/api/v1/activities/{third.pk}",
        {"title": "Weigh kids (vet present)", "scope": "this"},
        format="json",
    )
    assert Activity.objects.get(pk=third.pk).title == "Weigh kids (vet present)"
    assert Activity.objects.get(pk=occ[3].pk).title == "Weigh kids"
    # This and following: move one day later and change priority.
    fifth = occ[4]
    admin.patch(
        f"/api/v1/activities/{fifth.pk}",
        {"date": iso(fifth.date + timedelta(days=1)), "priority": "high", "scope": "following"},
        format="json",
    )
    after = Activity.objects.filter(date__gt=fifth.date).order_by("date")
    assert all(a.priority == "high" for a in after)
    assert all((a.date - start).days % 7 == 1 for a in after)
    assert Activity.objects.get(pk=occ[3].pk).priority == "medium"
    # Changing how it repeats needs "following" on an occurrence.
    res = admin.patch(f"/api/v1/activities/{occ[1].pk}", {"repeat": "monthly"}, format="json")
    assert "scope" in res.json()["errors"]


def test_change_rule_from_an_occurrence_splits_series(farm, admin):  # type: ignore[no-untyped-def]
    start = TODAY() + timedelta(days=1)
    admin.post(
        "/api/v1/activities",
        {"title": "Weigh kids", "date": iso(start), "repeat": "weekly"},
        format="json",
    )
    occ = _series(farm)
    split = occ[3]
    admin.patch(
        f"/api/v1/activities/{split.pk}", {"repeat": "monthly", "scope": "following"}, format="json"
    )
    head = Activity.objects.get(pk=occ[0].pk)
    assert "UNTIL=" in head.recurrence_rule
    weekly = Activity.objects.filter(date__lt=split.date)
    assert weekly.count() == 3
    assert cal.extend_series(head) == 0  # capped: no duplicates come back
    new = Activity.objects.get(pk=split.pk)
    assert new.recurrence_rule == "FREQ=MONTHLY" and new.series_id is None
    assert Activity.objects.filter(series=new).count() >= 11


def test_delete_this_and_following(farm, admin):  # type: ignore[no-untyped-def]
    start = TODAY() + timedelta(days=1)
    admin.post(
        "/api/v1/activities",
        {"title": "Weigh kids", "date": iso(start), "repeat": "weekly"},
        format="json",
    )
    occ = _series(farm)
    assert admin.delete(f"/api/v1/activities/{occ[1].pk}").status_code == 204
    assert len(_series(farm)) == len(occ) - 1
    admin.delete(f"/api/v1/activities/{occ[4].pk}?scope=following")
    assert len(_series(farm)) == 3
    assert cal.extend_series(Activity.objects.get(pk=occ[0].pk)) == 0


def test_extend_series_task(farm, admin):  # type: ignore[no-untyped-def]
    from apps.calendar.tasks import extend_all_series

    admin.post(
        "/api/v1/activities",
        {"title": "Weigh kids", "date": iso(TODAY() + timedelta(days=1)), "repeat": "monthly"},
        format="json",
    )
    Activity.objects.filter(title="Weigh kids", series__isnull=False).order_by(
        "-date"
    ).first().hard_delete()
    assert extend_all_series() == 1


# --- Template and calendar views ------------------------------------------------------------------------------


def test_apply_2027_health_calendar_once(farm, admin):  # type: ignore[no-untyped-def]
    [template] = admin.get("/api/v1/activity-templates").json()
    assert template["count"] == 23 and template["applied"] == 0
    assert admin.post("/api/v1/activity-templates/health-calendar-2027/apply").json() == {
        "created": 23,
        "skipped": 0,
    }
    assert admin.post("/api/v1/activity-templates/health-calendar-2027/apply").json() == {
        "created": 0,
        "skipped": 23,
    }
    assert admin.get("/api/v1/activity-templates").json()[0]["applied"] == 23
    jan = admin.get("/api/v1/activities/calendar?view=month&date=2027-01-15").json()
    titles = [a["title"] for a in jan["activities"] if a["date"].startswith("2027-01")]
    assert titles[0] == "Opening herd health assessment"
    dec = admin.get("/api/v1/activities/calendar?view=month&date=2027-12-01").json()
    assert any(a["title"].startswith("Annual health review") for a in dec["activities"])
    assert all(a["category"] for a in jan["activities"])
    assert admin.post("/api/v1/activity-templates/nope/apply").status_code == 400


@pytest.mark.parametrize(
    ("view", "day", "start", "end"),
    [
        ("month", date(2027, 1, 15), date(2026, 12, 28), date(2027, 1, 31)),
        ("month", date(2027, 2, 10), date(2027, 2, 1), date(2027, 2, 28)),
        ("week", date(2027, 1, 15), date(2027, 1, 11), date(2027, 1, 17)),
        ("day", date(2027, 1, 15), date(2027, 1, 15), date(2027, 1, 15)),
        ("agenda", date(2027, 1, 15), date(2027, 1, 15), date(2027, 2, 14)),
    ],
)
def test_calendar_ranges(view, day, start, end):  # type: ignore[no-untyped-def]
    assert calendar_range(view, day) == (start, end)


def test_calendar_view_validation_and_default(farm, admin):  # type: ignore[no-untyped-def]
    assert admin.get("/api/v1/activities/calendar?view=year").status_code == 400
    assert admin.get("/api/v1/activities/calendar?date=2027-13-01").status_code == 400
    assert (
        admin.get("/api/v1/activities/calendar").json()["view"] == "month"
    )  # the farm's default view


def test_new_farm_gets_categories_and_catalogs(client):  # type: ignore[no-untyped-def]
    from rest_framework.test import APIClient

    from apps.accounts.models import Farm
    from apps.calendar.models import ActivityCategory
    from apps.health.models import Medicine, Vaccine

    APIClient().post(
        "/api/v1/auth/signup",
        {
            "first_name": "A",
            "last_name": "B",
            "email": "a@b.ke",
            "phone": "0712000001",
            "password": "Green-Pasture-27",
            "farm_name": "New Farm",
            "livestock_types": ["goats"],
        },
        format="json",
    )
    farm = Farm.objects.get(name="New Farm")
    assert ActivityCategory.unscoped.filter(farm=farm).count() == 8
    assert Vaccine.unscoped.filter(farm=farm).count() == 7
    assert Medicine.unscoped.filter(farm=farm).count() == 8


def test_status_choices_cover_the_badges():  # type: ignore[no-untyped-def]
    assert [c for c, _ in ActivityStatus.choices] == [
        "pending",
        "in_progress",
        "completed",
        "overdue",
        "cancelled",
    ]


def test_assignees_list_for_managers(farm, member, client_for):  # type: ignore[no-untyped-def]
    manager = member(farm, Role.FARM_MANAGER, user__first_name="Grace")
    member(farm, Role.LIVESTOCK_ATTENDANT, user__first_name="Peter")
    member(farm, Role.LIVESTOCK_ATTENDANT, user__first_name="Ali", status="inactive")
    rows = client_for(manager, farm).get("/api/v1/activities/assignees").json()
    assert [r["name"].split()[0] for r in rows] == ["Grace", "Peter"]
    assert rows[1]["role_label"] == "Livestock Attendant"


def test_mark_overdue_command(farm):  # type: ignore[no-untyped-def]
    from io import StringIO

    from django.core.management import call_command

    ActivityFactory(farm=farm, date=TODAY() + timedelta(days=2))
    out = StringIO()
    call_command(
        "mark_overdue",
        "--as-of",
        iso(TODAY() + timedelta(days=3)),
        f"--farm={farm.slug}",
        stdout=out,
    )
    assert "Marked 1 activities" in out.getvalue()
    assert Activity.objects.get().status == "overdue"
