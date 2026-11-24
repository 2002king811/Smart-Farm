"""Runs the scheduled jobs in a simple loop, for computers without Redis/Celery beat (the
Windows local mode). Staging and production use Celery beat instead.

    python manage.py run_jobs          # every minute until stopped
    python manage.py run_jobs --once   # one pass (handy in tests and scripts)
"""

from __future__ import annotations

import logging
import time
from typing import Any

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.calendar.tasks import extend_all_series, mark_overdue_all
from apps.notifications.schedules import run_schedules
from apps.notifications.services import purge_old, release_due
from apps.reports.services import send_scheduled

logger = logging.getLogger("smartfarm.jobs")


class Command(BaseCommand):
    help = "Run reminders, overdue checks and queued messages every minute (no Celery needed)."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--once", action="store_true", help="Run one pass and exit")

    def handle(self, *args: Any, **options: Any) -> None:
        last_hour = last_day = None
        while True:
            now = timezone.now()
            try:
                if now.strftime("%Y%m%d%H") != last_hour:
                    mark_overdue_all()
                    send_scheduled()
                    last_hour = now.strftime("%Y%m%d%H")
                if now.date() != last_day:
                    extend_all_series()
                    purge_old()
                    last_day = now.date()
                sent = run_schedules()
                released = release_due()
                if sent or released:
                    self.stdout.write(
                        f"{now:%H:%M} reminders: {sent}, queued messages sent: {released}"
                    )
            except Exception:
                logger.exception("Scheduled jobs failed")
            if options["once"]:
                return
            time.sleep(60)
