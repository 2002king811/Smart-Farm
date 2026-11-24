"""Phase 8 backend: offline sync, idempotency, security headers, personal data rights,
message log retention and the platform staff console with logged support access."""

import datetime as dt
import uuid

import pytest
from django.utils import timezone

from apps.accounts.models import FarmMembership, Role, SupportAccessGrant, User
from apps.audit.models import AuditLog
from apps.calendar.models import ActivityStatus, ActivityStatusHistory
from apps.notifications import services as notify_services
from apps.notifications.models import Notification, OutboundMessage
from tests.factories import ActivityFactory, AnimalFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin(farm_a, admin_a, client_for):  # type: ignore[no-untyped-def]
    return client_for(admin_a, farm_a)


# --- Offline sync -------------------------------------------------------------------------------------


def test_offline_complete_is_idempotent_and_last_write_wins(farm_a, admin, member, client_for):  # type: ignore[no-untyped-def]
    worker = member(farm_a, Role.LIVESTOCK_ATTENDANT)
    act = ActivityFactory(farm=farm_a, assigned_to=worker, status=ActivityStatus.PENDING)
    me = client_for(worker, farm_a)
    when = (timezone.now() - dt.timedelta(hours=2)).isoformat()
    res = me.post(f"/api/v1/activities/{act.pk}/complete", {"offline_at": when}, format="json")
    assert res.status_code == 200 and res.json()["status"] == "completed"
    note = ActivityStatusHistory.unscoped.filter(activity=act).last().note
    assert note.startswith("Done offline at") and "last write wins" not in note
    # The same queued change again: nothing new.
    assert (
        me.post(
            f"/api/v1/activities/{act.pk}/complete", {"offline_at": when}, format="json"
        ).status_code
        == 200
    )
    assert ActivityStatusHistory.unscoped.filter(activity=act).count() == 1

    # A manager cancelled it while the phone was offline: the later sync wins, and says so.
    other = ActivityFactory(farm=farm_a, assigned_to=worker, status=ActivityStatus.CANCELLED)
    res = me.post(f"/api/v1/activities/{other.pk}/complete", {"offline_at": when}, format="json")
    assert res.json()["status"] == "completed"
    assert "last write wins" in ActivityStatusHistory.unscoped.filter(activity=other).last().note
    # Online, the normal rule still applies.
    third = ActivityFactory(farm=farm_a, status=ActivityStatus.CANCELLED)
    assert (
        admin.post(f"/api/v1/activities/{third.pk}/complete", {}, format="json").status_code == 400
    )


def test_idempotency_key_replays_instead_of_saving_twice(farm_a, admin):  # type: ignore[no-untyped-def]
    animal = AnimalFactory(farm=farm_a)
    key = str(uuid.uuid4())
    body = {"date": str(timezone.localdate()), "weight_kg": "31.5"}
    url = f"/api/v1/animals/{animal.pk}/weights"
    first = admin.post(url, body, format="json", HTTP_IDEMPOTENCY_KEY=key)
    second = admin.post(url, body, format="json", HTTP_IDEMPOTENCY_KEY=key)
    assert first.status_code == second.status_code == 201
    assert second["Idempotent-Replay"] == "true" and first.json()["id"] == second.json()["id"]
    assert animal.weights.count() == 1
    admin.post(url, body, format="json", HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
    assert animal.weights.count() == 2


def test_security_headers(client):  # type: ignore[no-untyped-def]
    res = client.get("/api/v1/countries")
    assert "default-src 'self'" in res["Content-Security-Policy"]
    assert "frame-ancestors 'none'" in res["Content-Security-Policy"]


def test_test_message_is_rate_limited(farm_a, admin):  # type: ignore[no-untyped-def]
    codes = [
        admin.post("/api/v1/notifications/test", {"channel": "in_app"}, format="json").status_code
        for _ in range(7)
    ]
    assert codes[:5] == [201] * 5 and codes[-1] == 429


# --- Personal data rights -------------------------------------------------------------------------------


def test_download_my_data(farm_a, admin_a, admin):  # type: ignore[no-untyped-def]
    notify_services.send_test(admin_a, farm_a, "in_app")
    res = admin.get("/api/v1/me/data")
    assert res.status_code == 200 and "attachment" in res["Content-Disposition"]
    import json

    data = json.loads(res.content)
    assert data["profile"]["email"] == admin_a.email
    assert data["farms"][0]["farm"] == farm_a.name
    assert data["notifications"][0]["title"] == "Test message from Smart Farm"


def test_delete_my_account(farm_a, admin_a, member, client_for):  # type: ignore[no-untyped-def]
    worker = member(farm_a, Role.LIVESTOCK_ATTENDANT)
    worker.phone = "+256772111222"
    worker.save()
    notify_services.send_test(worker, farm_a, "in_app")
    me = client_for(worker, farm_a)
    assert me.post("/api/v1/me/delete", {"password": "wrong"}, format="json").status_code == 400
    assert (
        me.post("/api/v1/me/delete", {"password": "Str0ng-pass!"}, format="json").status_code == 204
    )
    worker.refresh_from_db()
    assert (
        not worker.is_active
        and worker.email == ""
        and worker.phone == ""
        and worker.first_name == "Deleted"
    )
    assert not Notification.unscoped.filter(recipient=worker).exists()
    assert FarmMembership.objects.get(user=worker).status == "inactive"

    # The only administrator cannot delete themselves.
    res = client_for(admin_a, farm_a).post(
        "/api/v1/me/delete", {"password": "Str0ng-pass!"}, format="json"
    )
    assert res.status_code == 400 and "only administrator" in res.json()["errors"]["detail"][0]


def test_message_logs_kept_12_months(farm_a, admin_a):  # type: ignore[no-untyped-def]
    old = notify_services.send_test(admin_a, farm_a, "sms")
    new = notify_services.send_test(admin_a, farm_a, "in_app")
    Notification.unscoped.filter(pk=old.pk).update(
        created_at=timezone.now() - dt.timedelta(days=400)
    )
    OutboundMessage.unscoped.filter(notification=old).update(
        created_at=timezone.now() - dt.timedelta(days=400)
    )
    notify_services.purge_old()
    assert list(Notification.unscoped.values_list("pk", flat=True)) == [new.pk]


# --- Platform staff console ------------------------------------------------------------------------------


def test_staff_need_a_logged_grant_to_see_farm_records(farm_a, client):  # type: ignore[no-untyped-def]
    staff = User.objects.create_superuser("platform", "ops@example.com", "Str0ng-pass!")
    AnimalFactory(farm=farm_a, name="Neema")
    client.force_login(staff)
    url = f"/admin/accounts/farm/{farm_a.pk}/records/"
    assert client.get(url).status_code == 403
    assert client.get("/admin/accounts/farm/").status_code == 200  # the farm list with usage

    res = client.post(
        "/admin/accounts/supportaccessgrant/add/",
        {"farm": str(farm_a.pk), "reason": "Ticket 42: missing animal", "hours": 2},
    )
    assert res.status_code == 302, res.content[:500]
    grant = SupportAccessGrant.objects.get()
    assert grant.staff == staff and grant.active
    page = client.get(url)
    assert page.status_code == 200 and b"Neema" in page.content
    logs = AuditLog.unscoped.filter(farm=farm_a, object_id=str(grant.pk)).values_list(
        "action", flat=True
    )
    assert sorted(logs) == ["access", "create"]

    SupportAccessGrant.objects.update(expires_at=timezone.now() - dt.timedelta(minutes=1))
    assert client.get(url).status_code == 403
