from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any

from django.utils import timezone
from rest_framework import serializers

from apps.health.serializers import HealthRecordSerializer
from apps.livestock.models import Animal, Sex

from . import services
from .models import GESTATION_DAYS, Birth, Mating, MatingStatus, Mortality, PregnancyStatus


def _label(animal: Animal | None) -> str | None:
    return f"{animal.animal_id} {animal.name}".strip() if animal else None


class MatingSerializer(HealthRecordSerializer):
    doe_label = serializers.SerializerMethodField()
    buck_label = serializers.SerializerMethodField()
    progress = serializers.SerializerMethodField()

    class Meta(HealthRecordSerializer.Meta):
        model = Mating
        fields = (
            "id",
            "doe",
            "doe_label",
            "buck",
            "buck_label",
            "ai_straw",
            "date",
            "method",
            "pregnancy_status",
            "scan_date",
            "expected_kidding_date",
            "actual_kidding_date",
            "kids_count",
            "status",
            "notes",
            "progress",
            "recorded_by",
            "created_at",
        )
        read_only_fields = ("id", "actual_kidding_date", "kids_count", "created_at")

    def get_doe_label(self, obj: Mating) -> str | None:
        return _label(obj.doe)

    def get_buck_label(self, obj: Mating) -> str:
        return _label(obj.buck) or (f"AI: {obj.ai_straw}" if obj.ai_straw else "—")

    def get_progress(self, obj: Mating) -> dict[str, int] | None:
        if (
            obj.status != MatingStatus.ACTIVE
            or obj.pregnancy_status == PregnancyStatus.NOT_PREGNANT
        ):
            return None
        return services.pregnancy_progress(obj)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        attrs = super().validate(attrs)

        def current(field: str) -> Any:
            return attrs[field] if field in attrs else getattr(self.instance, field, None)

        doe, buck = current("doe"), current("buck")
        if doe is None:
            raise serializers.ValidationError({"doe": ["Choose the doe."]})
        if "doe" in attrs or "buck" in attrs or "ai_straw" in attrs:
            services.validate_pair(doe, buck, current("ai_straw") or "")
        if (
            self.instance is None
            and Mating.objects.filter(doe=doe, status=MatingStatus.ACTIVE).exists()
        ):
            raise serializers.ValidationError(
                {
                    "doe": [
                        "This doe already has an open mating. Record its scan result or birth first."
                    ]
                }
            )
        expected = current("expected_kidding_date")
        if expected and expected <= current("date"):
            raise serializers.ValidationError(
                {"expected_kidding_date": ["It must be after the mating date."]}
            )
        if "date" in attrs and "expected_kidding_date" not in attrs and self.instance is not None:
            # Moving the mating date moves the default expected date with it.
            attrs["expected_kidding_date"] = attrs["date"] + timedelta(days=GESTATION_DAYS)
        return attrs


class ScanSerializer(serializers.Serializer):
    result = serializers.ChoiceField(
        choices=[PregnancyStatus.CONFIRMED, PregnancyStatus.NOT_PREGNANT]
    )
    scan_date = serializers.DateField(default=timezone.localdate)


class PregnancySerializer(serializers.Serializer):
    mating_id = serializers.UUIDField()
    doe = serializers.UUIDField()
    doe_label = serializers.CharField()
    buck_label = serializers.CharField()
    mating_date = serializers.DateField()
    pregnancy_status = serializers.CharField()
    expected_kidding_date = serializers.DateField()
    days_pregnant = serializers.IntegerField()
    days_remaining = serializers.IntegerField()
    progress_percent = serializers.IntegerField()
    trimester = serializers.IntegerField()


class KidInputSerializer(serializers.Serializer):
    sex = serializers.ChoiceField(choices=Sex.choices)
    name = serializers.CharField(max_length=80, required=False, allow_blank=True)
    animal_id = serializers.CharField(max_length=30, required=False, allow_blank=True)
    ear_tag = serializers.CharField(max_length=30, required=False, allow_blank=True)
    birth_weight_kg = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        required=False,
        allow_null=True,
        min_value=Decimal("0.1"),
        max_value=Decimal("50"),
    )
    alive = serializers.BooleanField(default=True)
    colour = serializers.CharField(max_length=120, required=False, allow_blank=True)


class KidRefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Animal
        fields = ("id", "animal_id", "name", "sex")


class BirthSerializer(HealthRecordSerializer):
    dam_label = serializers.SerializerMethodField()
    sire_label = serializers.SerializerMethodField()
    kids = KidRefSerializer(many=True, read_only=True)

    class Meta(HealthRecordSerializer.Meta):
        model = Birth
        fields = (
            "id",
            "mating",
            "dam",
            "dam_label",
            "sire",
            "sire_label",
            "date",
            "birth_type",
            "condition",
            "kids",
            "stillborn_count",
            "notes",
            "recorded_by",
            "created_at",
        )
        read_only_fields = (
            "id",
            "mating",
            "dam",
            "sire",
            "date",
            "kids",
            "stillborn_count",
            "created_at",
        )

    def get_dam_label(self, obj: Birth) -> str | None:
        return _label(obj.dam)

    def get_sire_label(self, obj: Birth) -> str | None:
        return _label(obj.sire)


class BirthCreateSerializer(HealthRecordSerializer):
    kids = KidInputSerializer(many=True, write_only=True)

    class Meta(HealthRecordSerializer.Meta):
        model = Birth
        fields = ("id", "mating", "dam", "sire", "date", "birth_type", "condition", "notes", "kids")
        extra_kwargs = {"birth_type": {"required": False}, "condition": {"required": False}}

    def validate_kids(self, value: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not value:
            raise serializers.ValidationError("Add at least one kid.")
        if len(value) > 6:
            raise serializers.ValidationError("A birth can have at most 6 kids.")
        ids = [k["animal_id"].strip().upper() for k in value if k.get("animal_id")]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError("Each kid needs its own animal ID.")
        return value


class KidSerializer(serializers.ModelSerializer):
    age_days = serializers.SerializerMethodField()
    dam_label = serializers.SerializerMethodField()
    growth = serializers.SerializerMethodField()

    class Meta:
        model = Animal
        fields = (
            "id",
            "animal_id",
            "name",
            "sex",
            "date_of_birth",
            "age_days",
            "dam",
            "dam_label",
            "health_status",
            "growth",
        )

    def get_age_days(self, obj: Animal) -> int | None:
        return (timezone.localdate() - obj.date_of_birth).days if obj.date_of_birth else None

    def get_dam_label(self, obj: Animal) -> str | None:
        return _label(obj.dam)

    def get_growth(self, obj: Animal) -> dict[str, Any]:
        return services.kid_growth(obj)


class MortalitySerializer(HealthRecordSerializer):
    class Meta(HealthRecordSerializer.Meta):
        model = Mortality
        # "recorded_by" (from the base) is who entered it.
        fields = (
            *HealthRecordSerializer.Meta.fields,
            "animal",
            "age_at_death_months",
            "cause_category",
            "cause",
            "disposal",
        )
        read_only_fields = ("id", "age_at_death_months", "created_at")
        # Our own check below gives a clearer message than the one-to-one uniqueness check.
        extra_kwargs: dict[str, Any] = {"animal": {"validators": []}}

    def validate_animal(self, animal: Animal) -> Animal:
        if self.instance is None and not animal.is_active:
            raise serializers.ValidationError("This animal is no longer in the herd.")
        return animal
