"""Give farms created before phase 3 the default locations and groups."""

import uuid

from django.db import migrations

LOCATIONS = [
    ("Main Paddock", "paddock", "Daytime grazing"),
    ("Night Pen", "pen", "Night housing"),
    ("Kid Pen", "pen", "Kids and their dams"),
    ("Isolation Pen", "isolation", "Sick animals"),
    ("Quarantine Pen", "quarantine", "New arrivals and suspected disease"),
]
GROUPS = [
    ("Breeding Does", "Females for breeding"),
    ("Bucks", "Breeding males"),
    ("Kids", "Under 6 months"),
    ("Growers", "Young stock 6–12 months"),
]


def seed(apps, schema_editor):
    Farm = apps.get_model("accounts", "Farm")
    Location = apps.get_model("livestock", "Location")
    Group = apps.get_model("livestock", "AnimalGroup")
    for farm in Farm.objects.all():
        if not Location.objects.filter(farm=farm).exists():
            Location.objects.bulk_create(
                Location(id=uuid.uuid4(), farm=farm, name=n, type=t, description=d) for n, t, d in LOCATIONS
            )
        if not Group.objects.filter(farm=farm).exists():
            Group.objects.bulk_create(
                Group(id=uuid.uuid4(), farm=farm, name=n, description=d) for n, d in GROUPS
            )


class Migration(migrations.Migration):
    dependencies = [("livestock", "0001_initial"), ("accounts", "0002_phase2_accounts")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
