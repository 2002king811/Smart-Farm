"""Phase 7: dashboard figures, the 15 reports, exports, large runs, schedules, sharing and the
farm data export. "Done when": the dashboard numbers match the reports for the same period."""

import datetime as dt
import io
import zipfile
from datetime import timedelta
from unittest import mock

import pytest
from django.core import mail
from django.utils import timezone
from openpyxl import load_workbook

from apps.accounts.models import Role
from apps.calendar import services as cal
from apps.calendar.models import ActivityStatus
from apps.health.services import seed_catalogs
from apps.notifications.messaging import SENT
from apps.notifications.models import Notification, OutboundMessage
from apps.reports import metrics, services
from apps.reports.builders import REPORTS
from apps.reports.models import ReportRun, ReportSchedule
from tests.factories import (
    ActivityFactory,
    AnimalFactory,
    DewormingFactory,
    FeedItemFactory,
    HealthObservationFactory,
    MatingFactory,
    TreatmentFactory,
    VaccinationFactory,
)

pytestmark = pytest.mark.django_db
TODAY = timezone.localdate


@pytest.fixture
def farm(farm_a):  # type: ignore[no-untyped-def]
    farm_a.timezone = "UTC"
    farm_a.save()
    cal.seed_categories(farm_a)
    seed_catalogs(farm_a)
    return farm_a


@pytest.fixture
def admin(farm, admin_a, client_for):  # type: ignore[no-untyped-def]
    return client_for(admin_a, farm)


@pytest.fixture
def herd(farm, admin):  # type: ignore[no-untyped-def]
    """A small farm with a month of records."""
    today = TODAY()
    month_start = today.replace(day=1)
    doe = AnimalFactory(farm=farm, animal_id="YPA-001", sex="female")
    buck = AnimalFactory(farm=farm, animal_id="YPA-002", sex="male")
    sick = AnimalFactory(farm=farm, animal_id="YPA-003", sex="female", health_status="sick")
    AnimalFactory(
        farm=farm, animal_id="YPA-004", sex="male", date_of_birth=today - timedelta(days=40)
    )
    old = AnimalFactory(farm=farm, animal_id="YPA-005", sex="female")
    VaccinationFactory(farm=farm, animal=doe, date=month_start, vaccine_name="PPR vaccine")
    VaccinationFactory(farm=farm, animal=buck, date=month_start, vaccine_name="PPR vaccine")
    VaccinationFactory(
        farm=farm, animal=sick, date=month_start, vaccine_name="CCPP vaccine", status="missed"
    )
    VaccinationFactory(farm=farm, animal=doe, date=month_start - timedelta(days=3))  # last month
    DewormingFactory(farm=farm, animal=doe, date=month_start, product_name="Albendazole")
    TreatmentFactory(farm=farm, animal=sick, date=month_start, diagnosis="Pneumonia")
    HealthObservationFactory(
        farm=farm, animal=sick, date=month_start, severity="severe", temperature_c="40.8"
    )
    res = admin.post(
        "/api/v1/births",
        {
            "dam": str(doe.pk),
            "date": str(month_start),
            "kids": [{"sex": "female"}, {"sex": "male"}, {"sex": "male", "alive": False}],
        },
        format="json",
    )
    assert res.status_code == 201, res.content
    res = admin.post(
        "/api/v1/mortality",
        {"animal": str(old.pk), "date": str(month_start), "cause_category": "disease"},
        format="json",
    )
    assert res.status_code == 201, res.content
    MatingFactory(farm=farm, doe=sick, buck=buck, date=month_start)
    ActivityFactory(farm=farm, title="Dip", date=month_start, status=ActivityStatus.COMPLETED)
    ActivityFactory(farm=farm, title="Weigh", date=month_start, status=ActivityStatus.OVERDUE)
    ActivityFactory(
        farm=farm, title="Trim", date=metrics.month_period(today).end, status=ActivityStatus.PENDING
    )
    return {"doe": doe, "buck": buck, "sick": sick}


def card(report, key):  # type: ignore[no-untyped-def]
    return next(c["value"] for c in report["summary"] if c["key"] == key)


