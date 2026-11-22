"""Phase 3: the livestock register, registration rules, weights, photos, exits and timeline."""

import csv
import io
from datetime import timedelta
from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from openpyxl import load_workbook
from PIL import Image

from apps.accounts.models import Role
from apps.livestock import services
from apps.livestock.models import Animal, AnimalPhoto, Location
from tests.factories import AnimalFactory, AnimalGroupFactory, LocationFactory, WeightRecordFactory

pytestmark = pytest.mark.django_db
TODAY = timezone.localdate


@pytest.fixture
def admin(farm_a, admin_a, client_for):  # type: ignore[no-untyped-def]
    return client_for(admin_a, farm_a)


@pytest.fixture
def attendant(farm_a, member, client_for):  # type: ignore[no-untyped-def]
    return client_for(member(farm_a, Role.LIVESTOCK_ATTENDANT), farm_a)


_seq = iter(range(1, 10_000))


def register(client, **fields):  # type: ignore[no-untyped-def]
    fields.setdefault("animal_id", f"NEW-{next(_seq):04d}")
    payload = {"name": "Simba", "sex": "male", "breed": "Galla", **fields}
    return client.post("/api/v1/animals", payload, format="json")


# --- IDs and registration ---------------------------------------------------------------------------


def test_next_id_uses_farm_prefix(farm_a, admin):  # type: ignore[no-untyped-def]
    assert admin.get("/api/v1/animals/next-id").json() == {"animal_id": "YPA-001"}
    AnimalFactory(farm=farm_a, animal_id="YPA-020")
    AnimalFactory(farm=farm_a, animal_id="YPA-007")
    AnimalFactory(farm=farm_a, animal_id="OTHER-99")
    AnimalFactory(animal_id="YPA-500")  # another farm: ignored
    assert admin.get("/api/v1/animals/next-id").json() == {"animal_id": "YPA-021"}


def test_register_animal_with_estimated_age(farm_a, admin):  # type: ignore[no-untyped-def]
    loc = LocationFactory(farm=farm_a)
    res = register(
        admin, ear_tag="ke 0001", estimated_age_months=18, location=str(loc.pk), animal_id="ypa-001"
    )
    assert res.status_code == 201, res.content
    body = res.json()
    assert body["animal_id"] == "YPA-001" and body["ear_tag"] == "KE 0001"
    assert body["dob_estimated"] is True and body["age_months"] == 18
    assert body["location"]["name"] == loc.name
    assert body["health_status"] == "healthy"


def test_ids_and_tags_unique_per_farm_only(farm_a, admin):  # type: ignore[no-untyped-def]
    AnimalFactory(farm=farm_a, animal_id="YPA-001", ear_tag="KE1")
    AnimalFactory(animal_id="YPA-002", ear_tag="KE2")  # other farm
    res = register(admin, animal_id="ypa-001", ear_tag="ke1")
    assert res.json()["errors"] == {
        "animal_id": ["This animal ID is already used on this farm."],
        "ear_tag": ["This ear tag is already used on this farm."],
    }
    assert register(admin, animal_id="YPA-002", ear_tag="KE2").status_code == 201
    # Blank ear tags never clash.
    assert register(admin, animal_id="YPA-003", ear_tag="").status_code == 201
    assert register(admin, animal_id="YPA-004", ear_tag="").status_code == 201


def test_soft_deleted_ids_can_be_reused(farm_a, admin):  # type: ignore[no-untyped-def]
    goat = AnimalFactory(farm=farm_a, animal_id="YPA-001")
    goat.delete()
    assert register(admin, animal_id="YPA-001").status_code == 201


