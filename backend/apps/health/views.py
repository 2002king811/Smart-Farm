from __future__ import annotations

from datetime import timedelta
from typing import Any

import django_filters
from django.db import transaction
from django.db.models import Count, QuerySet
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from apps.calendar.models import Activity, ActivityStatus, CategoryKey
from apps.core.views import FarmScopedAPIView, FarmScopedViewSet
from apps.livestock.models import Animal

from . import serializers as s
from . import services
from .models import (
    Deworming,
    HealthInspection,
    HealthObservation,
    Medicine,
    ParasiteControl,
    Treatment,
    TreatmentStatus,
    Vaccination,
    Vaccine,
    VetVisit,
)


class DateRangeFilter(django_filters.FilterSet):
    date_from = django_filters.DateFilter(field_name="date", lookup_expr="gte", label="from")
    date_to = django_filters.DateFilter(field_name="date", lookup_expr="lte", label="to")


def filterset_for(model: Any, extra: tuple[str, ...]) -> type[django_filters.FilterSet]:
    meta = type("Meta", (), {"model": model, "fields": list(extra)})
    return type(f"{model.__name__}Filter", (DateRangeFilter,), {"Meta": meta})


class HealthRecordViewSet(FarmScopedViewSet):
    """Attendants view and record (no delete). Saving keeps the linked calendar activity and the
    animal's health status in step."""

    permission_module = "health"
    ordering = ("-date", "-created_at")
    ordering_fields = ("date", "created_at")
    related: tuple[str, ...] = ()
    prefetch: tuple[str, ...] = ()

    def get_queryset(self) -> QuerySet:
        return (
            super()
            .get_queryset()
            .select_related("created_by", *self.related)
            .prefetch_related(*self.prefetch)
        )

    @transaction.atomic
    def perform_create(self, serializer: Any) -> None:
        super().perform_create(serializer)
        services.after_save(serializer.instance, created=True)

    @transaction.atomic
    def perform_update(self, serializer: Any) -> None:
        super().perform_update(serializer)
        services.after_save(serializer.instance, created=False)

    @transaction.atomic
    def perform_destroy(self, instance: Any) -> None:
        instance.delete()
        services.after_delete(instance)


class VaccinationViewSet(HealthRecordViewSet):
    model = Vaccination
    serializer_class = s.VaccinationSerializer
    filterset_class = filterset_for(Vaccination, ("animal", "group", "disease_category", "status"))
    search_fields = (
        "vaccine__name",
        "vaccine_name",
        "batch_number",
        "animal__animal_id",
        "animal__name",
    )
    related = ("animal", "group", "vaccine")


class DewormingViewSet(HealthRecordViewSet):
    model = Deworming
    serializer_class = s.DewormingSerializer
    filterset_class = filterset_for(Deworming, ("animal", "group", "status"))
    search_fields = ("product__name", "product_name", "animal__animal_id", "animal__name")
    related = ("animal", "group", "product")


class TreatmentViewSet(HealthRecordViewSet):
    model = Treatment
    serializer_class = s.TreatmentSerializer
    filterset_class = filterset_for(Treatment, ("animal", "status"))
    search_fields = (
        "diagnosis",
        "medication__name",
        "medication_name",
        "animal__animal_id",
        "animal__name",
    )
    related = ("animal", "medication")
    action_permissions = {"resolve": "update"}

    @extend_schema(request=s.ResolveSerializer, responses=s.TreatmentSerializer)
    @action(detail=True, methods=["post"])
    def resolve(self, request: Request, pk: str | None = None) -> Response:
        treatment = self.get_object()
        body = s.ResolveSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        serializer = s.TreatmentSerializer(
            treatment,
            data={
                "status": TreatmentStatus.RESOLVED,
                **body.validated_data,
                **(
                    {"notes": f"{treatment.notes}\n{body.validated_data['notes']}".strip()}
                    if body.validated_data.get("notes")
                    else {}
                ),
            },
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(s.TreatmentSerializer(serializer.instance).data)


class VetVisitViewSet(HealthRecordViewSet):
    model = VetVisit
    serializer_class = s.VetVisitSerializer
    filterset_class = filterset_for(VetVisit, ("animals",))
    search_fields = ("vet_name", "reason", "findings")
    prefetch = ("animals",)


class HealthObservationViewSet(HealthRecordViewSet):
    model = HealthObservation
    serializer_class = s.HealthObservationSerializer
    filterset_class = filterset_for(HealthObservation, ("animal", "severity"))
    search_fields = ("symptoms", "suspected_disease", "animal__animal_id", "animal__name")
    related = ("animal",)


class HealthInspectionViewSet(HealthRecordViewSet):
    model = HealthInspection
    serializer_class = s.HealthInspectionSerializer
    filterset_class = filterset_for(HealthInspection, ("result", "group"))
    search_fields = ("inspector", "findings")
    related = ("group",)
    prefetch = ("animals",)


class ParasiteControlViewSet(HealthRecordViewSet):
    model = ParasiteControl
    serializer_class = s.ParasiteControlSerializer
    filterset_class = filterset_for(ParasiteControl, ("method", "group"))
    search_fields = ("target", "product__name", "product_name")
    related = ("group", "product")
    prefetch = ("animals",)


class _CatalogViewSet(FarmScopedViewSet):
    permission_module = "health"
    pagination_class = None
    ordering = ("name",)
    search_fields = ("name",)
    # Everyone picks from the lists; managers maintain them.
    action_permissions = {
        "create": "manage",
        "update": "manage",
        "partial_update": "manage",
        "destroy": "manage",
    }


class VaccineViewSet(_CatalogViewSet):
    model = Vaccine
    serializer_class = s.VaccineSerializer


class MedicineViewSet(_CatalogViewSet):
    model = Medicine
    serializer_class = s.MedicineSerializer
    filterset_fields = ("type",)


class HealthSummaryView(FarmScopedAPIView):
    permission_module = "health"

    @extend_schema(responses=s.HealthSummarySerializer)
    def get(self, request: Request) -> Response:
        today = timezone.localdate()
        animals = Animal.objects.filter(is_active=True)
        counts = dict(animals.values_list("health_status").annotate(n=Count("pk")))
        withdrawal = (
            Treatment.objects.filter(withdrawal_until__gte=today, animal__is_active=True)
            .values("animal")
            .distinct()
            .count()
        )
        return Response(
            {
                "status_counts": counts,
                "ongoing_treatments": Treatment.objects.filter(
                    status=TreatmentStatus.ONGOING
                ).count(),
                "under_withdrawal": withdrawal,
                "vaccinations_due_30_days": Activity.objects.filter(
                    category__key=CategoryKey.VACCINATION,
                    date__range=(today, today + timedelta(days=30)),
                    status__in=[ActivityStatus.PENDING, ActivityStatus.IN_PROGRESS],
                ).count(),
                "overdue_health_activities": Activity.objects.filter(
                    status=ActivityStatus.OVERDUE,
                    category__key__in=[
                        CategoryKey.VACCINATION,
                        CategoryKey.DEWORMING,
                        CategoryKey.PARASITE_CONTROL,
                        CategoryKey.TREATMENT,
                        CategoryKey.VET_VISIT,
                        CategoryKey.INSPECTION,
                    ],
                ).count(),
                "observations_7_days": HealthObservation.objects.filter(
                    date__gte=today - timedelta(days=7)
                ).count(),
            }
        )
