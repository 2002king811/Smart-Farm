"""Building, exporting, storing, scheduling and sharing reports."""

from __future__ import annotations

import csv
import datetime as dt
import io
import logging
import zipfile
from typing import Any

from celery import shared_task
from django.apps import apps
from django.conf import settings
from django.core import signing
from django.core.files.base import ContentFile
from django.core.mail import EmailMessage
from django.urls import reverse
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.accounts.models import Farm, FarmStatus
from apps.core.context import farm_context
from apps.core.models import FarmOwnedModel
from apps.core.utils import after_commit

from . import exports
from . import metrics as m
from .builders import REPORTS, ReportData, default_period
from .metrics import Period
from .models import ReportRun, ReportSchedule, RunStatus, ScheduledType

logger = logging.getLogger("smartfarm.reports")
LARGE_ROWS = 2000
LINK_HOURS = 24
MAX_DAYS = 3 * 366
_signer = signing.TimestampSigner(salt="report-download")


# --- Parameters -----------------------------------------------------------------------------------


def parse_date(value: str | None, field: str) -> dt.date | None:
    if not value:
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        raise ValidationError({field: ["Use a date like 2026-11-30."]}) from None


def resolve(
    report_type: str, params: dict[str, str], today: dt.date | None = None
) -> tuple[type, Period, str]:
    cls = REPORTS.get(report_type)
    if cls is None:
        raise ValidationError({"type": ["Unknown report."]})
    today = today or timezone.localdate()
    start, end = parse_date(params.get("from"), "from"), parse_date(params.get("to"), "to")
    if start is None or end is None:
        default = default_period(cls.default_period, today)
        start, end = start or default.start, end or default.end
    if end < start:
        raise ValidationError({"to": ["The end date must be on or after the start date."]})
    if (end - start).days > MAX_DAYS:
        raise ValidationError({"to": ["Choose a period of 3 years or less."]})
    period = Period(start, end)
    group = params.get("group") or m.auto_group(period)
    if group not in m.TRUNC:
        raise ValidationError({"group": ["Use day, week or month."]})
    return cls, period, group


def build(farm: Any, report_type: str, params: dict[str, str]) -> ReportData:
    cls, period, group = resolve(report_type, params)
    return cls(farm, period, group, params).build()


# --- Runs and signed links --------------------------------------------------------------------------


def download_url(run: ReportRun) -> str:
    token = _signer.sign(str(run.pk))
    path = reverse("report-run-download", kwargs={"pk": run.pk})
    return f"{settings.FRONTEND_URL.rstrip('/')}{path}?token={token}"


def check_token(run_id: str, token: str) -> bool:
    try:
        return _signer.unsign(token, max_age=dt.timedelta(hours=LINK_HOURS)) == str(run_id)
    except signing.BadSignature:
        return False


def store(run: ReportRun, data: ReportData, user: Any) -> None:
    content, _ctype, name = exports.render(data, run.format, run.farm, user)
    run.file.save(f"{run.farm_id}/{run.pk}/{name}", ContentFile(content), save=False)
    run.row_count = data.row_count
    run.status = RunStatus.DONE
    run.finished_at = timezone.now()
    run.save()


def new_run(
    farm: Any,
    user: Any,
    report_type: str,
    params: dict[str, str],
    fmt: str,
    purpose: str = "download",
) -> ReportRun:
    _cls, period, group = resolve(report_type, params)
    filters = {
        k: v
        for k, v in params.items()
        if k not in ("from", "to", "group", "format", "phone", "to_phone")
    }
    return ReportRun.objects.create(
        farm=farm,
        report_type=report_type,
        filters=filters,
        date_from=period.start,
        date_to=period.end,
        group=group,
        format=fmt,
        requested_by=user,
        purpose=purpose,
    )


def run_params(run: ReportRun) -> dict[str, str]:
    return {
        **run.filters,
        "from": run.date_from.isoformat(),
        "to": run.date_to.isoformat(),
        "group": run.group,
    }


@shared_task(name="reports.generate")
def generate(run_id: str) -> str:
    """Builds a large export in the background, then tells the requester it is ready."""
    from apps.notifications.models import EventType
    from apps.notifications.services import notify

    run = ReportRun.unscoped.select_related("farm", "requested_by").get(pk=run_id)
    with farm_context(run.farm_id):
        run.status = RunStatus.RUNNING
        run.save(update_fields=["status"])
        try:
            data = build(run.farm, run.report_type, run_params(run))
            store(run, data, run.requested_by)
        except Exception as exc:
            logger.exception("Report run %s failed", run.pk)
            run.status, run.error, run.finished_at = (
                RunStatus.FAILED,
                str(exc)[:300],
                timezone.now(),
            )
            run.save(update_fields=["status", "error", "finished_at"])
            return run.status
        if run.requested_by:
            notify(
                run.requested_by,
                run.farm,
                EventType.REPORT_READY,
                title=f"Report ready: {data.title}",
                message=f"{data.title} ({data.period.label()}, {run.get_format_display()}) is ready. "
                f"Download it within {LINK_HOURS} hours: {download_url(run)}",
                link=f"/reports?run={run.pk}",
                urgent=True,  # never held by quiet hours (it only goes in-app and by email)
            )
    return run.status


def start_large(run: ReportRun) -> None:
    after_commit(lambda: generate.delay(str(run.pk)))


# --- Scheduled reports ------------------------------------------------------------------------------


