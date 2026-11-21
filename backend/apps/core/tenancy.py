"""Resolves the active farm for an API request and checks the user belongs to it."""

from __future__ import annotations

import uuid
from typing import Any

from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.request import Request

FARM_HEADER = "HTTP_X_FARM_ID"
FARM_CLAIM = "farm_id"


def requested_farm_id(request: Request) -> str | None:
    header = request.META.get(FARM_HEADER)
    if header:
        return header.strip()
    token = getattr(request, "auth", None)
    if token is not None and hasattr(token, "get"):
        claim = token.get(FARM_CLAIM)
        return str(claim) if claim else None
    return None


def resolve_membership(request: Request) -> Any:
    """Return the user's active membership for the requested farm.

    Anything other than an active membership of an existing farm is a 404, so a farm ID
    cannot be probed. A member of a suspended farm gets 403 with a reason.
    """
    from apps.accounts.models import FarmMembership, FarmStatus, MembershipStatus

    raw = requested_farm_id(request)
    if not raw:
        raise NotFound("Select a farm (send the X-Farm-ID header).")
    try:
        farm_id = uuid.UUID(raw)
    except ValueError as exc:
        raise NotFound() from exc

    membership = (
        FarmMembership.objects.select_related("farm")  # type: ignore[misc]
        .filter(user_id=request.user.pk, farm_id=farm_id, status=MembershipStatus.ACTIVE)
        .first()
    )
    if membership is None:
        raise NotFound()
    if membership.farm.status != FarmStatus.ACTIVE:
        raise PermissionDenied("This farm is suspended. Contact Smart Farm support.")
    return membership
