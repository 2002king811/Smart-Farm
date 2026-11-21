"""The model layer enforces tenancy even when a view forgets to."""

import uuid

import pytest

from apps.accounts.models import FarmMembership, FarmStatus, MembershipStatus, Role
from apps.core.context import current_farm_id, farm_context
from apps.core.models import TenancyViolation
from apps.core.tasks import FarmTask
from tests.factories import GoatFactory, PenFactory
from tests.testapp.models import Goat

pytestmark = pytest.mark.django_db


def test_manager_scopes_to_active_farm(farm_a, farm_b):  # type: ignore[no-untyped-def]
    ga, gb = GoatFactory(farm=farm_a), GoatFactory(farm=farm_b)
    with farm_context(farm_a.pk):
        assert list(Goat.objects.all()) == [ga]
        assert not Goat.objects.filter(pk=gb.pk).exists()
    assert set(Goat.unscoped.all()) == {ga, gb}


def test_save_assigns_active_farm(farm_a):  # type: ignore[no-untyped-def]
    with farm_context(farm_a.pk):
        goat = Goat.objects.create(name="Simba")
    assert goat.farm_id == farm_a.pk


def test_save_without_farm_or_context_is_refused():  # type: ignore[no-untyped-def]
    with pytest.raises(TenancyViolation):
        Goat(name="Orphan").save()


def test_cannot_write_for_another_farm(farm_a, farm_b):  # type: ignore[no-untyped-def]
    with farm_context(farm_a.pk), pytest.raises(TenancyViolation):
        Goat.objects.create(name="Intruder", farm=farm_b)


def test_cannot_move_record_between_farms(farm_a, farm_b):  # type: ignore[no-untyped-def]
    goat = Goat.unscoped.get(pk=GoatFactory(farm=farm_a).pk)
    goat.farm = farm_b
    with pytest.raises(TenancyViolation):
        goat.save()


def test_foreign_key_must_stay_in_farm(farm_a, farm_b):  # type: ignore[no-untyped-def]
    pen_b = PenFactory(farm=farm_b)
    with pytest.raises(TenancyViolation):
        Goat.unscoped.create(farm=farm_a, name="Simba", pen=pen_b)
    with pytest.raises(TenancyViolation):
        Goat.unscoped.create(farm=farm_a, name="Simba", pen_id=pen_b.pk)  # uncached FK path
    pen_a = PenFactory(farm=farm_a)
    assert Goat.unscoped.create(farm=farm_a, name="Simba", pen=pen_a).pen == pen_a


def test_many_to_many_must_stay_in_farm(farm_a, farm_b):  # type: ignore[no-untyped-def]
    goat = GoatFactory(farm=farm_a)
    goat.visited_pens.add(PenFactory(farm=farm_a))
    with pytest.raises(TenancyViolation):
        goat.visited_pens.add(PenFactory(farm=farm_b))


def test_soft_delete_hides_but_keeps_row(farm_a):  # type: ignore[no-untyped-def]
    goat = GoatFactory(farm=farm_a)
    goat.delete()
    assert not Goat.objects.filter(pk=goat.pk).exists()
    assert Goat.unscoped.get(pk=goat.pk).deleted_at is not None
    goat.restore()
    assert Goat.objects.filter(pk=goat.pk).exists()


def test_queryset_delete_is_soft(farm_a):  # type: ignore[no-untyped-def]
    GoatFactory.create_batch(2, farm=farm_a)
    count, _ = Goat.objects.filter(farm=farm_a).delete()
    assert count == 2
    assert Goat.unscoped.filter(farm=farm_a, deleted_at__isnull=False).count() == 2
    Goat.unscoped.filter(farm=farm_a).hard_delete()
    assert not Goat.unscoped.filter(farm=farm_a).exists()


def test_farm_context_is_restored():  # type: ignore[no-untyped-def]
    fid = uuid.uuid4()
    with farm_context(fid):
        assert current_farm_id() == fid
    assert current_farm_id() is None


def test_farm_task_runs_inside_farm_context(farm_a):  # type: ignore[no-untyped-def]
    from config.celery import app

    seen = {}

    @app.task(base=FarmTask, name="tests.probe")
    def probe(farm_id):  # type: ignore[no-untyped-def]
        seen["farm"] = current_farm_id()
        return Goat.objects.count()

    GoatFactory(farm=farm_a)
    GoatFactory()  # another farm
    assert probe.apply(kwargs={"farm_id": str(farm_a.pk)}).get() == 1
    assert seen["farm"] == farm_a.pk
    assert current_farm_id() is None


def test_inactive_membership_gets_404(farm_a, member, client_for):  # type: ignore[no-untyped-def]
    user = member(farm_a, Role.ADMINISTRATOR, status=MembershipStatus.INACTIVE)
    assert client_for(user, farm_a).get("/api/v1/test-goats").status_code == 404


def test_missing_or_bad_farm_header_gets_404(admin_a, client_for):  # type: ignore[no-untyped-def]
    assert client_for(admin_a).get("/api/v1/test-goats").status_code == 404
    client = client_for(admin_a)
    client.credentials(HTTP_X_FARM_ID="not-a-uuid")
    assert client.get("/api/v1/test-goats").status_code == 404


def test_suspended_farm_gets_403_for_members(farm_a, admin_a, client_for):  # type: ignore[no-untyped-def]
    farm_a.status = FarmStatus.SUSPENDED
    farm_a.save()
    res = client_for(admin_a, farm_a).get("/api/v1/test-goats")
    assert res.status_code == 403
    assert "suspended" in res.json()["errors"]["detail"][0]


def test_unauthenticated_gets_401(farm_a, client_for):  # type: ignore[no-untyped-def]
    res = client_for(None, farm_a).get("/api/v1/test-goats")
    assert res.status_code == 401
    assert res.json()["errors"]["detail"]


def test_api_create_sets_farm_and_author(farm_a, admin_a, client_for):  # type: ignore[no-untyped-def]
    res = client_for(admin_a, farm_a).post("/api/v1/test-goats", {"name": "Simba"})
    assert res.status_code == 201, res.content
    goat = Goat.unscoped.get(pk=res.json()["id"])
    assert goat.farm_id == farm_a.pk
    assert goat.created_by == admin_a and goat.updated_by == admin_a


def test_api_rejects_foreign_key_from_other_farm(farm_a, farm_b, admin_a, client_for):  # type: ignore[no-untyped-def]
    pen_b = PenFactory(farm=farm_b)
    res = client_for(admin_a, farm_a).post(
        "/api/v1/test-goats", {"name": "Simba", "pen": str(pen_b.pk)}
    )
    assert res.status_code == 400
    assert "pen" in res.json()["errors"]


def test_jwt_farm_claim_is_used_when_header_missing(farm_a, admin_a):  # type: ignore[no-untyped-def]
    from rest_framework.test import APIClient
    from rest_framework_simplejwt.tokens import AccessToken

    token = AccessToken.for_user(admin_a)
    token["farm_id"] = str(farm_a.pk)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    assert client.get("/api/v1/test-goats").status_code == 200
    FarmMembership.objects.filter(user=admin_a).update(status=MembershipStatus.INACTIVE)
    assert client.get("/api/v1/test-goats").status_code == 404