def due_period(kind: str, today: dt.date) -> tuple[Period, str] | None:
    """On the 1st: the month or quarter that just ended, with its label."""
    if today.day != 1:
        return None
    last = today - dt.timedelta(days=1)
    if kind == ScheduledType.MONTHLY_ACTIVITIES:
        return m.month_period(last), f"{last:%Y-%m}"
    if today.month in (1, 4, 7, 10):
        q = m.quarter_period(last)
        return q, f"{last.year}-Q{(last.month - 1) // 3 + 1}"
    return None


def send_schedule(schedule: ReportSchedule, period: Period, label: str) -> None:
    farm = schedule.farm
    data = REPORTS[schedule.report_type](
        farm, period, "month" if period.days > 31 else "week", {}
    ).build()
    content, ctype, name = exports.render(data, schedule.format, farm, schedule.created_by)
    email = EmailMessage(
        subject=f"{farm.name}: {data.title} – {period.label()}",
        body=(
            f"Hello,\n\nAttached is the {data.title} for {farm.name}, {period.label()}.\n\n"
            + "\n".join(f"{c.label}: {exports.card_text(c)}" for c in data.summary)
            + "\n\nSent automatically by Smart Farm."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=schedule.recipients,
    )
    email.attach(name, content, ctype.split(";")[0])
    email.send()
    schedule.last_period, schedule.last_sent_at = label, timezone.now()
    schedule.save(update_fields=["last_period", "last_sent_at", "updated_at"])


@shared_task(name="reports.send_scheduled")
def send_scheduled() -> int:
    """Hourly: on the 1st, after 06:00 farm time, email each due schedule once."""
    from apps.notifications.services import farm_zone

    sent = 0
    for farm in Farm.objects.filter(status=FarmStatus.ACTIVE):
        local = timezone.now().astimezone(farm_zone(farm))
        if local.hour < 6:
            continue
        with farm_context(farm.pk):
            for schedule in ReportSchedule.objects.filter(enabled=True).select_related(
                "farm", "created_by"
            ):
                due = due_period(schedule.report_type, local.date())
                if due is None or schedule.last_period == due[1] or not schedule.recipients:
                    continue
                try:
                    send_schedule(schedule, *due)
                    sent += 1
                except Exception:
                    logger.exception("Scheduled report %s failed", schedule.pk)
    return sent


# --- WhatsApp sharing -----------------------------------------------------------------------------


def share(farm: Any, user: Any, report_type: str, params: dict[str, str], phone: str) -> Any:
    """Saves the PDF and sends a short summary with a 24-hour link by WhatsApp template."""
    from apps.notifications.models import OutboundMessage
    from apps.notifications.services import _deliver_later

    run = new_run(farm, user, report_type, params, "pdf", purpose="share")
    data = build(farm, report_type, run_params(run))
    store(run, data, user)
    highlights = "; ".join(f"{c.label}: {exports.card_text(c)}" for c in data.summary[:4])
    link = download_url(run)
    out = OutboundMessage.objects.create(
        farm=farm,
        notification=None,
        channel="whatsapp",
        to=phone,
        template="smartfarm_report_share",
        payload={
            "title": f"{farm.name}: {data.title} ({data.period.label()})",
            "message": f"{highlights}. Download the PDF (valid {LINK_HOURS} h): {link}",
            "link": "",
            "farm_name": farm.name,
        },
        language="en",
    )
    after_commit(_deliver_later(str(out.pk)))
    return out


# --- Export all farm data ---------------------------------------------------------------------------

SKIP_FIELDS = {"farm", "password"}


def farm_data_zip(farm: Any) -> bytes:
    """A ZIP with one CSV per table of the farm's data (backup and portability)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for model in apps.get_models():
            if not issubclass(model, FarmOwnedModel) or model._meta.app_label in (
                "tests",
                "testapp",
            ):
                continue
            if model._meta.app_label == "notifications" and model.__name__ in ("OutboundMessage",):
                continue
            fields = [f for f in model._meta.concrete_fields if f.name not in SKIP_FIELDS]
            out = io.StringIO()
            w = csv.writer(out)
            w.writerow([f.attname for f in fields])
            qs = model._base_manager.filter(farm=farm)
            if hasattr(model, "deleted_at"):
                qs = qs.filter(deleted_at__isnull=True)  # type: ignore[misc]
            for row in qs.values_list(*[f.attname for f in fields]).iterator():
                w.writerow(
                    [
                        "" if v is None else (v.isoformat() if hasattr(v, "isoformat") else v)
                        for v in row
                    ]
                )
            zf.writestr(
                f"{model._meta.app_label}/{model._meta.model_name}.csv", "﻿" + out.getvalue()
            )
        members = farm.memberships.select_related("user")
        out = io.StringIO()
        w = csv.writer(out)
        w.writerow(
            ["user_id", "name", "email", "phone", "role", "status", "job_title", "joined_at"]
        )
        for ms in members:
            w.writerow(
                [
                    ms.user_id,
                    ms.user.full_name,
                    ms.user.email,
                    ms.user.phone,
                    ms.role,
                    ms.status,
                    ms.job_title,
                    ms.joined_at.isoformat(),
                ]
            )
        zf.writestr("accounts/members.csv", "﻿" + out.getvalue())
        zf.writestr(
            "README.txt",
            f"Smart Farm data export for {farm.name}, {timezone.localtime():%d %b %Y %H:%M}.\nOne CSV per table, UTF-8.\n",
        )
    return buf.getvalue()
