from __future__ import annotations

from typing import Any

from django.utils import timezone
from rest_framework import serializers

from apps.core.serializers import FarmScopedModelSerializer, FarmScopedRelatedField
from apps.livestock.models import Animal

from . import services
from .models import (
    Deworming,
    HealthInspection,
    HealthObservation,
    Medicine,
    ParasiteControl,
    Treatment,
    Vaccination,
    Vaccine,
    VetVisit,
)


class VaccineSerializer(FarmScopedModelSerializer):
    class Meta(FarmScopedModelSerializer.Meta):
        model = Vaccine
        fields = (
            "id",
            "name",
            "disease_category",
            "manufacturer",
            "default_dose",
            "route",
            "withdrawal_days",
            "booster_interval_days",
        )


class MedicineSerializer(FarmScopedModelSerializer):
    class Meta(FarmScopedModelSerializer.Meta):
        model = Medicine
        fields = ("id", "name", "type", "manufacturer", "default_dose", "route", "withdrawal_days")


class HealthRecordSerializer(FarmScopedModelSerializer):
    """Shared behaviour: subject labels, who recorded it, and date checks."""

    animal_label = serializers.SerializerMethodField()
    group_label = serializers.SerializerMethodField()
    recorded_by = serializers.SerializerMethodField()

    class Meta(FarmScopedModelSerializer.Meta):
        fields: tuple[str, ...] = (
            "id",
            "date",
            "notes",
            "animal_label",
            "group_label",
            "recorded_by",
            "created_at",
        )

    def get_animal_label(self, obj: Any) -> str | None:
        animal = getattr(obj, "animal", None)
        return f"{animal.animal_id} {animal.name}".strip() if animal else None

    def get_group_label(self, obj: Any) -> str | None:
        group = getattr(obj, "group", None)
        return group.name if group else None

    def get_recorded_by(self, obj: Any) -> str | None:
        return obj.created_by.full_name if obj.created_by else None

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        errors: dict[str, str] = {}

        def current(field: str) -> Any:
            return attrs[field] if field in attrs else getattr(self.instance, field, None)

        day = current("date") or timezone.localdate()
        if day > timezone.localdate():
            errors["date"] = "Record what has happened: the date cannot be in the future."
        next_field = self.Meta.model.NEXT_DATE_FIELD
        if next_field and current(next_field) and current(next_field) <= day:
            errors[next_field] = "The next date must be after the record date."
        if (
            "animal" in self.fields
            and "group" in self.fields
            and current("animal")
            and current("group")
        ):
            errors["group"] = "Choose one animal or one group, not both."
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


class VaccinationSerializer(HealthRecordSerializer):
    vaccine_label = serializers.SerializerMethodField()

    class Meta(HealthRecordSerializer.Meta):
        model = Vaccination
        fields = (
            *HealthRecordSerializer.Meta.fields,
            "animal",
            "group",
            "vaccine",
            "vaccine_name",
            "vaccine_label",
            "disease_category",
            "batch_number",
            "dosage",
            "route",
            "administered_by",
            "vet_officer",
            "next_due_date",
            "status",
        )
        extra_kwargs = {"disease_category": {"required": False}}

    def get_vaccine_label(self, obj: Vaccination) -> str:
        return (
            obj.vaccine.name
            if obj.vaccine
            else (obj.vaccine_name or obj.get_disease_category_display())
        )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        attrs = super().validate(attrs)
        vaccine = attrs.get("vaccine")
        if vaccine:
            attrs.setdefault("disease_category", vaccine.disease_category)
            attrs.setdefault("route", vaccine.route)
            attrs.setdefault("dosage", vaccine.default_dose)
        if not self.instance and not attrs.get("disease_category"):
            raise serializers.ValidationError({"disease_category": ["Choose the disease."]})
        if not self.instance and not vaccine and not attrs.get("vaccine_name"):
            raise serializers.ValidationError({"vaccine": ["Choose a vaccine or type its name."]})
        return attrs


