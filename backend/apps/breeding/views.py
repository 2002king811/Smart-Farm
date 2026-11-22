from __future__ import annotations

from typing import Any

from django.db import transaction
from django.db.models import QuerySet
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response

from apps.core.views import FarmContextMixin, FarmScopedAPIView, FarmScopedViewSet
from apps.health.views import filterset_for
from apps.livestock.models import Animal

from . import serializers as s
from . import services
from .models import Birth, Mating, MatingStatus, Mortality, PregnancyStatus

SNAPSHOT = ("pregnancy_status", "status", "date", "expected_kidding_date")


class MatingViewSet(FarmScopedViewSet):
    model = Mating
    serializer_class = s.MatingSerializer
    permission_module = "breeding"
    filterset_class = filterset_for(Mating, ("doe", "buck", "status", "pregnancy_status", "method"))
    search_fields = ("doe__animal_id", "doe__name", "buck__animal_id", "ai_straw")
    ordering = ("-date", "-created_at")
    action_permissions = {"scan": "update", "abort": "update"}

    def get_queryset(self) -> QuerySet:
        return super().get_queryset().select_related("doe", "buck", "created_by")

    @transaction.atomic
    def perform_create(self, serializer: Any) -> None:
        super().perform_create(serializer)
        services.after_mating_saved(serializer.instance, True, None, self.request.user)

    @transaction.atomic
    def perform_update(self, serializer: Any) -> None:
        before = {f: getattr(serializer.instance, f) for f in SNAPSHOT}
        super().perform_update(serializer)
        services.after_mating_saved(serializer.instance, False, before, self.request.user)

    @transaction.atomic
    def perform_destroy(self, instance: Any) -> None:
        if instance.status == MatingStatus.KIDDED:
            raise ValidationError({"detail": ["A mating with a recorded birth cannot be deleted."]})
        instance.status = MatingStatus.FAILED
        services.after_mating_saved(
            instance, False, {"status": MatingStatus.ACTIVE}, self.request.user
        )
        instance.delete()

    def _out(self, mating: Mating) -> Response:
        mating.refresh_from_db()
        return Response(s.MatingSerializer(mating).data)

    @extend_schema(request=s.ScanSerializer, responses=s.MatingSerializer)
    @action(detail=True, methods=["post"])
    def scan(self, request: Request, pk: str | None = None) -> Response:
        """Record the pregnancy scan result."""
        mating = self.get_object()
        if mating.status != MatingStatus.ACTIVE:
            raise ValidationError({"detail": ["This mating is closed."]})
        body = s.ScanSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        serializer = s.MatingSerializer(
            mating,
            data={
                "pregnancy_status": body.validated_data["result"],
                "scan_date": body.validated_data["scan_date"],
            },
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return self._out(mating)

    @extend_schema(request=None, responses=s.MatingSerializer)
    @action(detail=True, methods=["post"])
    def abort(self, request: Request, pk: str | None = None) -> Response:
        """The pregnancy was lost."""
        mating = self.get_object()
        if mating.status != MatingStatus.ACTIVE:
            raise ValidationError({"detail": ["This mating is closed."]})
        serializer = s.MatingSerializer(mating, data={"status": MatingStatus.ABORTED}, partial=True)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return self._out(mating)


class PregnancyListView(FarmScopedAPIView):
    """Pregnancy monitoring, derived from open matings, soonest kidding first."""

    permission_module = "breeding"

    @extend_schema(responses=s.PregnancySerializer(many=True))
    def get(self, request: Request) -> Response:
        matings = (
            Mating.objects.filter(
                status=MatingStatus.ACTIVE,
                pregnancy_status__in=[PregnancyStatus.AWAITING_SCAN, PregnancyStatus.CONFIRMED],
            )
            .select_related("doe", "buck")
            .order_by("expected_kidding_date")
        )
        out = []
        for m in matings:
            out.append(
                {
                    "mating_id": m.pk,
                    "doe": m.doe_id,
                    "doe_label": s._label(m.doe),
                    "buck_label": s._label(m.buck) or (f"AI: {m.ai_straw}" if m.ai_straw else "—"),
                    "mating_date": m.date,
                    "pregnancy_status": m.pregnancy_status,
                    "expected_kidding_date": m.expected_kidding_date,
                    **services.pregnancy_progress(m),
                }
            )
        return Response(out)


class BirthViewSet(
    FarmContextMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """Registering a birth creates the kids. Births are corrected, not deleted, because the
    kids are animals with their own records."""

    model = Birth
    permission_module = "breeding"
    filterset_class = filterset_for(Birth, ("dam", "condition"))
    search_fields = ("dam__animal_id", "dam__name")
    ordering = ("-date", "-created_at")
    action_permissions = {"create": "record_birth"}
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self) -> QuerySet:
        return (
            self.farm_queryset()
            .select_related("dam", "sire", "created_by")
            .prefetch_related("kids")
        )

    def get_serializer_class(self) -> Any:
        return s.BirthCreateSerializer if self.action == "create" else s.BirthSerializer

    @extend_schema(request=s.BirthCreateSerializer, responses={201: s.BirthSerializer})
    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = s.BirthCreateSerializer(
            data=request.data, context=self.get_serializer_context()
        )
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        kids = data.pop("kids")
        birth = services.record_birth(request.farm, request.user, data, kids)  # type: ignore[attr-defined]
        birth = self.get_queryset().get(pk=birth.pk)
        return Response(s.BirthSerializer(birth).data, status=status.HTTP_201_CREATED)


class KidViewSet(
    FarmContextMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """Kids under 6 months, with birth weight, latest weight and average daily gain."""

    model = Animal
    serializer_class = s.KidSerializer
    permission_module = "breeding"
    search_fields = ("animal_id", "name")
    ordering = ("-date_of_birth", "animal_id")
    action_permissions = {"growth": "view"}

    def get_queryset(self) -> QuerySet:
        return (
            services.kids_queryset(self.farm_queryset())
            .select_related("dam")
            .prefetch_related("weights")
        )

    @extend_schema(responses=s.KidSerializer)
    @action(detail=True)
    def growth(self, request: Request, pk: str | None = None) -> Response:
        return Response(services.kid_growth(self.get_object()))


class MortalityViewSet(FarmScopedViewSet):
    model = Mortality
    serializer_class = s.MortalitySerializer
    permission_module = "breeding"
    filterset_class = filterset_for(Mortality, ("cause_category", "animal"))
    search_fields = ("animal__animal_id", "animal__name", "cause")
    ordering = ("-date", "-created_at")

    def get_queryset(self) -> QuerySet:
        return super().get_queryset().select_related("animal", "created_by")

    @transaction.atomic
    def perform_create(self, serializer: Any) -> None:
        super().perform_create(serializer)
        services.record_death(serializer.instance)

    @transaction.atomic
    def perform_update(self, serializer: Any) -> None:
        super().perform_update(serializer)
        services.record_death(serializer.instance)

    @transaction.atomic
    def perform_destroy(self, instance: Any) -> None:
        """Recorded by mistake: the animal returns to the herd."""
        services.undo_death(instance)
        instance.hard_delete()
