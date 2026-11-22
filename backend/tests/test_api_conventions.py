"""Error shape, pagination, health checks and the user endpoints."""

from unittest import mock

import pytest
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from rest_framework import serializers

from apps.core.exceptions import exception_handler
from tests.factories import GoatFactory

pytestmark = pytest.mark.django_db


def test_validation_errors_use_one_shape(farm_a, admin_a, client_for):  # type: ignore[no-untyped-def]
    res = client_for(admin_a, farm_a).post("/api/v1/test-goats", {"status": "flying"})
    assert res.status_code == 400
    errors = res.json()["errors"]
    assert errors["name"] == ["This field is required."]
    assert errors["status"] == ['"flying" is not a valid choice.']


def test_not_found_shape(farm_a, admin_a, client_for):  # type: ignore[no-untyped-def]
    res = client_for(admin_a, farm_a).get("/api/v1/test-goats/00000000-0000-0000-0000-000000000000")
    assert res.status_code == 404
    assert (
        res.json() == {"errors": {"detail": ["No Goat matches the given query."]}}
        or res.json()["errors"]["detail"]
    )


@pytest.mark.parametrize(
    ("exc", "status", "key"),
    [
        (DjangoValidationError({"name": ["Bad name"]}), 400, "name"),
        (DjangoValidationError("Whole thing is wrong"), 400, "detail"),
        (Http404(), 404, "detail"),
        (DjangoPermissionDenied(), 403, "detail"),
        (serializers.ValidationError({"items": [{"qty": ["Too many"]}]}), 400, "items"),
        (serializers.ValidationError(["Top level problem"]), 400, "detail"),
    ],
)
def test_exception_handler_normalises(exc, status, key):  # type: ignore[no-untyped-def]
    response = exception_handler(exc, {})
    assert response is not None
    assert response.status_code == status
    assert key in response.data["errors"]


def test_nested_errors_keep_structure():  # type: ignore[no-untyped-def]
    exc = serializers.ValidationError({"items": [{"qty": ["Too many"]}], "meta": {"x": "bad"}})
    data = exception_handler(exc, {}).data  # type: ignore[union-attr]
    assert data["errors"]["items"] == [{"qty": ["Too many"]}]
    assert data["errors"]["meta"] == {"x": ["bad"]}


def test_unknown_exception_is_not_handled():  # type: ignore[no-untyped-def]
    assert exception_handler(ValueError("boom"), {}) is None


def test_cursor_pagination_with_count_and_ordering(farm_a, admin_a, client_for):  # type: ignore[no-untyped-def]
    for name in ["Cleo", "Asha", "Baraka"]:
        GoatFactory(farm=farm_a, name=name)
    client = client_for(admin_a, farm_a)
    page1 = client.get("/api/v1/test-goats?page_size=2&ordering=name").json()
    assert page1["count"] == 3
    assert [g["name"] for g in page1["results"]] == ["Asha", "Baraka"]
    page2 = client.get(page1["next"]).json()
    assert [g["name"] for g in page2["results"]] == ["Cleo"]
    assert page2["next"] is None
    assert client.get("/api/v1/test-goats?search=bar").json()["count"] == 1
    assert client.get("/api/v1/test-goats?status=sick").json()["count"] == 0


def test_health_endpoints(client):  # type: ignore[no-untyped-def]
    assert client.get("/api/health/live").json() == {"status": "ok"}
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["checks"] == {"database": "ok", "cache": "ok"}
    assert res["X-Request-ID"]


def test_health_reports_degraded(client):  # type: ignore[no-untyped-def]
    with mock.patch("apps.core.health.cache.set", side_effect=ConnectionError):
        res = client.get("/api/health")
    assert res.status_code == 503
    assert res.json()["status"] == "degraded"


def test_request_id_is_echoed(client):  # type: ignore[no-untyped-def]
    assert client.get("/api/health/live", HTTP_X_REQUEST_ID="abc123")["X-Request-ID"] == "abc123"


def test_me_and_my_farms(farm_a, farm_b, member, client_for):  # type: ignore[no-untyped-def]
    from apps.accounts.models import FarmMembership, FarmStatus, Role

    user = member(farm_a, Role.FARM_MANAGER)
    FarmMembership.objects.create(user=user, farm=farm_b, role=Role.LIVESTOCK_ATTENDANT)
    client = client_for(user)
    me = client.get("/api/v1/me").json()
    assert me["id"] == str(user.pk) and me["full_name"] == user.get_full_name()
    farms = client.get("/api/v1/me/farms").json()
    assert [f["farm"]["name"] for f in farms] == ["Other Farm", "YPA FARM"]
    assert farms[1]["role_label"] == "Farm Manager"
    assert farms[1]["permissions"]["reports"]["actions"] == "*"
    assert "users" not in farms[1]["permissions"]
    farm_b.status = FarmStatus.SUSPENDED
    farm_b.save()
    assert len(client.get("/api/v1/me/farms").json()) == 1
    assert client_for(None).get("/api/v1/me").status_code == 401


def test_openapi_schema_builds(client):  # type: ignore[no-untyped-def]
    res = client.get("/api/schema/?format=json")
    assert res.status_code == 200
    assert "/api/v1/me/farms" in res.json()["paths"]


def test_logging_filter_adds_context(farm_a):  # type: ignore[no-untyped-def]
    import logging

    from apps.core.context import farm_context
    from apps.core.logging import RequestContextFilter

    record = logging.LogRecord("x", logging.INFO, __file__, 1, "msg", None, None)
    with farm_context(farm_a.pk):
        RequestContextFilter().filter(record)
    assert record.farm_id == str(farm_a.pk)  # type: ignore[attr-defined]
    assert record.request_id == "-"  # type: ignore[attr-defined]


def test_ping_task():  # type: ignore[no-untyped-def]
    from apps.core.tasks import ping

    assert ping.delay().get() == "pong"


def test_websocket_health():  # type: ignore[no-untyped-def]
    from asgiref.sync import async_to_sync
    from channels.testing.websocket import WebsocketCommunicator

    from config.asgi import application

    async def run() -> dict:
        comm = WebsocketCommunicator(
            application, "/ws/health", headers=[(b"origin", b"http://localhost")]
        )
        connected, _ = await comm.connect()
        assert connected
        message = await comm.receive_json_from()
        await comm.disconnect()
        return message

    assert async_to_sync(run)() == {"status": "ok"}


def test_dev_outbox_only_in_debug(client, settings):  # type: ignore[no-untyped-def]
    from importlib import reload

    from django.urls import clear_url_caches

    import config.urls
    import tests.urls
    from apps.notifications import messaging

    assert client.get("/api/dev/outbox").status_code == 404
    settings.DEBUG = True
    try:
        reload(config.urls)
        reload(tests.urls)
        clear_url_caches()
        messaging.SENT.append(messaging.SentMessage("sms", "+254700000000", "123456 is your code"))
        res = client.get("/api/dev/outbox")
        assert res.json()["messages"][0]["body"] == "123456 is your code"
    finally:
        settings.DEBUG = False
        reload(config.urls)
        reload(tests.urls)
        clear_url_caches()
