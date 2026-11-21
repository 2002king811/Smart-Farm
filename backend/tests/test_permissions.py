import json
from pathlib import Path

import pytest
from django.core.management import CommandError, call_command

from apps.accounts.models import Role
from apps.core.permissions import load_matrix, role_can, role_scope
from tests.factories import GoatFactory

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    ("role", "module", "action", "allowed"),
    [
        (Role.ADMINISTRATOR, "users", "create", True),
        (Role.ADMINISTRATOR, "settings", "update", True),
        (Role.FARM_MANAGER, "reports", "view", True),
        (Role.FARM_MANAGER, "users", "view", False),
        (Role.FARM_MANAGER, "settings", "view", False),
        (Role.LIVESTOCK_ATTENDANT, "livestock", "create", True),
        (Role.LIVESTOCK_ATTENDANT, "livestock", "record_weight", True),
        (Role.LIVESTOCK_ATTENDANT, "livestock", "delete", False),
        (Role.LIVESTOCK_ATTENDANT, "health", "create", True),
        (Role.LIVESTOCK_ATTENDANT, "health", "delete", False),
        (Role.LIVESTOCK_ATTENDANT, "calendar", "create", False),
        (Role.LIVESTOCK_ATTENDANT, "activities", "complete", True),
        (Role.LIVESTOCK_ATTENDANT, "activities", "create", False),
        (Role.LIVESTOCK_ATTENDANT, "breeding", "record_birth", True),
        (Role.LIVESTOCK_ATTENDANT, "nutrition", "record_feeding", True),
        (Role.LIVESTOCK_ATTENDANT, "reports", "view", False),
        (Role.LIVESTOCK_ATTENDANT, "users", "view", False),
        ("unknown", "livestock", "view", False),
    ],
)
def test_role_table(role, module, action, allowed):  # type: ignore[no-untyped-def]
    assert role_can(role, module, action) is allowed


def test_scopes():  # type: ignore[no-untyped-def]
    assert role_scope(Role.LIVESTOCK_ATTENDANT, "activities") == "own"
    assert role_scope(Role.FARM_MANAGER, "activities") == "all"
    assert role_scope(Role.FARM_MANAGER, "users") is None


def test_every_role_lists_only_known_modules():  # type: ignore[no-untyped-def]
    matrix = load_matrix()
    for rules in matrix["roles"].values():
        assert set(rules) <= set(matrix["modules"])


def test_attendant_permissions_enforced_by_api(farm_a, member, client_for):  # type: ignore[no-untyped-def]
    attendant = member(farm_a, Role.LIVESTOCK_ATTENDANT)
    client = client_for(attendant, farm_a)
    goat = GoatFactory(farm=farm_a)
    assert client.get("/api/v1/test-goats").status_code == 200
    assert client.post("/api/v1/test-goats", {"name": "Kid"}).status_code == 201
    assert client.post(f"/api/v1/test-goats/{goat.pk}/weights", {}).status_code == 200
    denied = client.patch(f"/api/v1/test-goats/{goat.pk}", {"name": "X"})
    assert denied.status_code == 403
    assert denied.json() == {
        "errors": {"detail": ["Your role on this farm does not allow this action."]}
    }
    assert client.delete(f"/api/v1/test-goats/{goat.pk}").status_code == 403


def test_role_is_per_farm(farm_a, farm_b, member, client_for):  # type: ignore[no-untyped-def]
    from apps.accounts.models import FarmMembership

    user = member(farm_a, Role.LIVESTOCK_ATTENDANT)
    FarmMembership.objects.create(user=user, farm=farm_b, role=Role.ADMINISTRATOR)
    goat_a, goat_b = GoatFactory(farm=farm_a), GoatFactory(farm=farm_b)
    assert client_for(user, farm_a).delete(f"/api/v1/test-goats/{goat_a.pk}").status_code == 403
    assert client_for(user, farm_b).delete(f"/api/v1/test-goats/{goat_b.pk}").status_code == 204


def test_view_without_module_is_a_programming_error(rf, admin_a, farm_a):  # type: ignore[no-untyped-def]
    from apps.core.permissions import FarmModulePermission

    class NoModule:
        action = "list"

    request = rf.get("/")
    request.membership = admin_a.memberships.get()
    with pytest.raises(AssertionError):
        FarmModulePermission().has_permission(request, NoModule())


def test_frontend_copy_in_sync_check(tmp_path: Path):  # type: ignore[no-untyped-def]
    target = tmp_path / "permissions.json"
    with pytest.raises(CommandError):
        call_command("export_permissions", str(target), "--check")
    call_command("export_permissions", str(target))
    assert json.loads(target.read_text()) == load_matrix()
    call_command("export_permissions", str(target), "--check")


@pytest.mark.skipif(
    not (Path(__file__).resolve().parents[2] / "frontend").exists(),
    reason="frontend not present (e.g. inside the backend image)",
)
def test_repository_frontend_copy_is_in_sync():  # type: ignore[no-untyped-def]
    call_command("export_permissions", "--check")