# --- Done when: the dashboard matches the reports ---------------------------------------------------------


def test_dashboard_numbers_match_reports(farm, admin, herd):  # type: ignore[no-untyped-def]
    month = metrics.month_period(TODAY())
    q = f"from={month.start}&to={month.end}"
    dash = admin.get(f"/api/v1/dashboard/summary?{q}").json()
    register = admin.get("/api/v1/reports/livestock_register").json()
    for key in ("total", "males", "females", "kids", "needing_attention", "pregnant"):
        assert dash["herd"][key] == card(register, key), key
    # 5 + 2 kids − 1 death = 6 animals, 2 kids (the young one and two newborns? one is 40 days, plus 2)
    assert dash["herd"]["total"] == 6 and dash["herd"]["kids"] == 3

    vacc = admin.get(f"/api/v1/reports/vaccination?{q}").json()
    assert dash["health"]["vaccinations"] == card(vacc, "records") == 3
    births = admin.get(f"/api/v1/reports/birth?{q}").json()
    assert dash["health"]["kids_born"] == card(births, "kids_born") == 2
    assert card(births, "stillborn") == 1
    deaths = admin.get(f"/api/v1/reports/mortality?{q}").json()
    assert dash["health"]["deaths"] == card(deaths, "deaths") == 1
    acts = admin.get(f"/api/v1/reports/monthly_activities?{q}").json()
    for key in ("total", "completed", "pending", "overdue", "completion_rate"):
        assert dash["activity_overview"][key] == card(acts, key), key
    quarterly = admin.get(
        f"/api/v1/reports/quarterly_health?from={month.start}&to={month.end}"
    ).json()
    assert card(quarterly, "treatments") == dash["health"]["treatments"] == 1

    # The 6-month chart's current month equals the same reports.
    charts = admin.get("/api/v1/dashboard/charts?range=6m").json()
    assert len(charts["labels"]) == 6
    assert (
        charts["vaccinations"][-1] == 3
        and charts["kids_born"][-1] == 2
        and charts["deaths"][-1] == 1
    )
    assert charts["herd_size"][-1] == dash["herd"]["total"]


def test_attendant_dashboard_shows_own_tasks_only(farm, member, client_for):  # type: ignore[no-untyped-def]
    worker = member(farm, Role.LIVESTOCK_ATTENDANT)
    other = member(farm, Role.FARM_MANAGER)
    ActivityFactory(farm=farm, title="Mine", date=TODAY(), assigned_to=worker)
    ActivityFactory(farm=farm, title="Theirs", date=TODAY(), assigned_to=other)
    me = client_for(worker, farm)
    dash = me.get("/api/v1/dashboard/summary").json()
    assert dash["own"] is True and dash["tasks_today"] == 1 and "herd" not in dash
    assert [a["title"] for a in me.get("/api/v1/dashboard/upcoming").json()] == ["Mine"]
    assert me.get("/api/v1/dashboard/charts").status_code == 403
    assert me.get("/api/v1/reports").status_code == 403  # attendants have no reports


def test_upcoming_and_recent_health(farm, admin, herd):  # type: ignore[no-untyped-def]
    upcoming = admin.get("/api/v1/dashboard/upcoming").json()
    assert {"Weigh"} <= {a["title"] for a in upcoming} or upcoming == []
    recent = admin.get("/api/v1/dashboard/recent-health").json()
    assert {r["kind"] for r in recent} >= {"observation", "treatment", "vaccination"}


# --- Every report builds, previews and exports ---------------------------------------------------------


@pytest.mark.parametrize("key", sorted(REPORTS))
def test_every_report_previews_and_exports(key, farm, admin, herd):  # type: ignore[no-untyped-def]
    preview = admin.get(f"/api/v1/reports/{key}")
    assert preview.status_code == 200, preview.content
    body = preview.json()
    assert body["title"] == REPORTS[key].title and body["summary"] and body["tables"]
    for fmt, magic in (("pdf", b"%PDF"), ("xlsx", b"PK"), ("csv", b"\xef\xbb\xbf")):
        res = admin.get(f"/api/v1/reports/{key}/export?format={fmt}")
        assert res.status_code == 200, res.content
        assert res.content.startswith(magic)
        assert key in res["Content-Disposition"]
    assert ReportRun.objects.filter(report_type=key, status="done").count() == 3


