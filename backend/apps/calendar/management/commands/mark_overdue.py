from datetime import date
from typing import Any
from unittest import mock

from django.core.management.base import BaseCommand

from apps.accounts.models import Farm, FarmStatus
from apps.calendar import services


class Command(BaseCommand):
    help = (
        "Mark past-due activities as Overdue now (the scheduled job does this at 00:05 farm time)."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--farm", help="Farm slug (default: all active farms)")
        parser.add_argument("--as-of", help="Pretend today is this date (YYYY-MM-DD), for testing")

    def handle(self, *args: Any, farm: str | None, as_of: str | None, **options: Any) -> None:
        farms = Farm.objects.filter(status=FarmStatus.ACTIVE)
        if farm:
            farms = farms.filter(slug=farm)
        patch = (
            mock.patch.object(services, "farm_today", lambda f: date.fromisoformat(as_of))
            if as_of
            else None
        )
        if patch:
            patch.start()
        try:
            total = sum(services.mark_overdue(f) for f in farms)
        finally:
            if patch:
                patch.stop()
        self.stdout.write(f"Marked {total} activities as overdue.")
