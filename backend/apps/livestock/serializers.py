from __future__ import annotations

from datetime import date
from typing import Any

from django.utils import timezone
from rest_framework import serializers

from apps.accounts.serializers import FileUrlField
from apps.core.serializers import FarmScopedModelSerializer

from . import services
from .models import (
    Animal,
    AnimalGroup,
    AnimalPhoto,
    ExitReason,
    Location,
    Sex,
    WeightRecord,
)


class LocationSerializer(FarmScopedModelSerializer):
    animal_count = serializers.IntegerField(read_only=True, default=0)

    class Meta(FarmScopedModelSerializer.Meta):
        model = Location
        fields = ("id", "name", "type", "capacity", "description", "animal_count")

    def validate_name(self, value: str) -> str:
        qs = Location.objects.filter(name__iexact=value.strip())
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A location with this name already exists.")
        return value.strip()


class AnimalGroupSerializer(FarmScopedModelSerializer):
    animal_count = serializers.IntegerField(read_only=True, default=0)

    class Meta(FarmScopedModelSerializer.Meta):
        model = AnimalGroup
        fields = ("id", "name", "description", "animal_count")

    def validate_name(self, value: str) -> str:
        qs = AnimalGroup.objects.filter(name__iexact=value.strip())
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A group with this name already exists.")
        return value.strip()


class NamedRefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()


class AnimalRefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Animal
        fields = ("id", "animal_id", "name", "sex")


class AnimalListSerializer(serializers.ModelSerializer):
    age_months = serializers.SerializerMethodField()
    is_kid = serializers.BooleanField(read_only=True)
    location = NamedRefSerializer(read_only=True, allow_null=True)
    group = NamedRefSerializer(read_only=True, allow_null=True)
    latest_weight_kg = serializers.DecimalField(
        max_digits=6, decimal_places=2, read_only=True, allow_null=True
    )
    latest_weight_date = serializers.DateField(read_only=True, allow_null=True)
    thumbnail = serializers.SerializerMethodField()

    class Meta:
        model = Animal
        fields: tuple[str, ...] = (
            "id",
            "animal_id",
            "ear_tag",
            "name",
            "species",
            "breed",
            "sex",
            "date_of_birth",
            "dob_estimated",
            "age_months",
            "is_kid",
            "health_status",
            "breeding_status",
            "location",
            "group",
            "latest_weight_kg",
            "latest_weight_date",
            "thumbnail",
            "is_active",
            "exit_reason",
        )

    def get_age_months(self, obj: Animal) -> int | None:
        return obj.age_in_months()

    def get_thumbnail(self, obj: Animal) -> str | None:
        name = getattr(obj, "primary_thumb", None)
        if not name:
            return None
        return AnimalPhoto._meta.get_field("thumbnail").storage.url(name)  # type: ignore[attr-defined]


class AnimalDetailSerializer(AnimalListSerializer):
    dam = AnimalRefSerializer(read_only=True, allow_null=True)
    sire = AnimalRefSerializer(read_only=True, allow_null=True)
    offspring_count = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()
    withdrawal_until = serializers.SerializerMethodField(
        help_text="Do not sell or milk until this date (from treatments and vaccinations)"
    )

    class Meta(AnimalListSerializer.Meta):
        fields = (
            *AnimalListSerializer.Meta.fields,
            "acquisition_date",
            "acquisition_source",
            "acquisition_details",
            "dam",
            "sire",
            "sire_details",
            "colour_markings",
            "current_condition",
            "previous_history",
            "remarks",
            "exit_date",
            "exit_notes",
            "offspring_count",
            "created_at",
            "created_by_name",
            "updated_at",
            "withdrawal_until",
        )

    def get_withdrawal_until(self, obj: Animal) -> date | None:
        from apps.health.services import withdrawal_until

        return withdrawal_until(obj)

    def get_offspring_count(self, obj: Animal) -> int:
        related = obj.offspring_as_dam if obj.sex == Sex.FEMALE else obj.offspring_as_sire
        return related.filter(deleted_at__isnull=True).count()

    def get_created_by_name(self, obj: Animal) -> str | None:
        return obj.created_by.full_name if obj.created_by else None


