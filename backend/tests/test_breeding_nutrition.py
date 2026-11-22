"""Phase 5: matings, pregnancies, births creating kids, deaths, feed stock and feeding."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.models import Role
from apps.calendar import services as cal
from apps.calendar.models import Activity
from apps.livestock.models import Animal, WeightRecord
from apps.notifications.events import domain_event
from apps.nutrition.models import FeedItem, FeedStockMovement
from apps.nutrition.services import seed_feed_items
from tests.factories import AnimalFactory, AnimalGroupFactory, FeedItemFactory, LocationFactory

pytestmark = pytest.mark.django_db
TODAY = timezone.localdate


def iso(d):  # type: ignore[no-untyped-def]
    return d.isoformat()


@pytest.fixture
def farm(farm_a):  # type: ignore[no-untyped-def]
    cal.seed_categories(farm_a)
    return farm_a


@pytest.fixture
def admin(farm, admin_a, client_for):  # type: ignore[no-untyped-def]
    return client_for(admin_a, farm)


@pytest.fixture
def attendant(farm, member, client_for):  # type: ignore[no-untyped-def]
    return client_for(member(farm, Role.LIVESTOCK_ATTENDANT), farm)


@pytest.fixture
def events():  # type: ignore[no-untyped-def]
    seen = []

    def receiver(sender, event_type, farm_id, **payload):  # type: ignore[no-untyped-def]
        seen.append((event_type, payload))

    domain_event.connect(receiver)
    yield seen
    domain_event.disconnect(receiver)


@pytest.fixture
def pair(farm):  # type: ignore[no-untyped-def]
    pen = LocationFactory(farm=farm, name="Night Pen")
    doe = AnimalFactory(
        farm=farm, animal_id="YPA-002", name="Neema", sex="female", breed="Galla", location=pen
    )
    buck = AnimalFactory(farm=farm, animal_id="YPA-001", name="Simba", sex="male", breed="Galla")
    return doe, buck


def mate(client, doe, buck=None, **extra):  # type: ignore[no-untyped-def]
    body = {"doe": str(doe.pk), "date": iso(TODAY() - timedelta(days=40)), **extra}
    if buck is not None:
        body["buck"] = str(buck.pk)
    return client.post("/api/v1/matings", body, format="json")


# --- Matings and pregnancy -----------------------------------------------------------------------------


def test_mating_sets_expected_kidding_and_tasks(farm, admin, pair):  # type: ignore[no-untyped-def]
    doe, buck = pair
    res = mate(admin, doe, buck)
    assert res.status_code == 201, res.content
    body = res.json()
    mated = TODAY() - timedelta(days=40)
    assert body["expected_kidding_date"] == iso(mated + timedelta(days=150))
    assert body["pregnancy_status"] == "awaiting_scan" and body["status"] == "active"
    assert body["progress"]["days_pregnant"] == 40 and body["progress"]["days_remaining"] == 110
    assert body["buck_label"] == "YPA-001 Simba"
    doe.refresh_from_db()
    assert doe.breeding_status == "served"
    tasks = {a.template_key: a for a in Activity.objects.filter(source="breeding")}
    assert tasks["scan"].date == mated + timedelta(days=35) and tasks["scan"].status == "overdue"
    assert (
        tasks["kidding"].title == "Expected kidding – YPA-002"
        and tasks["kidding"].category.key == "breeding"
    )


def test_mating_validation(farm, admin, pair):  # type: ignore[no-untyped-def]
    doe, buck = pair
    assert mate(admin, buck, doe).json()["errors"] == {
        "doe": ["Choose a female."],
        "buck": ["Choose a male."],
    }
    assert "AI straw" in mate(admin, doe).json()["errors"]["buck"][0]
    assert mate(admin, doe, ai_straw="Boer AI 0042", method="ai").status_code == 201
    again = mate(admin, doe, buck)
    assert "already has an open mating" in again.json()["errors"]["doe"][0]
    sheep = AnimalFactory(farm=farm, sex="male", species="sheep")
    other_doe = AnimalFactory(farm=farm, sex="female")
    assert mate(admin, other_doe, sheep).json()["errors"]["buck"] == [
        "The buck must be the same species."
    ]


def test_confirmed_scan_makes_doe_pregnant(farm, admin, pair):  # type: ignore[no-untyped-def]
    doe, buck = pair
    mid = mate(admin, doe, buck).json()["id"]
    res = admin.post(f"/api/v1/matings/{mid}/scan", {"result": "confirmed"}, format="json")
    assert res.json()["pregnancy_status"] == "confirmed" and res.json()["scan_date"] == iso(TODAY())
    doe.refresh_from_db()
    assert doe.breeding_status == "pregnant" and doe.health_status == "pregnant"
    assert Activity.objects.get(template_key="scan").status == "completed"
    [p] = admin.get("/api/v1/pregnancies").json()
    assert p["doe_label"] == "YPA-002 Neema" and p["days_pregnant"] == 40 and p["trimester"] == 1
    assert p["progress_percent"] == 27


def test_not_pregnant_closes_mating(farm, admin, pair):  # type: ignore[no-untyped-def]
    doe, buck = pair
    mid = mate(admin, doe, buck).json()["id"]
    res = admin.post(
        f"/api/v1/matings/{mid}/scan", {"result": "not_pregnant"}, format="json"
    ).json()
    assert res["status"] == "failed"
    doe.refresh_from_db()
    assert doe.breeding_status == "open"
    assert not Activity.objects.filter(template_key="kidding").exists()
    assert admin.get("/api/v1/pregnancies").json() == []
    assert (
        admin.post(
            f"/api/v1/matings/{mid}/scan", {"result": "confirmed"}, format="json"
        ).status_code
        == 400
    )
    assert mate(admin, doe, buck).status_code == 201  # the doe can be served again


def test_abort_resets_pregnant_doe(farm, admin, pair):  # type: ignore[no-untyped-def]
    doe, buck = pair
    mid = mate(admin, doe, buck).json()["id"]
    admin.post(f"/api/v1/matings/{mid}/scan", {"result": "confirmed"}, format="json")
    assert admin.post(f"/api/v1/matings/{mid}/abort").json()["status"] == "aborted"
    doe.refresh_from_db()
    assert doe.health_status == "healthy" and doe.breeding_status == "open"


def test_moving_mating_date_moves_expected_kidding(farm, admin, pair):  # type: ignore[no-untyped-def]
    doe, buck = pair
    mid = mate(admin, doe, buck).json()["id"]
    new = TODAY() - timedelta(days=20)
    res = admin.patch(f"/api/v1/matings/{mid}", {"date": iso(new)}, format="json").json()
    assert res["expected_kidding_date"] == iso(new + timedelta(days=150))
    assert Activity.objects.get(template_key="kidding").date == new + timedelta(days=150)


# --- Births ---------------------------------------------------------------------------------------------


def test_birth_adds_kids_to_register_and_closes_mating(farm, admin, attendant, pair):  # type: ignore[no-untyped-def]
    """Phase 5 "done when": registering a birth adds the kids to the register."""
    doe, buck = pair
    kids_group = AnimalGroupFactory(farm=farm, name="Kids")
    AnimalFactory(farm=farm, animal_id="YPA-020")
    mid = mate(admin, doe, buck).json()["id"]
    admin.post(f"/api/v1/matings/{mid}/scan", {"result": "confirmed"}, format="json")

    res = attendant.post(
        "/api/v1/births",
        {
            "dam": str(doe.pk),
            "condition": "assisted",
            "kids": [
                {"sex": "female", "name": "Baraka", "birth_weight_kg": "3.2", "ear_tag": "ke2001"},
                {"sex": "male", "birth_weight_kg": "3.6"},
                {"sex": "male", "alive": False},
            ],
        },
        format="json",
    )
    assert res.status_code == 201, res.content
    birth = res.json()
    assert birth["birth_type"] == "triplets" and birth["stillborn_count"] == 1
    assert birth["mating"] == mid and birth["sire_label"] == "YPA-001 Simba"
    assert [k["animal_id"] for k in birth["kids"]] == ["YPA-021", "YPA-022"]

    register = admin.get("/api/v1/animals?age=kid").json()["results"]
    assert {a["animal_id"] for a in register} == {"YPA-021", "YPA-022"}
    baraka = Animal.objects.get(animal_id="YPA-021")
    assert baraka.dam == doe and baraka.sire == buck and baraka.date_of_birth == TODAY()
    assert (
        baraka.ear_tag == "KE2001"
        and baraka.location == doe.location
        and baraka.group == kids_group
    )
    assert baraka.breeding_status == "too_young" and baraka.acquisition_source == "born_on_farm"
    assert WeightRecord.objects.get(animal=baraka).weight_kg == Decimal("3.20")

    mating = admin.get(f"/api/v1/matings/{mid}").json()
    assert (
        mating["status"] == "kidded"
        and mating["kids_count"] == 2
        and mating["actual_kidding_date"] == iso(TODAY())
    )
    doe.refresh_from_db()
    assert doe.breeding_status == "lactating" and doe.health_status == "healthy"
    assert Activity.objects.get(template_key="kidding").status == "completed"
    assert admin.get(f"/api/v1/animals/{doe.pk}").json()["offspring_count"] == 2
    titles = [e["title"] for e in admin.get(f"/api/v1/animals/{doe.pk}/timeline").json()]
    assert "Gave birth (Triplets)" in titles and "Mated with YPA-001" in titles
    kid_titles = [e["title"] for e in admin.get(f"/api/v1/animals/{baraka.pk}/timeline").json()]
    assert "Born to YPA-002" in kid_titles


def test_birth_validation(farm, admin, attendant, pair):  # type: ignore[no-untyped-def]
    doe, buck = pair
    AnimalFactory(farm=farm, animal_id="YPA-050", ear_tag="KE9")
    assert admin.post("/api/v1/births", {"dam": str(doe.pk), "kids": []}, format="json").json()[
        "errors"
    ]["kids"]
    assert (
        "female"
        in admin.post(
            "/api/v1/births", {"dam": str(buck.pk), "kids": [{"sex": "male"}]}, format="json"
        ).json()["errors"]["dam"][0]
    )
    dup = admin.post(
        "/api/v1/births",
        {"dam": str(doe.pk), "kids": [{"sex": "male", "animal_id": "ypa-050"}]},
        format="json",
    )
    assert "already used" in dup.json()["errors"]["kids"][0]
    assert not Animal.objects.filter(dam=doe).exists()  # nothing half-saved
    twice = admin.post(
        "/api/v1/births",
        {
            "dam": str(doe.pk),
            "kids": [{"sex": "male", "animal_id": "A"}, {"sex": "male", "animal_id": "a"}],
        },
        format="json",
    )
    assert twice.json()["errors"]["kids"] == ["Each kid needs its own animal ID."]
    assert attendant.get("/api/v1/matings").status_code == 200
    assert mate(attendant, doe, buck).status_code == 403


def test_birth_without_mating_on_record(farm, admin, pair):  # type: ignore[no-untyped-def]
    doe, _ = pair
    res = admin.post(
        "/api/v1/births", {"dam": str(doe.pk), "kids": [{"sex": "female"}]}, format="json"
    ).json()
    assert res["mating"] is None and res["birth_type"] == "single" and len(res["kids"]) == 1


def test_kids_list_with_growth(farm, admin, pair):  # type: ignore[no-untyped-def]
    doe, _ = pair
    born = TODAY() - timedelta(days=20)
    admin.post(
        "/api/v1/births",
        {
            "dam": str(doe.pk),
            "date": iso(born),
            "kids": [{"sex": "female", "birth_weight_kg": "3.0"}],
        },
        format="json",
    )
    kid = Animal.objects.get(dam=doe)
    admin.post(
        f"/api/v1/animals/{kid.pk}/weights",
        {"weight_kg": "5.0", "date": iso(TODAY())},
        format="json",
    )
    AnimalFactory(farm=farm)  # an adult, not listed
    [row] = admin.get("/api/v1/kids").json()["results"]
    assert row["age_days"] == 20 and row["dam_label"] == "YPA-002 Neema"
    assert (
        row["growth"]["birth_weight_kg"] == "3.00" and row["growth"]["average_daily_gain_g"] == 100
    )
    assert admin.get(f"/api/v1/kids/{kid.pk}/growth").json()["latest_weight_kg"] == "5.00"


# --- Deaths ---------------------------------------------------------------------------------------------


def test_death_takes_animal_out_and_alerts(farm, admin, attendant, pair, events):  # type: ignore[no-untyped-def]
    doe, buck = pair
    mid = mate(admin, doe, buck).json()["id"]
    assert (
        attendant.post("/api/v1/mortality", {"animal": str(doe.pk)}, format="json").status_code
        == 403
    )
    res = admin.post(
        "/api/v1/mortality",
        {"animal": str(doe.pk), "cause_category": "disease", "cause": "Suspected CCPP"},
        format="json",
    )
    assert res.status_code == 201
    assert res.json()["age_at_death_months"] == doe.age_in_months()
    doe.refresh_from_db()
    assert not doe.is_active and doe.exit_reason == "died" and doe.exit_notes == "Suspected CCPP"
    assert admin.get(f"/api/v1/matings/{mid}").json()["status"] == "failed"
    [(_name, payload)] = [e for e in events if e[0] == "health.alert"]
    assert payload["urgent"] is True and "Suspected CCPP" in payload["message"]
    again = admin.post("/api/v1/mortality", {"animal": str(doe.pk)}, format="json")
    assert again.json()["errors"]["animal"] == ["This animal is no longer in the herd."]
    # Recorded by mistake: deleting it brings the animal back.
    admin.delete(f"/api/v1/mortality/{res.json()['id']}")
    doe.refresh_from_db()
    assert doe.is_active


# --- Feed stock and feeding ------------------------------------------------------------------------------


def stock_in(client, item, qty, **extra):  # type: ignore[no-untyped-def]
    return client.post(
        f"/api/v1/feed-items/{item.pk}/stock",
        {"kind": "purchase", "quantity": qty, **extra},
        format="json",
    )


def test_feeding_lowers_stock(farm, admin, attendant, events):  # type: ignore[no-untyped-def]
    """Phase 5 "done when": feeding lowers the stock."""
    hay = FeedItemFactory(farm=farm, name="Rhodes hay", unit="bale", reorder_level="5")
    res = stock_in(admin, hay, "12", unit_cost_cents=45000, supplier="Nakuru Agrovet")
    assert res.json()["stock_quantity"] == "12.00" and res.json()["unit_cost_cents"] == 45000
    group = AnimalGroupFactory(farm=farm, name="Breeding Does")
    fed = attendant.post(
        "/api/v1/feeding-records",
        {"feed_item": str(hay.pk), "quantity": "4", "group": str(group.pk)},
        format="json",
    )
    assert fed.status_code == 201, fed.content
    hay.refresh_from_db()
    assert hay.stock_quantity == Decimal("8")
    assert events == []
    # Correcting the record re-deducts; crossing the reorder level raises one alert.
    admin.patch(f"/api/v1/feeding-records/{fed.json()['id']}", {"quantity": "7"}, format="json")
    hay.refresh_from_db()
    assert hay.stock_quantity == Decimal("5") and hay.is_low
    assert [e for e, _ in events] == ["feed.low_stock"]
    attendant.post(
        "/api/v1/feeding-records", {"feed_item": str(hay.pk), "quantity": "1"}, format="json"
    )
    assert [e for e, _ in events] == ["feed.low_stock"]  # still low: no repeat
    too_much = attendant.post(
        "/api/v1/feeding-records", {"feed_item": str(hay.pk), "quantity": "9"}, format="json"
    )
    assert too_much.json()["errors"]["quantity"] == ["Only 4 bale of Rhodes hay in stock."]
    # Deleting a feeding puts the feed back.
    admin.delete(f"/api/v1/feeding-records/{fed.json()['id']}")
    hay.refresh_from_db()
    assert hay.stock_quantity == Decimal("11")
    kinds = list(admin.get(f"/api/v1/feed-stock?feed_item={hay.pk}").json()["results"])
    assert [m["kind"] for m in kinds].count("usage") == 1


def test_days_left_from_last_14_days(farm, admin):  # type: ignore[no-untyped-def]
    meal = FeedItemFactory(farm=farm, name="Dairy meal", unit="kg")
    stock_in(admin, meal, "100")
    for days_ago in (1, 5, 10):
        admin.post(
            "/api/v1/feeding-records",
            {
                "feed_item": str(meal.pk),
                "quantity": "7",
                "date": iso(TODAY() - timedelta(days=days_ago)),
            },
            format="json",
        )
    admin.post(
        "/api/v1/feeding-records",
        {"feed_item": str(meal.pk), "quantity": "20", "date": iso(TODAY() - timedelta(days=30))},
        format="json",
    )
    item = admin.get(f"/api/v1/feed-items/{meal.pk}").json()
    assert item["stock_quantity"] == "59.00"
    assert item["average_daily_use"] == "1.50" and item["days_left"] == 39


def test_stock_count_and_waste(farm, admin, attendant):  # type: ignore[no-untyped-def]
    lick = FeedItemFactory(farm=farm, name="Mineral lick", unit="block")
    stock_in(admin, lick, "10")
    counted = admin.post(
        f"/api/v1/feed-items/{lick.pk}/stock",
        {"kind": "adjustment", "counted_quantity": "7"},
        format="json",
    )
    assert counted.json()["stock_quantity"] == "7.00"
    assert (
        admin.post(
            f"/api/v1/feed-items/{lick.pk}/stock", {"kind": "waste", "quantity": "2"}, format="json"
        ).json()["stock_quantity"]
        == "5.00"
    )
    assert (
        admin.post(
            f"/api/v1/feed-items/{lick.pk}/stock", {"kind": "waste", "quantity": "9"}, format="json"
        ).status_code
        == 400
    )
    assert admin.post(
        f"/api/v1/feed-items/{lick.pk}/stock", {"kind": "adjustment"}, format="json"
    ).json()["errors"]["counted_quantity"]
    assert (
        attendant.post(
            f"/api/v1/feed-items/{lick.pk}/stock",
            {"kind": "purchase", "quantity": "1"},
            format="json",
        ).status_code
        == 403
    )
    assert attendant.post("/api/v1/feed-items", {"name": "X"}, format="json").status_code == 403
    assert FeedStockMovement.objects.filter(feed_item=lick).count() == 3


def test_supplementation_from_stock(farm, admin, pair):  # type: ignore[no-untyped-def]
    doe, _ = pair
    lick = FeedItemFactory(farm=farm, name="Mineral lick", unit="block")
    stock_in(admin, lick, "4")
    res = admin.post(
        "/api/v1/supplementation",
        {
            "supplement": "Mineral lick",
            "feed_item": str(lick.pk),
            "quantity": "1",
            "animal": str(doe.pk),
        },
        format="json",
    )
    assert res.status_code == 201
    lick.refresh_from_db()
    assert lick.stock_quantity == Decimal("3")
    missing = admin.post(
        "/api/v1/supplementation", {"supplement": "x", "feed_item": str(lick.pk)}, format="json"
    )
    assert "quantity" in missing.json()["errors"]
    assert "Supplement: Mineral lick" in [
        e["title"] for e in admin.get(f"/api/v1/animals/{doe.pk}/timeline").json()
    ]


def test_assessment_links_calendar_and_hygiene_score(farm, admin, pair):  # type: ignore[no-untyped-def]
    doe, _ = pair
    admin.post(
        "/api/v1/nutrition-assessments",
        {
            "animal": str(doe.pk),
            "body_condition_score": "2.5",
            "next_assessment_date": iso(TODAY() + timedelta(days=30)),
        },
        format="json",
    )
    task = Activity.objects.get(title="Nutrition assessment – YPA-002")
    assert task.category.key == "feeding"
    check = admin.post(
        "/api/v1/water-hygiene",
        {"water_clean": False, "bedding_dry": False, "issues": "Trough dirty"},
        format="json",
    ).json()
    assert check["score"] == 3
    summary = admin.get("/api/v1/nutrition/summary").json()
    assert summary["last_hygiene_score"] == 3


def test_nutrition_summary_and_seeded_items(farm, admin):  # type: ignore[no-untyped-def]
    seed_feed_items(farm)
    hay = FeedItem.objects.get(name="Rhodes grass hay")
    stock_in(admin, hay, "20", unit_cost_cents=50000)
    admin.post(
        "/api/v1/feeding-records", {"feed_item": str(hay.pk), "quantity": "2"}, format="json"
    )
    s = admin.get("/api/v1/nutrition/summary").json()
    assert s["feed_items"] == 4 and s["feedings_today"] == 1
    assert s["feed_cost_this_month_cents"] == 20 * 50000
    assert (
        s["low_stock_items"] == 3
    )  # the three seeded items with no stock are at their reorder level
