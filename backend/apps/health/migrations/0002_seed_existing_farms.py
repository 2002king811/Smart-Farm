"""Starter vaccine and medicine lists, and the 8 activity categories, for farms created before
phase 4."""

import uuid

from django.db import migrations

VACCINES = [
    ("Enterotoxaemia (Clostridial) vaccine", "clostridial", "sc", "2 ml", 21, 365),
    ("PPR vaccine", "ppr", "sc", "1 ml", 21, 1095),
    ("Goat pox vaccine", "goat_pox", "sc", "1 ml", 21, 365),
    ("Brucella Rev-1 vaccine", "brucellosis", "sc", "1 ml", 21, None),
    ("Anthrax spore vaccine", "anthrax", "sc", "1 ml", 42, 365),
    ("CCPP vaccine", "ccpp", "sc", "1 ml", 21, 365),
    ("FMD vaccine", "fmd", "sc", "2 ml", 21, 180),
]
MEDICINES = [
    ("Albendazole", "dewormer", "oral", "1 ml / 10 kg", 10),
    ("Ivermectin", "dewormer", "sc", "1 ml / 50 kg", 35),
    ("Levamisole", "dewormer", "oral", "1 ml / 10 kg", 10),
    ("Oxytetracycline LA", "antibiotic", "im", "1 ml / 10 kg", 28),
    ("Penicillin-Streptomycin", "antibiotic", "im", "1 ml / 25 kg", 30),
    ("Flunixin", "anti_inflammatory", "im", "1 ml / 45 kg", 10),
    ("Multivitamin injection", "vitamin", "im", "2 ml", 0),
    ("Amitraz (acaricide)", "acaricide", "topical", "2 ml / litre", 7),
]
CATEGORIES = [
    ("vaccination", "Vaccination", "#2E7D32", "syringe"),
    ("deworming", "Deworming", "#6A1B9A", "bug"),
    ("parasite_control", "Parasite Control", "#00838F", "shield"),
    ("treatment", "Treatment", "#C62828", "pill"),
    ("vet_visit", "Vet Visit", "#1565C0", "stethoscope"),
    ("inspection", "Health Inspection", "#455A64", "clipboard-check"),
    ("breeding", "Breeding", "#AD1457", "heart"),
    ("feeding", "Feeding & Nutrition", "#EF6C00", "wheat"),
]


def seed(apps, schema_editor):
    Farm = apps.get_model("accounts", "Farm")
    Vaccine = apps.get_model("health", "Vaccine")
    Medicine = apps.get_model("health", "Medicine")
    Category = apps.get_model("calendar", "ActivityCategory")
    for farm in Farm.objects.all():
        if not Vaccine.objects.filter(farm=farm).exists():
            Vaccine.objects.bulk_create(
                Vaccine(id=uuid.uuid4(), farm=farm, name=n, disease_category=d, route=r, default_dose=dose,
                        withdrawal_days=w, booster_interval_days=b)
                for n, d, r, dose, w, b in VACCINES
            )
        if not Medicine.objects.filter(farm=farm).exists():
            Medicine.objects.bulk_create(
                Medicine(id=uuid.uuid4(), farm=farm, name=n, type=t, route=r, default_dose=dose, withdrawal_days=w)
                for n, t, r, dose, w in MEDICINES
            )
        if not Category.objects.filter(farm=farm).exists():
            Category.objects.bulk_create(
                Category(id=uuid.uuid4(), farm=farm, key=k, name=n, colour=c, icon=i) for k, n, c, i in CATEGORIES
            )


class Migration(migrations.Migration):
    dependencies = [("health", "0001_initial"), ("calendar", "0001_initial"), ("accounts", "0002_phase2_accounts")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
