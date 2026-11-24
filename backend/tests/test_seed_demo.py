"""seed_demo loads YPA FARM as in the prototype, is safe to re-run and refuses production."""

import pytest
from django.core.management import CommandError, call_command
from django.test import override_settings

from apps.accounts.models import Farm, FarmMembership
from apps.breeding.models import Mating
from apps.calendar.models import Activity
from apps.core.context import farm_context
from apps.livestock.models import Animal
from apps.reports import metrics

pytestmark = pytest.mark.django_db


def test_seed_demo_loads_the_demo_farm_and_is_safe_to_rerun():  # type: ignore[no-untyped-def]
    call_command("seed_demo")
    farm = Farm.objects.get(slug="ypa-farm")
    assert farm.name == "YPA FARM" and farm.currency == "UGX" and farm.country == "UG"
    with farm_context(farm.pk):
        animals = Animal.objects.order_by("animal_id")
        assert animals.count() == 20
        assert (animals.first().animal_id, animals.first().name) == ("YPA-001", "Simba")
        assert (animals.last().animal_id, animals.last().name) == ("YPA-020", "Subira")
        herd = metrics.herd()
        assert herd["kids"] == 5 and herd["pregnant"] == 4
        statuses = set(animals.values_list("health_status", flat=True))
        assert {"under_treatment", "sick", "quarantined", "monitoring"} <= statuses
        assert Mating.objects.filter(pregnancy_status="confirmed").count() == 4
        assert (
            Activity.objects.filter(template_key__startswith="2027").count()
            + Activity.objects.filter(source="template").count()
            >= 23
        )
        assert Activity.objects.filter(date__year=2026, date__month=11).count() >= 14
    members = FarmMembership.objects.filter(farm=farm)
    assert members.count() == 8
    assert members.filter(status="inactive").get().user.first_name == "Ali"

    call_command("seed_demo")  # again: nothing doubles
    with farm_context(farm.pk):
        assert Animal.objects.count() == 20
    assert FarmMembership.objects.filter(farm=farm).count() == 8

    call_command("seed_demo", "--reset")
    farm = Farm.objects.get(slug="ypa-farm")
    with farm_context(farm.pk):
        assert Animal.objects.count() == 20


@override_settings(APP_ENV="production")
def test_seed_demo_refuses_production_without_force():  # type: ignore[no-untyped-def]
    with pytest.raises(CommandError):
        call_command("seed_demo")
    assert not Farm.objects.filter(slug="ypa-farm").exists()
