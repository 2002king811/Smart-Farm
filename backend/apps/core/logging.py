import logging

from .context import get_context


class RequestContextFilter(logging.Filter):
    """Adds request_id, farm_id and user_id to every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        ctx = get_context()
        record.request_id = ctx.request_id or "-"
        record.farm_id = str(ctx.farm_id) if ctx.farm_id else "-"
        record.user_id = str(ctx.user_id) if ctx.user_id else "-"
        return True