def test_registration_validation(farm_a, admin):  # type: ignore[no-untyped-def]
    tomorrow = (TODAY() + timedelta(days=1)).isoformat()
    assert "sex" in register(admin, sex="").json()["errors"]
    res = register(admin, date_of_birth=tomorrow, acquisition_date=tomorrow)
    assert set(res.json()["errors"]) == {"date_of_birth", "acquisition_date"}
    both = register(admin, date_of_birth="2025-01-01", estimated_age_months=4)
    assert "estimated_age_months" in both.json()["errors"]
    early = register(admin, date_of_birth="2025-06-01", acquisition_date="2025-01-01")
    assert early.json()["errors"]["acquisition_date"] == [
        "The animal cannot be acquired before it was born."
    ]


def test_parent_rules(farm_a, farm_b, admin):  # type: ignore[no-untyped-def]
    doe = AnimalFactory(farm=farm_a, sex="female", date_of_birth=TODAY() - timedelta(days=900))
    buck = AnimalFactory(farm=farm_a, sex="male", date_of_birth=TODAY() - timedelta(days=900))
    young_doe = AnimalFactory(farm=farm_a, sex="female", date_of_birth=TODAY() - timedelta(days=10))
    sheep = AnimalFactory(farm=farm_a, sex="male", species="sheep")
    other_farm_doe = AnimalFactory(farm=farm_b, sex="female")
    dob = (TODAY() - timedelta(days=60)).isoformat()

    swapped = register(admin, date_of_birth=dob, dam=str(buck.pk), sire=str(doe.pk))
    assert swapped.json()["errors"] == {
        "dam": ["The dam (mother) must be female."],
        "sire": ["The sire (father) must be male."],
    }
    assert (
        "same species"
        in register(admin, date_of_birth=dob, sire=str(sheep.pk)).json()["errors"]["sire"][0]
    )
    assert (
        "older"
        in register(admin, date_of_birth=dob, dam=str(young_doe.pk)).json()["errors"]["dam"][0]
    )
    assert (
        "dam" in register(admin, dam=str(other_farm_doe.pk)).json()["errors"]
    )  # not found on this farm

    kid = register(admin, date_of_birth=dob, dam=str(doe.pk), sire=str(buck.pk), sex="female")
    assert kid.status_code == 201
    assert kid.json()["dam"]["animal_id"] == doe.animal_id
    self_parent = admin.patch(f"/api/v1/animals/{doe.pk}", {"dam": str(doe.pk)}, format="json")
    assert self_parent.json()["errors"]["dam"] == ["An animal cannot be its own parent."]
    detail = admin.get(f"/api/v1/animals/{doe.pk}").json()
    assert detail["offspring_count"] == 1


# --- Register: filters, summary, export ----------------------------------------------------------------


@pytest.fixture
def herd(farm_a):  # type: ignore[no-untyped-def]
    pen = LocationFactory(farm=farm_a, name="Night Pen")
    return {
        "simba": AnimalFactory(farm=farm_a, name="Simba", sex="male", breed="Boer", location=pen),
        "neema": AnimalFactory(farm=farm_a, name="Neema", health_status="pregnant"),
        "kid": AnimalFactory(
            farm=farm_a, name="Baraka", sex="male", date_of_birth=TODAY() - timedelta(days=60)
        ),
        "sick": AnimalFactory(farm=farm_a, name="Zawadi", health_status="sick"),
        "young": AnimalFactory(
            farm=farm_a, name="Imani", date_of_birth=TODAY() - timedelta(days=270)
        ),
        "sold": AnimalFactory(farm=farm_a, name="Old", is_active=False, exit_reason="sold"),
        "pen": pen,
    }


def _names(res):  # type: ignore[no-untyped-def]
    return sorted(a["name"] for a in res.json()["results"])


