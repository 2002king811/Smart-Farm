"""Loads the demonstration farm, YPA FARM, so the app looks like the approved design.

    python manage.py seed_demo            # create or top up the demo farm (safe to re-run)
    python manage.py seed_demo --reset    # delete the demo farm first, then create it again
    python manage.py seed_demo --force    # needed in staging/production

What it adds: 8 people (2 administrators, 2 farm managers, 4 attendants, one inactive),
20 goats YPA-001 Simba … YPA-020 Subira (5 kids, 4 pregnant does, and animals under treatment,
sick, quarantined and monitoring), the November 2026 activities, the 23 planned 2027 health
calendar activities, and vaccination, deworming, treatment, vet visit, breeding, kid, feeding
and notification records. Everyone's password is printed at the end.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Farm, FarmMembership, MembershipStatus, Role, User
from apps.accounts.signals import farm_created
from apps.core.context import farm_context

FARM_SLUG = "ypa-farm"
PASSWORD = "Demo-Farm-2026"  # noqa: S105 - published demo password, demo farm only
VET = "Dr. Samuel Mutua"

PEOPLE = [
    # first, last, role, job title, active
    ("Daniel", "Mwangi", Role.ADMINISTRATOR, "Owner", True),
    ("Faith", "Wambui", Role.ADMINISTRATOR, "Co-owner", True),
    ("Grace", "Wanjiru", Role.FARM_MANAGER, "Farm manager", True),
    ("Esther", "Njeri", Role.FARM_MANAGER, "Assistant manager", True),
    ("Peter", "Otieno", Role.LIVESTOCK_ATTENDANT, "Herdsman", True),
    ("Mary", "Achieng", Role.LIVESTOCK_ATTENDANT, "Kid pen attendant", True),
    ("James", "Kiprop", Role.LIVESTOCK_ATTENDANT, "Herdsman", True),
    ("Ali", "Hassan", Role.LIVESTOCK_ATTENDANT, "Herdsman", False),
]

# animal id, name, sex, breed, age in days, location, health status
GOATS = [
    ("YPA-001", "Simba", "male", "Boer", 1460, "Night Pen", "healthy"),
    ("YPA-002", "Neema", "female", "Galla", 1100, "Main Paddock", "pregnant"),
    ("YPA-003", "Baraka", "male", "Galla", 900, "Main Paddock", "healthy"),
    ("YPA-004", "Zawadi", "female", "Toggenburg", 1300, "Main Paddock", "pregnant"),
    ("YPA-005", "Imani", "female", "Galla", 820, "Main Paddock", "pregnant"),
    ("YPA-006", "Amani", "female", "Saanen cross", 1000, "Kid Pen", "healthy"),
    ("YPA-007", "Furaha", "female", "Galla", 760, "Main Paddock", "under_treatment"),
    ("YPA-008", "Tumaini", "female", "Boer", 690, "Isolation Pen", "sick"),
    ("YPA-009", "Upendo", "female", "Galla", 1200, "Main Paddock", "pregnant"),
    ("YPA-010", "Jabari", "male", "Boer", 540, "Quarantine Pen", "quarantined"),
    ("YPA-011", "Rehema", "female", "Toggenburg", 980, "Main Paddock", "monitoring"),
    ("YPA-012", "Malaika", "female", "Galla", 620, "Main Paddock", "healthy"),
    ("YPA-013", "Kito", "male", "Galla", 400, "Night Pen", "healthy"),
    ("YPA-014", "Nuru", "female", "Saanen cross", 450, "Main Paddock", "healthy"),
    ("YPA-015", "Asali", "female", "Galla", 300, "Main Paddock", "healthy"),
    ("YPA-016", "Bahati", "female", "Galla", 95, "Kid Pen", "healthy"),
    ("YPA-017", "Shujaa", "male", "Galla", 95, "Kid Pen", "healthy"),
    ("YPA-018", "Pendo", "female", "Saanen cross", 60, "Kid Pen", "healthy"),
    ("YPA-019", "Tausi", "female", "Saanen cross", 60, "Kid Pen", "healthy"),
    ("YPA-020", "Subira", "male", "Boer", 30, "Kid Pen", "healthy"),
]

# November 2026: day, title, category, priority, assignee first name, status
NOVEMBER = [
    (2, "Weekly weighing – all kids", "inspection", "medium", "Mary", "completed"),
    (4, "Dip the herd (tick control)", "parasite_control", "high", "Peter", "completed"),
    (6, "PPR booster – young stock", "vaccination", "high", "James", "completed"),
    (9, "Hoof trimming – adult does", "inspection", "medium", "Peter", "completed"),
    (11, "Vet visit – herd check", "vet_visit", "high", "Grace", "completed"),
    (13, "Deworm young stock (Albendazole)", "deworming", "high", "Mary", "completed"),
    (16, "Pregnancy scan – Zawadi and Imani", "breeding", "medium", "Grace", "completed"),
    (18, "Restock dairy meal", "feeding", "medium", "Esther", "overdue"),
    (20, "Clean and disinfect kid pen", "inspection", "medium", "Mary", "overdue"),
    (23, "Weekly weighing – all kids", "inspection", "medium", "Mary", "in_progress"),
    (25, "Follow-up treatment – Furaha", "treatment", "high", "Peter", "pending"),
    (26, "Dip the herd (tick control)", "parasite_control", "high", "Peter", "pending"),
    (27, "CCPP vaccination – adults", "vaccination", "high", "James", "pending"),
    (30, "Monthly body condition scoring", "feeding", "low", "Grace", "pending"),
]


class Command(BaseCommand):
    help = "Load the YPA FARM demonstration data (safe to re-run)."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--reset", action="store_true", help="Delete the demo farm first")
        parser.add_argument("--force", action="store_true", help="Allow in staging/production")

    def handle(self, *args: Any, **options: Any) -> None:
        if settings.APP_ENV in ("staging", "production") and not options["force"]:
            raise CommandError(
                f"Refusing to load demo data in {settings.APP_ENV}. Add --force if you are sure."
            )
        if options["reset"]:
            old = Farm.objects.filter(slug=FARM_SLUG).first()
            if old:
                delete_farm(old)
                self.stdout.write("Deleted the old demo farm.")
        with transaction.atomic():
            farm, created = self.farm()
            with farm_context(farm.pk):
                people = self.people(farm)
                if created or not farm_has_animals(farm):
                    seed_records(farm, people)
                    self.stdout.write(self.style.SUCCESS("Added the demo animals and records."))
                else:
                    self.stdout.write(
                        "The demo farm already has animals; records were left as they are."
                    )
        self.stdout.write(
            self.style.SUCCESS(f"\nYPA FARM is ready. Everyone's password: {PASSWORD}")
        )
        for first, last, role, _title, active in PEOPLE:
            note = "" if active else " (inactive)"
            name = f"{first} {last}"
            self.stdout.write(f"  {name:<16} {Role(role).label:<20} {email_for(first, last)}{note}")

    def farm(self) -> tuple[Farm, bool]:
        farm = Farm.objects.filter(slug=FARM_SLUG).first()
        if farm:
            return farm, False
        farm = Farm.objects.create(
            name="YPA FARM",
            slug=FARM_SLUG,
            country="UG",
            county="Mbarara",
            location="Rwanyamahembe, Mbarara",
            currency="UGX",
            timezone="Africa/Kampala",
            phone="+256772000001",
            email=email_for("Daniel", "Mwangi"),
            description="A goat farm: Galla, Boer, Toggenburg and Saanen crosses for meat and milk.",
            herd_size_band="1-20",
            livestock_types=["goats"],
            animal_id_prefix="YPA",
        )
        return farm, True

    def people(self, farm: Farm) -> dict[str, User]:
        out: dict[str, User] = {}
        for i, (first, last, role, title, active) in enumerate(PEOPLE, start=1):
            email = email_for(first, last)
            user = User.objects.filter(email=email).first()
            if user is None:
                user = User(
                    username=f"{first}.{last}".lower(),
                    first_name=first,
                    last_name=last,
                    email=email,
                    phone=f"+2567720000{i:02d}",
                    email_verified=True,
                    phone_verified=True,
                    alert_channels=["in_app", "email", "sms", "whatsapp"],
                )
                user.set_password(PASSWORD)
                user.save()
            FarmMembership.objects.update_or_create(
                user=user,
                farm=farm,
                defaults={
                    "role": role,
                    "job_title": title,
                    "status": MembershipStatus.ACTIVE if active else MembershipStatus.INACTIVE,
                },
            )
            out[first] = user
        if not farm_has_animals(farm):
            farm_created.send(sender=Farm, farm=farm, created_by=out["Daniel"])
        return out


@transaction.atomic
def delete_farm(farm: Farm) -> None:
    """Removes a farm and everything it owns (rows protecting each other go in later passes)."""
    from django.apps import apps
    from django.db.models import ProtectedError

    from apps.core.models import FarmOwnedModel

    models = [m for m in apps.get_models() if issubclass(m, FarmOwnedModel)]
    for _ in range(len(models)):
        remaining = []
        for model in models:
            try:
                with transaction.atomic():
                    qs = model._base_manager.filter(farm=farm)
                    qs.hard_delete() if hasattr(qs, "hard_delete") else qs.delete()
            except ProtectedError:
                remaining.append(model)
        if not remaining:
            break
        models = remaining
    farm.delete()


def email_for(first: str, last: str) -> str:
    return f"{first}.{last}@ypafarm.example.com".lower()


def farm_has_animals(farm: Farm) -> bool:
    from apps.livestock.models import Animal

    return Animal.unscoped.filter(farm=farm).exists()


def seed_records(farm: Farm, people: dict[str, User]) -> None:
    from apps.breeding.models import Birth, Mating, PregnancyStatus
    from apps.calendar import services as cal
    from apps.calendar.models import Activity
    from apps.health import services as health
    from apps.health.models import (
        Deworming,
        HealthObservation,
        Medicine,
        Treatment,
        Vaccination,
        Vaccine,
        VetVisit,
    )
    from apps.livestock.models import Animal, Location, WeightRecord
    from apps.notifications.services import notify
    from apps.nutrition import services as nutrition
    from apps.nutrition.models import FeedingRecord, FeedItem, MovementKind

    today = timezone.localdate()
    daniel, grace, peter, mary = people["Daniel"], people["Grace"], people["Peter"], people["Mary"]
    by = {"created_by": daniel, "updated_by": daniel}
    locations = {loc.name: loc for loc in Location.objects.all()}

    goats: dict[str, Animal] = {}
    for animal_id, name, sex, breed, age, loc, status in GOATS:
        goats[name] = Animal.objects.create(
            farm=farm,
            animal_id=animal_id,
            ear_tag=f"UG{animal_id[-3:]}",
            name=name,
            species="goat",
            sex=sex,
            breed=breed,
            date_of_birth=today - dt.timedelta(days=age),
            acquisition_source="born_on_farm" if age < 400 else "purchased",
            acquisition_date=today - dt.timedelta(days=min(age, 700)),
            location=locations.get(loc),
            health_status=status,
            breeding_status=(
                "breeding_male"
                if sex == "male" and age > 365
                else "too_young" if age < 200 else "open"
            ),
            **by,
        )
        # A few weights for growth charts.
        for weeks, kg in ((8, 0.9), (4, 0.95), (0, 1.0)):
            base = Decimal(min(8 + age / 30, 55)).quantize(Decimal("0.1"))
            WeightRecord.objects.create(
                farm=farm,
                animal=goats[name],
                date=today - dt.timedelta(weeks=weeks),
                weight_kg=(base * Decimal(str(kg))).quantize(Decimal("0.1")),
                **by,
            )

    # Breeding: four confirmed pregnancies, two births that produced the kids.
    simba = goats["Simba"]
    for doe, days_ago in (("Neema", 110), ("Zawadi", 60), ("Imani", 55), ("Upendo", 125)):
        Mating.objects.create(
            farm=farm,
            doe=goats[doe],
            buck=simba,
            date=today - dt.timedelta(days=days_ago),
            method="natural",
            pregnancy_status=PregnancyStatus.CONFIRMED,
            scan_date=today - dt.timedelta(days=days_ago - 35),
            expected_kidding_date=today - dt.timedelta(days=days_ago) + dt.timedelta(days=150),
            **by,
        )
        Animal.objects.filter(pk=goats[doe].pk).update(breeding_status="pregnant")
    for dam, kids, days_ago, kind in (
        ("Amani", ["Bahati", "Shujaa"], 95, "twins"),
        ("Nuru", ["Pendo", "Tausi"], 60, "twins"),
    ):
        birth = Birth.objects.create(
            farm=farm,
            dam=goats[dam],
            sire=simba,
            date=today - dt.timedelta(days=days_ago),
            birth_type=kind,
            **by,
        )
        birth.kids.set([goats[k] for k in kids])
        for k in kids:
            Animal.objects.filter(pk=goats[k].pk).update(dam=goats[dam], sire=simba)
    Animal.objects.filter(pk__in=[goats["Amani"].pk, goats["Nuru"].pk]).update(
        breeding_status="lactating"
    )

    # Health records.
    ppr = Vaccine.objects.filter(name="PPR vaccine").first()
    ccpp = Vaccine.objects.filter(name="CCPP vaccine").first()
    albendazole = Medicine.objects.filter(name="Albendazole").first()
    oxytet = Medicine.objects.filter(name="Oxytetracycline LA").first()
    for name in ("Kito", "Nuru", "Asali", "Malaika", "Baraka"):
        v = Vaccination.objects.create(
            farm=farm,
            animal=goats[name],
            vaccine=ppr,
            vaccine_name="PPR vaccine",
            disease_category="ppr",
            date=dt.date(2026, 11, 6),
            dosage="1 ml",
            route="sc",
            administered_by="James Kiprop",
            vet_officer=VET,
            batch_number="PPR-2611",
            **by,
        )
        health.after_save(v, True)
    for name in ("Simba", "Neema", "Zawadi", "Upendo", "Rehema"):
        v = Vaccination.objects.create(
            farm=farm,
            animal=goats[name],
            vaccine=ccpp,
            vaccine_name="CCPP vaccine",
            disease_category="ccpp",
            date=today - dt.timedelta(days=330),
            dosage="1 ml",
            route="sc",
            administered_by="Peter Otieno",
            vet_officer=VET,
            next_due_date=dt.date(2026, 11, 27),
            **by,
        )
        health.after_save(v, True)
    for name in ("Bahati", "Shujaa", "Kito", "Asali"):
        d = Deworming.objects.create(
            farm=farm,
            animal=goats[name],
            product=albendazole,
            product_name="Albendazole",
            dosage="1 ml / 10 kg",
            date=dt.date(2026, 11, 13),
            administered_by="Mary Achieng",
            next_due_date=dt.date(2027, 2, 13),
            **by,
        )
        health.after_save(d, True)
    t = Treatment.objects.create(
        farm=farm,
        animal=goats["Furaha"],
        date=today - dt.timedelta(days=3),
        diagnosis="Pneumonia",
        symptoms="Coughing, nasal discharge",
        treatment="Antibiotic course, 5 days",
        medication=oxytet,
        medication_name="Oxytetracycline LA",
        dosage="4 ml",
        route="im",
        responsible_person="Peter Otieno",
        vet_officer=VET,
        follow_up_date=dt.date(2026, 11, 25),
        status="ongoing",
        withdrawal_until=today + dt.timedelta(days=25),
        **by,
    )
    health.after_save(t, True)
    Animal.objects.filter(pk=goats["Furaha"].pk).update(health_status="under_treatment")
    HealthObservation.objects.create(
        farm=farm,
        animal=goats["Tumaini"],
        date=today - dt.timedelta(days=1),
        observed_by="Peter Otieno",
        symptoms="Off feed, dull, diarrhoea",
        temperature_c=Decimal("40.6"),
        severity="severe",
        suspected_disease="Coccidiosis",
        action_taken="Moved to the isolation pen; vet called",
        **by,
    )
    HealthObservation.objects.create(
        farm=farm,
        animal=goats["Rehema"],
        date=today - dt.timedelta(days=4),
        observed_by="Mary Achieng",
        symptoms="Slight limp, front left",
        severity="mild",
        action_taken="Watching; hoof checked",
        **by,
    )
    HealthObservation.objects.create(
        farm=farm,
        animal=goats["Jabari"],
        date=today - dt.timedelta(days=6),
        observed_by="Grace Wanjiru",
        symptoms="New arrival – routine quarantine",
        severity="mild",
        action_taken="Quarantine 21 days",
        **by,
    )
    visit = VetVisit.objects.create(
        farm=farm,
        date=dt.date(2026, 11, 11),
        vet_name=VET,
        reason="Monthly herd check",
        findings="Herd in good condition. One case of pneumonia (Furaha). Pregnant does doing well.",
        recommendations="Finish Furaha's antibiotic course; CCPP vaccination for adults by 27 Nov.",
        next_visit_date=dt.date(2026, 12, 9),
        cost_cents=15_000_000,
        **by,
    )
    visit.animals.set([goats["Furaha"], goats["Neema"], goats["Zawadi"]])
    health.after_save(visit, True)

    # Feed: purchases, then daily feeding.
    items = {i.name: i for i in FeedItem.objects.all()}
    prices = {
        "Rhodes grass hay": 1_200_000,
        "Dairy meal": 250_000,
        "Maize germ": 120_000,
        "Mineral lick": 1_500_000,
    }
    for name, amount in (
        ("Rhodes grass hay", 60),
        ("Dairy meal", 200),
        ("Maize germ", 150),
        ("Mineral lick", 6),
    ):
        item = items.get(name)
        if item:
            nutrition.add_movement(
                item,
                MovementKind.PURCHASE,
                Decimal(amount),
                daniel,
                date=today - dt.timedelta(days=21),
                unit_cost_cents=prices[name],
                supplier="Mbarara Agro Supplies",
            )
    hay, meal = items.get("Rhodes grass hay"), items.get("Dairy meal")
    for days_ago in range(14, 0, -1):
        for item, qty in ((hay, Decimal("3")), (meal, Decimal("10"))):
            if item is None:
                continue
            rec = FeedingRecord.objects.create(
                farm=farm,
                date=today - dt.timedelta(days=days_ago),
                feed_item=item,
                quantity=qty,
                location=locations.get("Main Paddock"),
                animals_fed=15,
                responsible="Peter Otieno",
                created_by=peter,
                updated_by=peter,
            )
            nutrition.save_usage(rec, item, qty, peter)

    # November 2026 activities and the 2027 calendar.
    for day, title, cat, priority, who, status in NOVEMBER:
        when = dt.date(2026, 11, day)
        if status in ("pending", "in_progress") and when < today:
            status = "overdue"
        act = Activity.objects.create(
            farm=farm,
            title=title,
            category=cal.category(farm.pk, cat),
            date=when,
            priority=priority,
            assigned_to=people[who],
            status=status,
            reminder_days=[1],
            completed_at=(
                timezone.make_aware(dt.datetime.combine(when, dt.time(10)))
                if status == "completed"
                else None
            ),
            completed_by=people[who] if status == "completed" else None,
            **by,
        )
        if cat == "treatment":
            act.animals.set([goats["Furaha"]])
    cal.apply_template(farm, "health-calendar-2027", daniel)

    # A few notifications so the bell has something to show.
    for user in (daniel, grace):
        notify(
            user,
            farm,
            "health.alert",
            title="Health alert: YPA-008",
            message="Severe – off feed, dull, diarrhoea (temperature 40.6 °C)",
            link=f"/livestock/{goats['Tumaini'].pk}",
            urgent=True,
            force_channels=["in_app"],
        )
        notify(
            user,
            farm,
            "feed.low_stock",
            title="Low stock: Dairy meal",
            message="Dairy meal is getting low. Reorder soon.",
            link="/nutrition",
            force_channels=["in_app"],
        )
    for user in (peter, mary):
        notify(
            user,
            farm,
            "task.assigned",
            title="New task: Dip the herd (tick control)",
            message="Grace Wanjiru assigned you Dip the herd for 26 Nov 2026.",
            link="/activities",
            force_channels=["in_app"],
        )