class DewormingSerializer(HealthRecordSerializer):
    product_label = serializers.SerializerMethodField()

    class Meta(HealthRecordSerializer.Meta):
        model = Deworming
        fields = (
            *HealthRecordSerializer.Meta.fields,
            "animal",
            "group",
            "product",
            "product_name",
            "product_label",
            "dosage",
            "administered_by",
            "next_due_date",
            "status",
        )

    def get_product_label(self, obj: Deworming) -> str:
        return obj.product.name if obj.product else obj.product_name

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        attrs = super().validate(attrs)
        if not self.instance and not attrs.get("product") and not attrs.get("product_name"):
            raise serializers.ValidationError(
                {"product": ["Choose the dewormer or type its name."]}
            )
        return attrs


class TreatmentSerializer(HealthRecordSerializer):
    medication_label = serializers.SerializerMethodField()

    class Meta(HealthRecordSerializer.Meta):
        model = Treatment
        fields = (
            *HealthRecordSerializer.Meta.fields,
            "animal",
            "diagnosis",
            "symptoms",
            "treatment",
            "medication",
            "medication_name",
            "medication_label",
            "dosage",
            "route",
            "responsible_person",
            "vet_officer",
            "follow_up_date",
            "status",
            "resolved_date",
            "withdrawal_until",
        )

    def get_medication_label(self, obj: Treatment) -> str:
        return obj.medication.name if obj.medication else obj.medication_name

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        attrs = services.prepare_treatment(super().validate(attrs), self.instance)
        resolved = attrs.get("resolved_date")
        day = attrs.get("date", getattr(self.instance, "date", None))
        if resolved and day and resolved < day:
            raise serializers.ValidationError(
                {"resolved_date": ["It cannot be resolved before it started."]}
            )
        return attrs


class ResolveSerializer(serializers.Serializer):
    resolved_date = serializers.DateField(default=timezone.localdate)
    notes = serializers.CharField(required=False, allow_blank=True)


class _ManyAnimals(HealthRecordSerializer):
    animals = FarmScopedRelatedField(many=True, queryset=Animal.objects.all(), required=False)
    animal_labels = serializers.SerializerMethodField()

    def get_animal_labels(self, obj: Any) -> list[str]:
        return [a.animal_id for a in obj.animals.all()]


class VetVisitSerializer(_ManyAnimals):
    class Meta(HealthRecordSerializer.Meta):
        model = VetVisit
        fields = (
            *HealthRecordSerializer.Meta.fields,
            "vet_name",
            "reason",
            "animals",
            "animal_labels",
            "findings",
            "recommendations",
            "next_visit_date",
            "cost_cents",
        )


class HealthObservationSerializer(HealthRecordSerializer):
    class Meta(HealthRecordSerializer.Meta):
        model = HealthObservation
        fields = (
            *HealthRecordSerializer.Meta.fields,
            "animal",
            "observed_by",
            "symptoms",
            "temperature_c",
            "severity",
            "suspected_disease",
            "action_taken",
        )


class HealthInspectionSerializer(_ManyAnimals):
    class Meta(HealthRecordSerializer.Meta):
        model = HealthInspection
        fields = (
            *HealthRecordSerializer.Meta.fields,
            "inspector",
            "animals",
            "animal_labels",
            "group",
            "animals_inspected",
            "findings",
            "score",
            "result",
            "next_inspection_date",
        )


class ParasiteControlSerializer(_ManyAnimals):
    product_label = serializers.SerializerMethodField()

    class Meta(HealthRecordSerializer.Meta):
        model = ParasiteControl
        fields = (
            *HealthRecordSerializer.Meta.fields,
            "method",
            "target",
            "product",
            "product_name",
            "product_label",
            "animals",
            "animal_labels",
            "group",
            "administered_by",
            "next_due_date",
        )

    def get_product_label(self, obj: ParasiteControl) -> str:
        return obj.product.name if obj.product else obj.product_name


class HealthSummarySerializer(serializers.Serializer):
    status_counts = serializers.DictField(child=serializers.IntegerField())
    ongoing_treatments = serializers.IntegerField()
    under_withdrawal = serializers.IntegerField()
    vaccinations_due_30_days = serializers.IntegerField()
    overdue_health_activities = serializers.IntegerField()
    observations_7_days = serializers.IntegerField()
