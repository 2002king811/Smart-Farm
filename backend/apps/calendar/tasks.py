from celery import shared_task

from apps.accounts.models import Farm, FarmStatus
from apps.core.context import farm_context

from . import services
from .models import Activity


@shared_task(name="calendar.mark_overdue")
def mark_overdue_all() -> int:
    """Hourly at :05. Each farm's past-due activities turn Overdue once its local day ends, so a
    farm in Africa/Nairobi is processed at 00:05 Nairobi time."""
    return sum(
        services.mark_overdue(farm) for farm in Farm.objects.filter(status=FarmStatus.ACTIVE)
    )


@shared_task(name="calendar.extend_series")
def extend_all_series() -> int:
    """Daily: keep every repeating series generated 12 months ahead."""
    total = 0
    for head in (
        Activity.unscoped.filter(deleted_at__isnull=True)
        .exclude(recurrence_rule="")
        .select_related("farm")
    ):
        with farm_context(head.farm_id):
            total += services.extend_series(head)
    return total
