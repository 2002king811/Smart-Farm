"""Tenancy isolation across two farms, for every farm-scoped endpoint.

The endpoint list is discovered from the URL configuration, so each new viewset is covered
automatically. A new farm-owned model or endpoint without a factory makes this test fail.
"""

from typing import Any

import pytest
from django.apps import apps
from django.urls import URLPattern, URLResolver, get_resolver

from apps.accounts.models import Role
from apps.core.models import FarmOwnedModel
from apps.core.views import FarmContextMixin
from tests.factories import (
    FACTORY_FOR_ENDPOINT_MODEL,
    FACTORY_FOR_MODEL,
    FACTORY_FOR_ROUTE,
    OWNER_FIELD_FOR_ROUTE,
)

ALL_FACTORIES = {**FACTORY_FOR_MODEL, **FACTORY_FOR_ENDPOINT_MODEL}

pytestmark = pytest.mark.django_db

# Endpoints under /api/v1/ that are deliberately not farm-scoped (they act on the user).
NON_FARM_ENDPOINTS = {
    "me",
    "countries",
    "me/farms",
    "me/photo",
    "me/password",
    "auth/signup",
    "auth/login",
    "auth/refresh",
    "auth/logout",
    "auth/password/forgot",
    "auth/password/reset",
    "auth/verify-email",
    "auth/verify-email/resend",
    "auth/verify-phone/send",
    "auth/verify-phone",
    "invitations/lookup",
    "invitations/accept",
}


def _walk(patterns: list[Any], prefix: str = "") -> list[tuple[str, Any]]:
    found = []
    for p in patterns:
        if isinstance(p, URLResolver):
            found.extend(_walk(p.url_patterns, prefix + str(p.pattern)))
        elif isinstance(p, URLPattern):
            found.append((prefix + str(p.pattern), p.callback))
    return found


def _api_routes() -> list[tuple[str, Any]]:
    return [
        (route, cb)
        for route, cb in _walk(get_resolver().url_patterns)
        if route.startswith("api/v1/")
    ]


def _view_class(callback: Any) -> type | None:
    return getattr(callback, "cls", None) or getattr(callback, "view_class", None)


def _farm_viewsets() -> dict[str, type]:
    """{list route: viewset class} for each farm-scoped router-registered viewset."""
    result = {}
    for route, callback in _api_routes():
        cls = _view_class(callback)
        actions = getattr(callback, "actions", None)
        is_list = actions and actions.get("get") == "list" and "(?P<format>" not in route
        if cls and issubclass(cls, FarmContextMixin) and is_list:
            result[route.removeprefix("api/v1/").rstrip("$").removeprefix("^")] = cls
    return result


def _model_for(viewset: type) -> type:
    return viewset.model or viewset.queryset.model  # type: ignore[attr-defined]


def test_every_api_endpoint_is_farm_scoped_or_allowlisted() -> None:
    unscoped = set()
    for route, callback in _api_routes():
        cls = _view_class(callback)
        if cls is None or issubclass(cls, FarmContextMixin):
            continue
        unscoped.add(route.removeprefix("api/v1/"))
    assert (
        unscoped <= NON_FARM_ENDPOINTS
    ), f"Endpoints without farm scoping: {unscoped - NON_FARM_ENDPOINTS}"


def test_every_farm_owned_model_has_a_factory() -> None:
    models = [
        m for m in apps.get_models() if issubclass(m, FarmOwnedModel) and not m._meta.abstract
    ]
    missing = [m.__name__ for m in models if m not in FACTORY_FOR_MODEL]
    assert not missing, f"Add factories to tests/factories.py FACTORY_FOR_MODEL: {missing}"


VIEWSETS = _farm_viewsets()


def _own(route: str, user: Any, *rows: Any) -> None:
    """For "only my rows" endpoints, make the rows the user's own (on both farms)."""
    field = OWNER_FIELD_FOR_ROUTE.get(route)
    for row in rows if field else ():
        type(row)._base_manager.filter(pk=row.pk).update(**{field: user})


def test_discovers_farm_viewsets() -> None:
    assert "audit-logs" in VIEWSETS
    assert "test-goats" in VIEWSETS


@pytest.mark.parametrize("route", sorted(VIEWSETS))
def test_endpoint_never_returns_another_farms_data(route, farm_a, farm_b, member, client_for):  # type: ignore[no-untyped-def]
    viewset = VIEWSETS[route]
    model = _model_for(viewset)
    factory = FACTORY_FOR_ROUTE.get(route) or ALL_FACTORIES[model]
    mine = factory(farm=farm_a)
    theirs = factory(farm=farm_b)
    user = member(farm_a, Role.ADMINISTRATOR)
    _own(route, user, mine, theirs)
    client = client_for(user, farm_a)

    # List: only my farm's rows, and the other farm's row never appears in any page.
    ids: set[str] = set()
    url: str | None = f"/api/v1/{route}?page_size=200"
    while url:
        res = client.get(url)
        assert res.status_code == 200, res.content
        body = res.json()
        rows = body["results"] if isinstance(body, dict) else body  # unpaginated short lists
        ids |= {str(r["id"]) for r in rows}
        url = body.get("next") if isinstance(body, dict) else None
    assert str(mine.pk) in ids
    assert str(theirs.pk) not in ids
    assert all(model._base_manager.get(pk=i).farm_id == farm_a.pk for i in ids)

    # Detail of the other farm's row: 404, as if it does not exist.
    assert client.get(f"/api/v1/{route}/{theirs.pk}").status_code == 404
    assert client.get(f"/api/v1/{route}/{mine.pk}").status_code == 200

    # Writes to the other farm's row: 404 and nothing changes.
    allowed = set(viewset.http_method_names)
    if "patch" in allowed and hasattr(viewset, "partial_update"):
        assert client.patch(f"/api/v1/{route}/{theirs.pk}", {}, format="json").status_code == 404
    if "delete" in allowed and hasattr(viewset, "destroy"):
        assert client.delete(f"/api/v1/{route}/{theirs.pk}").status_code == 404
        assert model._base_manager.get(pk=theirs.pk).farm_id == farm_b.pk
        if hasattr(theirs, "deleted_at"):
            assert model._base_manager.get(pk=theirs.pk).deleted_at is None

    # Asking for the other farm (not a member): 404, never 403, so farm IDs cannot be probed.
    other = client_for(user, farm_b)
    assert other.get(f"/api/v1/{route}").status_code == 404
    assert other.get(f"/api/v1/{route}/{theirs.pk}").status_code == 404


@pytest.mark.parametrize("route", sorted(VIEWSETS))
def test_member_of_both_farms_sees_only_the_selected_one(route, farm_a, farm_b, member, client_for):  # type: ignore[no-untyped-def]
    model = _model_for(VIEWSETS[route])
    factory = FACTORY_FOR_ROUTE.get(route) or ALL_FACTORIES[model]
    a, b = factory(farm=farm_a), factory(farm=farm_b)
    user = member(farm_a, Role.ADMINISTRATOR)
    from apps.accounts.models import FarmMembership

    FarmMembership.objects.create(user=user, farm=farm_b, role=Role.ADMINISTRATOR)
    _own(route, user, a, b)

    def ids(farm):  # type: ignore[no-untyped-def]
        body = client_for(user, farm).get(f"/api/v1/{route}?page_size=200").json()
        return {str(r["id"]) for r in (body["results"] if isinstance(body, dict) else body)}

    ids_a, ids_b = ids(farm_a), ids(farm_b)
    assert str(a.pk) in ids_a and str(b.pk) not in ids_a
    assert str(b.pk) in ids_b and str(a.pk) not in ids_b
