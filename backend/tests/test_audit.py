import pytest

from apps.audit.models import AuditAction, AuditLog
from apps.core.context import farm_context, reset_context, set_context
from tests.factories import GoatFactory

pytestmark = pytest.mark.django_db


def _entries(obj):  # type: ignore[no-untyped-def]
    return list(AuditLog.unscoped.filter(object_id=str(obj.pk)).order_by("at", "id"))


def test_create_update_status_and_delete_are_logged(farm_a, admin_a, client_for):  # type: ignore[no-untyped-def]
    client = client_for(admin_a, farm_a)
    goat_id = client.post("/api/v1/test-goats", {"name": "Simba"}, REMOTE_ADDR="10.0.0.9").json()[
        "id"
    ]
    client.patch(f"/api/v1/test-goats/{goat_id}", {"name": "Simba II"})
    client.patch(f"/api/v1/test-goats/{goat_id}", {"status": "sick"})
    client.patch(f"/api/v1/test-goats/{goat_id}", {"status": "sick"})  # no change, no entry
    client.delete(f"/api/v1/test-goats/{goat_id}")

    entries = list(AuditLog.unscoped.filter(object_id=goat_id).order_by("at", "id"))
    assert [e.action for e in entries] == [
        AuditAction.CREATE,
        AuditAction.UPDATE,
        AuditAction.STATUS_CHANGE,
        AuditAction.DELETE,
    ]
    create, update, status, delete = entries
    assert create.after["name"] == "Simba" and create.before is None
    assert create.user == admin_a and create.farm_id == farm_a.pk
    assert create.ip == "10.0.0.9"
    assert update.before == {"name": "Simba"} and update.after == {"name": "Simba II"}
    assert status.changed_fields == ["status"]
    assert status.before == {"status": "healthy"} and status.after == {"status": "sick"}
    assert delete.after["deleted_at"] is not None


def test_restore_and_hard_delete_are_logged(farm_a):  # type: ignore[no-untyped-def]
    goat = GoatFactory(farm=farm_a)
    goat.delete()
    goat.restore()
    pk = goat.pk
    goat.hard_delete()
    actions = [e.action for e in AuditLog.unscoped.filter(object_id=str(pk)).order_by("at", "id")]
    assert actions == ["create", "delete", "restore", "delete"]


def test_audit_entries_are_append_only(farm_a):  # type: ignore[no-untyped-def]
    goat = GoatFactory(farm=farm_a)
    entry = _entries(goat)[0]
    with pytest.raises(RuntimeError):
        entry.save()
    with pytest.raises(RuntimeError):
        entry.delete()


def test_context_user_is_recorded_outside_requests(farm_a, admin_a):  # type: ignore[no-untyped-def]
    with farm_context(farm_a.pk, user_id=admin_a.pk):
        goat = GoatFactory(farm=farm_a)
    assert _entries(goat)[0].user == admin_a
    assert goat.created_by == admin_a


def test_audit_log_endpoint_is_admin_only(farm_a, member, client_for):  # type: ignore[no-untyped-def]
    GoatFactory(farm=farm_a)
    admin = member(farm_a, "administrator")
    manager = member(farm_a, "farm_manager")
    res = client_for(admin, farm_a).get("/api/v1/audit-logs?action=create")
    assert res.status_code == 200
    assert res.json()["count"] >= 1
    assert res.json()["results"][0]["object_type"] == "goat"
    assert client_for(manager, farm_a).get("/api/v1/audit-logs").status_code == 403


def test_request_context_reset_after_request(farm_a, admin_a, client_for):  # type: ignore[no-untyped-def]
    from apps.core.context import current_farm_id

    client_for(admin_a, farm_a).get("/api/v1/test-goats")
    assert current_farm_id() is None
    token = set_context(farm_id=farm_a.pk)
    reset_context(token)
    assert current_farm_id() is None