def test_register_filters(herd, admin):  # type: ignore[no-untyped-def]
    assert _names(admin.get("/api/v1/animals")) == ["Baraka", "Imani", "Neema", "Simba", "Zawadi"]
    assert _names(admin.get("/api/v1/animals?sex=male")) == ["Baraka", "Simba"]
    assert _names(admin.get("/api/v1/animals?age=kid")) == ["Baraka"]
    assert _names(admin.get("/api/v1/animals?age=young")) == ["Imani"]
    assert _names(admin.get("/api/v1/animals?age=adult")) == ["Neema", "Simba", "Zawadi"]
    assert _names(admin.get("/api/v1/animals?status=sick,pregnant")) == ["Neema", "Zawadi"]
    assert _names(admin.get("/api/v1/animals?attention=true")) == ["Zawadi"]
    assert _names(admin.get(f"/api/v1/animals?location={herd['pen'].pk}")) == ["Simba"]
    assert _names(admin.get("/api/v1/animals?breed=boer")) == ["Simba"]
    assert _names(admin.get("/api/v1/animals?search=zaw")) == ["Zawadi"]
    assert _names(admin.get("/api/v1/animals?active=false")) == ["Old"]
    assert len(admin.get("/api/v1/animals?active=all").json()["results"]) == 6
    ordered = admin.get("/api/v1/animals?ordering=-name").json()["results"]
    assert ordered[0]["name"] == "Zawadi"


def test_list_shows_latest_weight_and_kid_flag(farm_a, herd, admin):  # type: ignore[no-untyped-def]
    WeightRecordFactory(
        farm=farm_a, animal=herd["kid"], weight_kg="8.00", date=TODAY() - timedelta(days=30)
    )
    WeightRecordFactory(farm=farm_a, animal=herd["kid"], weight_kg="11.50", date=TODAY())
    row = next(a for a in admin.get("/api/v1/animals").json()["results"] if a["name"] == "Baraka")
    assert row["latest_weight_kg"] == "11.50" and row["is_kid"] is True and row["age_months"] == 1


def test_summary_counts(herd, admin):  # type: ignore[no-untyped-def]
    assert admin.get("/api/v1/animals/summary").json() == {
        "total": 5,
        "males": 2,
        "females": 3,
        "kids": 1,
        "needing_attention": 1,
        "pregnant": 1,
        "inactive": 1,
    }


def test_export_csv_and_excel(herd, admin, attendant):  # type: ignore[no-untyped-def]
    res = admin.get("/api/v1/animals/export?format=csv&sex=male")
    assert res["Content-Type"].startswith("text/csv")
    rows = list(csv.reader(io.StringIO(res.content.decode("utf-8-sig"))))
    assert rows[0][:3] == ["Animal ID", "Ear tag", "Name"]
    assert sorted(r[2] for r in rows[1:]) == ["Baraka", "Simba"]

    xlsx = admin.get("/api/v1/animals/export?format=xlsx")
    sheet = load_workbook(BytesIO(xlsx.content)).active
    assert sheet.max_row == 6 and sheet["A1"].value == "Animal ID"
    assert sheet.freeze_panes == "A2"
    dob_col = [c.value for c in sheet[1]].index("Date of birth") + 1
    assert hasattr(sheet.cell(row=2, column=dob_col).value, "year")  # real dates, not text
    assert attendant.get("/api/v1/animals/export").status_code == 403


# --- Roles ---------------------------------------------------------------------------------------------


def test_attendant_can_view_register_and_weigh_only(farm_a, attendant):  # type: ignore[no-untyped-def]
    goat = AnimalFactory(farm=farm_a)
    assert attendant.get("/api/v1/animals").status_code == 200
    assert register(attendant).status_code == 201
    weigh = attendant.post(
        f"/api/v1/animals/{goat.pk}/weights", {"weight_kg": "30.2"}, format="json"
    )
    assert weigh.status_code == 201
    assert (
        attendant.patch(f"/api/v1/animals/{goat.pk}", {"name": "X"}, format="json").status_code
        == 403
    )
    assert attendant.delete(f"/api/v1/animals/{goat.pk}").status_code == 403
    assert attendant.post(f"/api/v1/animals/{goat.pk}/exit", {"reason": "sold"}).status_code == 403
    assert attendant.delete(f"/api/v1/weights/{weigh.json()['id']}").status_code == 403
    assert attendant.post("/api/v1/locations", {"name": "New"}).status_code == 403


# --- Weights -------------------------------------------------------------------------------------------


