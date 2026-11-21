"""Per-request (or per-task) context: the active farm, the acting user and the client IP.

Values live in contextvars so they are isolated between concurrent requests, threads and
async tasks. The tenancy layer reads ``current_farm_id`` to scope every farm-owned query.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(frozen=True)
class RequestContext:
    farm_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None
    ip: str | None = None
    request_id: str | None = None


_EMPTY = RequestContext()  # frozen, so sharing it as the default is safe
_ctx: ContextVar[RequestContext] = ContextVar("smartfarm_request_context", default=_EMPTY)


def get_context() -> RequestContext:
    return _ctx.get()


def current_farm_id() -> uuid.UUID | None:
    return _ctx.get().farm_id


def set_context(**changes: object) -> object:
    """Update fields of the current context. Returns a token for ``reset_context``."""
    current = _ctx.get()
    values = {**current.__dict__, **changes}
    return _ctx.set(RequestContext(**values))  # type: ignore[arg-type]


def reset_context(token: object) -> None:
    _ctx.reset(token)  # type: ignore[arg-type]


@contextmanager
def farm_context(
    farm_id: uuid.UUID | str | None, user_id: uuid.UUID | None = None
) -> Iterator[None]:
    """Run a block (a Celery task, a management command) as if inside a request for one farm."""
    fid = uuid.UUID(str(farm_id)) if farm_id is not None else None
    token = set_context(farm_id=fid, user_id=user_id)
    try:
        yield
    finally:
        reset_context(token)
