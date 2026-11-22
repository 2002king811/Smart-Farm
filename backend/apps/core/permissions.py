"""Role-based access, per farm. The matrix lives in permissions_matrix.json."""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

from rest_framework.permissions import BasePermission
from rest_framework.request import Request

MATRIX_PATH = Path(__file__).with_name("permissions_matrix.json")

# Standard viewset actions map onto these permission actions.
DEFAULT_ACTION_MAP = {
    "list": "view",
    "retrieve": "view",
    "metadata": "view",
    "create": "create",
    "update": "update",
    "partial_update": "update",
    "destroy": "delete",
}


@cache
def load_matrix() -> dict[str, Any]:
    return json.loads(MATRIX_PATH.read_text())


def module_rule(role: str, module: str) -> dict[str, Any] | None:
    return load_matrix()["roles"].get(role, {}).get(module)


def role_can(role: str, module: str, action: str) -> bool:
    rule = module_rule(role, module)
    if not rule:
        return False
    actions = rule["actions"]
    return actions == "*" or action in actions


def role_scope(role: str, module: str) -> str | None:
    rule = module_rule(role, module)
    return rule["scope"] if rule else None


class FarmModulePermission(BasePermission):
    """Allows the request when the user's role on the active farm grants the module action.

    The view declares ``permission_module`` and may override action names with
    ``action_permissions = {"create": "record_weight"}``. Custom @action names are used as
    the permission action unless overridden.
    """

    message = "Your role on this farm does not allow this action."

    def has_permission(self, request: Request, view: Any) -> bool:
        membership = getattr(request, "membership", None)
        if membership is None:
            return False
        module = getattr(view, "permission_module", None)
        if module is None:
            raise AssertionError(f"{type(view).__name__} must declare permission_module")
        action = required_action(request, view)
        return role_can(membership.role, module, action)


def required_action(request: Request, view: Any) -> str:
    view_action = getattr(view, "action", None) or _method_action(request.method or "GET")
    overrides: dict[str, Any] = getattr(view, "action_permissions", {})
    if view_action in overrides:
        rule = overrides[view_action]
        # A dict maps HTTP methods to actions, e.g. {"GET": "view", "POST": "record_weight"}.
        if isinstance(rule, dict):
            return rule.get((request.method or "GET").upper(), "view")
        return rule
    return DEFAULT_ACTION_MAP.get(view_action, view_action)


def _method_action(method: str) -> str:
    return {
        "GET": "view",
        "HEAD": "view",
        "OPTIONS": "view",
        "POST": "create",
        "PUT": "update",
        "PATCH": "update",
        "DELETE": "delete",
    }[method.upper()]