def test_weights_list_with_gain_and_corrections(farm_a, admin, member, client_for):  # type: ignore[no-untyped-def]
    goat = AnimalFactory(farm=farm_a)
    url = f"/api/v1/animals/{goat.pk}/weights"
    admin.post(
        url, {"weight_kg": "28", "date": (TODAY() - timedelta(days=30)).isoformat()}, format="json"
    )
    second = admin.post(
        url, {"weight_kg": "31.5", "body_condition_score": "3.5"}, format="json"
    ).json()
    rows = admin.get(url).json()
    assert [r["weight_kg"] for r in rows] == ["31.50", "28.00"]
    assert rows[0]["gain_kg"] == "3.50" and rows[1]["gain_kg"] is None
    assert rows[0]["recorded_by"]

    bad = admin.post(
        url,
        {
            "weight_kg": "0",
            "date": (TODAY() + timedelta(days=1)).isoformat(),
            "body_condition_score": "7",
        },
        format="json",
    )
    assert set(bad.json()["errors"]) == {"weight_kg", "date", "body_condition_score"}

    manager = client_for(member(farm_a, Role.FARM_MANAGER), farm_a)
    assert (
        manager.patch(
            f"/api/v1/weights/{second['id']}", {"weight_kg": "31.0"}, format="json"
        ).status_code
        == 200
    )
    assert manager.delete(f"/api/v1/weights/{second['id']}").status_code == 204
    assert len(admin.get(url).json()) == 1


# --- Photos --------------------------------------------------------------------------------------------


def _jpeg_with_gps() -> SimpleUploadedFile:
    buf = BytesIO()
    exif = Image.Exif()
    exif[0x8825] = {2: (1.0, 17.0, 0.0)}
    Image.new("RGB", (3000, 2000), "brown").save(buf, format="JPEG", exif=exif)
    return SimpleUploadedFile("goat.jpg", buf.getvalue(), content_type="image/jpeg")


def test_photo_upload_thumbnail_primary_and_delete(farm_a, admin, attendant):  # type: ignore[no-untyped-def]
    goat = AnimalFactory(farm=farm_a)
    url = f"/api/v1/animals/{goat.pk}/photos"
    first = attendant.post(url, {"file": _jpeg_with_gps()}, format="multipart")
    assert first.status_code == 201, first.content
    assert first.json()["is_primary"] is True  # the first photo becomes the profile photo
    photo = AnimalPhoto.objects.get(pk=first.json()["id"])
    full, thumb = Image.open(photo.file), Image.open(photo.thumbnail)
    assert max(full.size) == 1600 and max(thumb.size) == 400
    assert not full.getexif() and not thumb.getexif()

    second = admin.post(
        url, {"file": _jpeg_with_gps(), "caption": "Side view"}, format="multipart"
    ).json()
    assert second["is_primary"] is False
    listing = admin.get("/api/v1/animals").json()["results"][0]
    assert listing["thumbnail"].endswith(".jpg")

    assert attendant.post(f"/api/v1/animal-photos/{second['id']}/primary").status_code == 403
    assert admin.post(f"/api/v1/animal-photos/{second['id']}/primary").json()["is_primary"] is True
    assert [p["is_primary"] for p in admin.get(url).json()] == [True, False]
    assert admin.delete(f"/api/v1/animal-photos/{second['id']}").status_code == 204
    assert admin.get(url).json()[0]["is_primary"] is True  # the other photo takes over

    gif = BytesIO()
    Image.new("RGB", (10, 10)).save(gif, format="GIF")
    bad = admin.post(
        url,
        {"file": SimpleUploadedFile("a.gif", gif.getvalue(), content_type="image/gif")},
        format="multipart",
    )
    assert bad.status_code == 400


# --- Exit, timeline, locations ----------------------------------------------------------------------------