class AnimalWriteSerializer(FarmScopedModelSerializer):
    estimated_age_months = serializers.IntegerField(
        write_only=True,
        required=False,
        allow_null=True,
        min_value=0,
        max_value=360,
        help_text="Use when the exact birth date is unknown.",
    )

    class Meta(FarmScopedModelSerializer.Meta):
        model = Animal
        fields = (
            "id",
            "animal_id",
            "ear_tag",
            "name",
            "species",
            "breed",
            "sex",
            "date_of_birth",
            "estimated_age_months",
            "acquisition_date",
            "acquisition_source",
            "acquisition_details",
            "health_status",
            "breeding_status",
            "dam",
            "sire",
            "sire_details",
            "location",
            "group",
            "colour_markings",
            "current_condition",
            "previous_history",
            "remarks",
        )
        # Uniqueness per farm is checked in validate() with friendly messages.
        validators: list[Any] = []

    def validate_animal_id(self, value: str) -> str:
        value = value.strip().upper()
        if not value:
            raise serializers.ValidationError("Enter an animal ID.")
        qs = Animal.objects.filter(animal_id__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("This animal ID is already used on this farm.")
        return value

    def validate_ear_tag(self, value: str) -> str:
        value = value.strip().upper()
        if value:
            qs = Animal.objects.filter(ear_tag__iexact=value)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError("This ear tag is already used on this farm.")
        return value

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        today = timezone.localdate()
        errors: dict[str, str] = {}

        def current(field: str) -> Any:
            if field in attrs:
                return attrs[field]
            if self.instance is not None:
                return getattr(self.instance, field, None)
            default = Animal._meta.get_field(field).get_default()  # type: ignore[union-attr]
            return default if default != "" else None

        months = attrs.pop("estimated_age_months", None)
        if months is not None:
            if attrs.get("date_of_birth"):
                errors["estimated_age_months"] = "Give a birth date or an estimated age, not both."
            else:
                attrs["date_of_birth"] = services.months_before(today, months)
                attrs["dob_estimated"] = True
        elif "date_of_birth" in attrs:
            attrs["dob_estimated"] = False

        dob = current("date_of_birth")
        if dob and dob > today:
            errors["date_of_birth"] = "The birth date cannot be in the future."
        acquired = current("acquisition_date")
        if acquired and acquired > today:
            errors["acquisition_date"] = "The date cannot be in the future."
        if acquired and dob and acquired < dob and not attrs.get("dob_estimated"):
            errors["acquisition_date"] = "The animal cannot be acquired before it was born."

        species = current("species")
        for field, sex, label in (
            ("dam", Sex.FEMALE, "dam (mother)"),
            ("sire", Sex.MALE, "sire (father)"),
        ):
            parent = attrs.get(field)
            if parent is None:
                continue
            if self.instance and parent.pk == self.instance.pk:
                errors[field] = "An animal cannot be its own parent."
            elif parent.sex != sex:
                errors[field] = f"The {label} must be {sex}."
            elif species and parent.species != species:
                errors[field] = "The parent must be the same species."
            elif dob and parent.date_of_birth and parent.date_of_birth >= dob:
                errors[field] = "The parent must be older than the animal."
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


class WeightRecordSerializer(FarmScopedModelSerializer):
    recorded_by = serializers.SerializerMethodField()
    gain_kg = serializers.SerializerMethodField()

    class Meta(FarmScopedModelSerializer.Meta):
        model = WeightRecord
        fields = (
            "id",
            "animal",
            "date",
            "weight_kg",
            "body_condition_score",
            "notes",
            "recorded_by",
            "gain_kg",
            "created_at",
        )
        read_only_fields = ("id", "animal", "created_at")

    def get_recorded_by(self, obj: WeightRecord) -> str | None:
        return obj.created_by.full_name if obj.created_by else None

    def get_gain_kg(self, obj: WeightRecord) -> str | None:
        previous = self.context.get("previous", {}).get(obj.pk)
        return f"{obj.weight_kg - previous:.2f}" if previous is not None else None

    def validate_date(self, value: Any) -> Any:
        if value > timezone.localdate():
            raise serializers.ValidationError("The date cannot be in the future.")
        return value


class AnimalPhotoSerializer(serializers.ModelSerializer):
    file = FileUrlField()
    thumbnail = FileUrlField()

    class Meta:
        model = AnimalPhoto
        fields = ("id", "animal", "file", "thumbnail", "is_primary", "caption", "created_at")
        read_only_fields = fields


class PhotoUploadSerializer(serializers.Serializer):
    file = serializers.ImageField()
    caption = serializers.CharField(max_length=120, required=False, allow_blank=True)
    is_primary = serializers.BooleanField(required=False, default=False)


class ExitSerializer(serializers.Serializer):
    reason = serializers.ChoiceField(choices=ExitReason.choices)
    date = serializers.DateField(default=timezone.localdate)
    notes = serializers.CharField(max_length=200, required=False, allow_blank=True)

    def validate_date(self, value: Any) -> Any:
        if value > timezone.localdate():
            raise serializers.ValidationError("The date cannot be in the future.")
        return value


class SummarySerializer(serializers.Serializer):
    total = serializers.IntegerField()
    males = serializers.IntegerField()
    females = serializers.IntegerField()
    kids = serializers.IntegerField()
    needing_attention = serializers.IntegerField()
    pregnant = serializers.IntegerField()
    inactive = serializers.IntegerField()


class NextIdSerializer(serializers.Serializer):
    animal_id = serializers.CharField()


class TimelineEventSerializer(serializers.Serializer):
    at = serializers.DateTimeField()
    kind = serializers.CharField()
    title = serializers.CharField()
    detail = serializers.CharField()
    by = serializers.CharField(allow_null=True)