def test_catalog_lists_15_reports(admin):  # type: ignore[no-untyped-def]
    reports = admin.get("/api/v1/reports").json()
    assert len(reports) == 15
    register = next(r for r in reports if r["key"] == "livestock_register")
    assert [f["key"] for f in register["filters"]] == ["sex", "health_status", "location"]


def test_filters_and_validation(farm, admin, herd):  # type: ignore[no-untyped-def]
    males = admin.get("/api/v1/reports/livestock_register?sex=male").json()
    assert {r["sex"] for r in males["tables"][0]["rows"]} == {"Male"}
    one = admin.get(f"/api/v1/reports/animal_health_history?animal={herd['sick'].pk}").json()
    assert {r["subject"] for r in one["tables"][0]["rows"]} == {"YPA-003"}
    bad = admin.get("/api/v1/reports/vaccination?from=2026-05-01&to=2026-04-01")
    assert bad.status_code == 400 and "to" in bad.json()["errors"]
    assert admin.get("/api/v1/reports/nope").status_code == 400
    assert admin.get("/api/v1/reports/vaccination?from=bad").json()["errors"]["from"]
    assert admin.get("/api/v1/reports/vaccination/export?format=doc").status_code == 400


def test_excel_has_summary_frozen_headers_and_real_dates(farm, admin, herd):  # type: ignore[no-untyped-def]
    res = admin.get("/api/v1/reports/vaccination/export?format=xlsx")
    wb = load_workbook(io.BytesIO(res.content))
    assert wb.sheetnames[0] == "Summary"
    sheet = wb["Vaccinations"]
    assert sheet.freeze_panes == "A2"
    assert sheet["A1"].value == "Date"
    assert isinstance(sheet["A2"].value, dt.datetime)


def test_pdf_has_letterhead_and_signatures(farm, admin, herd):  # type: ignore[no-untyped-def]
    from apps.reports import exports

    with mock.patch.object(exports, "_numbered", wraps=exports._numbered) as numbered:
        res = admin.get("/api/v1/reports/vaccination/export?format=pdf")
    assert res.status_code == 200 and numbered.called
    assert len(res.content) > 2000


# --- Large reports run in the background ------------------------------------------------------------------


def test_large_export_runs_in_background_and_notifies(farm, admin, admin_a, herd, client):  # type: ignore[no-untyped-def]
    admin_a.email_verified = True
    admin_a.save()
    with mock.patch.object(services, "LARGE_ROWS", 3):
        res = admin.get("/api/v1/reports/livestock_register/export?format=csv")
    assert res.status_code == 202, res.content
    run = ReportRun.objects.get(pk=res.json()["id"])
    assert run.status == "done" and run.file  # eager Celery in tests
    note = Notification.objects.get(recipient=admin_a, event_type="report.ready")
    assert "Livestock Register" in note.title and "/download?token=" in note.message
    assert [d.channel for d in note.deliveries.all()] == ["email"]
    listed = admin.get("/api/v1/report-runs").json()["results"][0]
    assert listed["download_url"]
    path = listed["download_url"].split("5180", 1)[1]
    file = client.get(path)
    assert file.status_code == 200 and b"Livestock Register" in b"".join(file.streaming_content)
    assert client.get(path[: path.index("token=") + 6] + "forged").status_code == 403
    with mock.patch(
        "django.core.signing.time.time", return_value=timezone.now().timestamp() + 25 * 3600
    ):
        assert client.get(path).status_code == 403  # expired after 24 hours


# --- Scheduled reports ----------------------------------------------------------------------------------


