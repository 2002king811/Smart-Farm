"""Starter feed items for farms created before phase 5."""

import uuid
from decimal import Decimal

from django.db import migrations

ITEMS = [
    ("Rhodes grass hay", "forage", "bale", Decimal("10")),
    ("Dairy meal", "concentrate", "kg", Decimal("50")),
    ("Maize germ", "concentrate", "kg", Decimal("50")),
    ("Mineral lick", "mineral", "block", Decimal("2")),
]


def seed(apps, schema_editor):
    Farm = apps.get_model("accounts", "Farm")
    FeedItem = apps.get_model("nutrition", "FeedItem")
    for farm in Farm.objects.all():
        if not FeedItem.objects.filter(farm=farm).exists():
            FeedItem.objects.bulk_create(
                FeedItem(id=uuid.uuid4(), farm=farm, name=n, category=c, unit=u, reorder_level=r) for n, c, u, r in ITEMS
            )


class Migration(migrations.Migration):
    dependencies = [("nutrition", "0001_initial"), ("accounts", "0002_phase2_accounts")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