def test_exit_and_reactivate(farm_a, admin):  # type: ignore[no-untyped-def]
    goat = AnimalFactory(farm=farm_a)
    res = admin.post(
        f"/api/v1/animals/{goat.pk}/exit", {"reason": "sold", "notes": "Nakuru market"}
    )
    assert res.json()["is_active"] is False and res.json()["exit_reason"] == "sold"
    assert admin.get("/api/v1/animals").json()["count"] == 0
    assert admin.get(f"/api/v1/animals/{goat.pk}").status_code == 200  # history still reachable
    assert admin.post(f"/api/v1/animals/{goat.pk}/reactivate").json()["is_active"] is True


def test_timeline_collects_events(farm_a, admin):  # type: ignore[no-untyped-def]
    pen, iso = LocationFactory(farm=farm_a, name="Night Pen"), LocationFactory(
        farm=farm_a, name="Isolation Pen"
    )
    goat_id = register(admin, location=str(pen.pk)).json()["id"]
    admin.post(f"/api/v1/animals/{goat_id}/weights", {"weight_kg": "30"}, format="json")
    admin.patch(
        f"/api/v1/animals/{goat_id}",
        {"health_status": "sick", "location": str(iso.pk)},
        format="json",
    )
    admin.post(f"/api/v1/animals/{goat_id}/exit", {"reason": "died"})
    events = admin.get(f"/api/v1/animals/{goat_id}/timeline").json()
    titles = [e["title"] for e in events]
    assert "Registered" in titles
    assert "Weighed 30.00 kg" in titles
    assert "Health status: Sick" in titles
    assert "Moved to Isolation Pen" in titles
    assert "Left the herd: Died" in titles
    assert all(events[i]["at"] >= events[i + 1]["at"] for i in range(len(events) - 1))


def test_new_farm_gets_default_locations_and_groups():  # type: ignore[no-untyped-def]
    from rest_framework.test import APIClient

    from apps.accounts.models import Farm

    res = APIClient().post(
        "/api/v1/auth/signup",
        {
            "first_name": "A",
            "last_name": "B",
            "email": "a@b.ke",
            "phone": "0712000000",
            "password": "Green-Pasture-27",
            "farm_name": "Test Farm",
            "livestock_types": ["goats"],
        },
        format="json",
    )
    assert res.status_code == 201
    farm = Farm.objects.get(name="Test Farm")
    names = set(Location.unscoped.filter(farm=farm).values_list("name", flat=True))
    assert {"Isolation Pen", "Quarantine Pen", "Main Paddock"} <= names
    services.seed_farm_defaults(farm)  # safe to run twice
    assert Location.unscoped.filter(farm=farm).count() == len(names)


def test_locations_and_groups(farm_a, admin):  # type: ignore[no-untyped-def]
    pen = LocationFactory(farm=farm_a, name="Night Pen", capacity=30)
    group = AnimalGroupFactory(farm=farm_a, name="Does")
    AnimalFactory.create_batch(2, farm=farm_a, location=pen, group=group)
    AnimalFactory(farm=farm_a, location=pen, is_active=False)
    locs = admin.get("/api/v1/locations").json()
    assert locs == [
        {
            "id": str(pen.pk),
            "name": "Night Pen",
            "type": "pen",
            "capacity": 30,
            "description": "",
            "animal_count": 2,
        }
    ]
    assert admin.post("/api/v1/locations", {"name": "night pen"}).json()["errors"]["name"]
    assert admin.get("/api/v1/animal-groups").json()[0]["animal_count"] == 2
    assert admin.delete(f"/api/v1/locations/{pen.pk}").status_code == 204
    assert not Animal.objects.filter(location__isnull=False).exists()


def test_age_helpers():  # type: ignore[no-untyped-def]
    from datetime import date

    assert services.months_before(date(2026, 3, 31), 1) == date(2026, 2, 28)
    assert services.months_before(date(2026, 1, 15), 13) == date(2024, 12, 15)
    goat = Animal(date_of_birth=date(2026, 1, 20))
    assert goat.age_in_months(date(2026, 7, 19)) == 5
    assert goat.age_in_months(date(2026, 7, 20)) == 6
    assert Animal().age_in_months() is None