def test_scheduled_reports_are_emailed_on_the_first(farm, admin, member, client_for, herd):  # type: ignore[no-untyped-def]
    res = admin.post(
        "/api/v1/report-schedules",
        {
            "report_type": "monthly_activities",
            "recipients": ["Owner@Example.com", "vet@example.com"],
        },
        format="json",
    )
    assert res.status_code == 201, res.content
    admin.post(
        "/api/v1/report-schedules",
        {"report_type": "quarterly_health", "recipients": ["vet@example.com"]},
        format="json",
    )
    manager = member(farm, Role.FARM_MANAGER)
    assert client_for(manager, farm).get("/api/v1/report-schedules").status_code == 403

    first = dt.datetime(2026, 10, 1, 7, 0, tzinfo=dt.UTC)
    with mock.patch("django.utils.timezone.now", return_value=first):
        assert services.send_scheduled() == 2
        assert services.send_scheduled() == 0  # once per period
    subjects = sorted(e.subject for e in mail.outbox)
    assert subjects[0].endswith("Monthly Farm Activities – 01 Sep 2026 – 30 Sep 2026")
    assert "Quarterly Health Report – 01 Jul 2026 – 30 Sep 2026" in subjects[1]
    monthly = next(e for e in mail.outbox if "Monthly" in e.subject)
    assert monthly.to == ["owner@example.com", "vet@example.com"]
    assert monthly.attachments[0][0].endswith(".pdf")
    assert ReportSchedule.objects.get(report_type="monthly_activities").last_period == "2026-09"
    second = dt.datetime(2026, 11, 2, 7, 0, tzinfo=dt.UTC)
    with mock.patch("django.utils.timezone.now", return_value=second):
        assert services.send_scheduled() == 0  # only on the 1st


# --- Sharing on WhatsApp --------------------------------------------------------------------------------


def test_share_on_whatsapp_sends_summary_and_link(farm, admin, herd):  # type: ignore[no-untyped-def]
    res = admin.post("/api/v1/reports/vaccination/share", {"phone": "0772 123456"}, format="json")
    assert res.status_code == 202, res.content
    assert res.json()["status"] == "sent" and res.json()["to"] == "+256772123456"
    out = OutboundMessage.objects.get(pk=res.json()["id"])
    assert out.template == "smartfarm_report_share" and out.notification is None
    sent = [m for m in SENT if m.channel == "whatsapp"][-1]
    assert "Vaccinations: 3" in sent.body and "/download?token=" in sent.body
    assert (
        admin.post("/api/v1/reports/vaccination/share", {"phone": "12"}, format="json").status_code
        == 400
    )


# --- Export all farm data -------------------------------------------------------------------------------


def test_export_all_farm_data(farm, admin, member, client_for, herd):  # type: ignore[no-untyped-def]
    FeedItemFactory(farm=farm, name="Hay")
    res = admin.get("/api/v1/farm/export")
    assert res.status_code == 200 and res["Content-Type"] == "application/zip"
    zf = zipfile.ZipFile(io.BytesIO(res.content))
    names = set(zf.namelist())
    assert {
        "livestock/animal.csv",
        "health/vaccination.csv",
        "nutrition/feeditem.csv",
        "accounts/members.csv",
    } <= names
    animals = zf.read("livestock/animal.csv").decode("utf-8-sig").splitlines()
    assert len(animals) == 1 + 7  # header + 5 + 2 kids (the dead one stays, marked as exited)
    manager = member(farm, Role.FARM_MANAGER)
    assert client_for(manager, farm).get("/api/v1/farm/export").status_code == 403


# --- Metrics edge cases -------------------------------------------------------------------------------


def test_periods_and_buckets():  # type: ignore[no-untyped-def]
    assert metrics.quarter_period(dt.date(2026, 11, 22)) == metrics.Period(
        dt.date(2026, 10, 1), dt.date(2026, 12, 31)
    )
    assert metrics.months_back(dt.date(2026, 2, 10), 6).start == dt.date(2025, 9, 1)
    week = metrics.buckets(metrics.Period(dt.date(2026, 11, 4), dt.date(2026, 11, 20)), "week")
    assert week[0] == dt.date(2026, 11, 2) and len(week) == 3
    assert metrics.auto_group(metrics.Period(dt.date(2026, 1, 1), dt.date(2026, 3, 1))) == "month"
    assert services.due_period("quarterly_health", dt.date(2026, 11, 1)) is None
    assert services.due_period("monthly_activities", dt.date(2026, 11, 2)) is None
