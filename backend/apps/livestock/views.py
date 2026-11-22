from __future__ import annotations

from typing import Any

import django_filters
from django.db import transaction
from django.db.models import Count, OuterRef, Q, QuerySet, Subquery
from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response

from apps.core.images import process_image
from apps.core.views import FarmContextMixin, FarmScopedViewSet

from . import serializers as s
from . import services
from .models import (
    NEEDS_ATTENTION,
    Animal,
    AnimalGroup,
    AnimalPhoto,
    HealthStatus,
    Location,
    Sex,
    WeightRecord,
)


def with_list_data(qs: QuerySet[Animal]) -> QuerySet[Animal]:
    """Latest weight and primary photo in the same query, so the register stays fast."""
    latest = WeightRecord.objects.filter(animal=OuterRef("pk"), deleted_at__isnull=True).order_by(
        "-date", "-created_at"
    )
    photo = AnimalPhoto.objects.filter(animal=OuterRef("pk"), deleted_at__isnull=True).order_by(
        "-is_primary", "-created_at"
    )
    return qs.select_related("location", "group").annotate(
        latest_weight_kg=Subquery(latest.values("weight_kg")[:1]),
        latest_weight_date=Subquery(latest.values("date")[:1]),
        primary_thumb=Subquery(photo.values("thumbnail")[:1]),
    )


class AnimalFilter(django_filters.FilterSet):
    sex = django_filters.ChoiceFilter(choices=Sex.choices)
    species = django_filters.CharFilter()
    breed = django_filters.CharFilter(lookup_expr="iexact")
    status = django_filters.CharFilter(
        method="filter_status", help_text="Health status (comma-separated)"
    )
    breeding = django_filters.CharFilter(field_name="breeding_status")
    location = django_filters.UUIDFilter(field_name="location_id")
    group = django_filters.UUIDFilter(field_name="group_id")
    age = django_filters.ChoiceFilter(
        method="filter_age", choices=[("kid", "Kid"), ("young", "Young"), ("adult", "Adult")]
    )
    attention = django_filters.BooleanFilter(method="filter_attention")
    active = django_filters.CharFilter(
        method="filter_active", help_text="true (default), false or all"
    )

    class Meta:
        model = Animal
        fields: list[str] = []

    def filter_status(self, qs: QuerySet, name: str, value: str) -> QuerySet:
        return qs.filter(health_status__in=[v.strip() for v in value.split(",") if v.strip()])

    def filter_age(self, qs: QuerySet, name: str, value: str) -> QuerySet:
        born_after, born_before = services.age_band_bounds(value)
        if born_after:
            qs = qs.filter(date_of_birth__gte=born_after)
        if born_before:
            qs = qs.filter(date_of_birth__lte=born_before)
        return qs.exclude(date_of_birth__isnull=True)

    def filter_attention(self, qs: QuerySet, name: str, value: bool) -> QuerySet:
        return qs.filter(health_status__in=NEEDS_ATTENTION) if value else qs

    def filter_active(self, qs: QuerySet, name: str, value: str) -> QuerySet:
        return qs  # applied in get_queryset so the default (active only) also works without it


class AnimalViewSet(FarmScopedViewSet):
    """The livestock register. Attendants can view, register and record weights."""

    model = Animal
    permission_module = "livestock"
    filterset_class = AnimalFilter
    search_fields = ("animal_id", "ear_tag", "name", "breed")
    ordering_fields = ("animal_id", "name", "date_of_birth", "created_at", "health_status", "breed")
    ordering = ("animal_id",)
    action_permissions = {
        "weights": {"GET": "view", "POST": "record_weight"},
        "photos": {"GET": "view", "POST": "create"},
        "timeline": "view",
        "summary": "view",
        "next_id": "view",
        "export": "export",
        "exit": "update",
        "reactivate": "update",
    }

    def get_queryset(self) -> QuerySet:
        qs = with_list_data(super().get_queryset())
        if self.action in ("list", "export", "summary"):
            active = self.request.query_params.get("active", "true").lower()
            if active in ("true", "1", "yes"):
                qs = qs.filter(is_active=True)
            elif active in ("false", "0", "no"):
                qs = qs.filter(is_active=False)
        if self.action == "retrieve":
            qs = qs.select_related("dam", "sire", "created_by")
        return qs

    def get_serializer_class(self) -> Any:
        if self.action == "list":
            return s.AnimalListSerializer
        if self.action == "retrieve":
            return s.AnimalDetailSerializer
        return s.AnimalWriteSerializer

    def _detail(self, animal: Animal, code: int = status.HTTP_200_OK) -> Response:
        fresh = (
            with_list_data(Animal.objects.filter(pk=animal.pk))
            .select_related("dam", "sire", "created_by")
            .get()
        )
        return Response(s.AnimalDetailSerializer(fresh).data, status=code)

    @extend_schema(request=s.AnimalWriteSerializer, responses={201: s.AnimalDetailSerializer})
    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return self._detail(serializer.instance, status.HTTP_201_CREATED)  # type: ignore[arg-type]

    @extend_schema(request=s.AnimalWriteSerializer, responses=s.AnimalDetailSerializer)
    def update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        partial = kwargs.pop("partial", False)
        serializer = self.get_serializer(self.get_object(), data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return self._detail(serializer.instance)  # type: ignore[arg-type]

    @extend_schema(responses=s.NextIdSerializer)
    @action(detail=False, url_path="next-id")
    def next_id(self, request: Request) -> Response:
        return Response({"animal_id": services.next_animal_id(request.farm)})  # type: ignore[attr-defined]

    @extend_schema(responses=s.SummarySerializer)
    @action(detail=False)
    def summary(self, request: Request) -> Response:
        """Counts for the register's stat cards (active animals, after filters)."""
        qs = self.filter_queryset(self.get_queryset())
        kid_born_after, _ = services.age_band_bounds("kid")
        counts = qs.aggregate(
            total=Count("pk"),
            males=Count("pk", filter=Q(sex=Sex.MALE)),
            females=Count("pk", filter=Q(sex=Sex.FEMALE)),
            kids=Count("pk", filter=Q(date_of_birth__gte=kid_born_after)),
            needing_attention=Count("pk", filter=Q(health_status__in=NEEDS_ATTENTION)),
            pregnant=Count("pk", filter=Q(health_status=HealthStatus.PREGNANT)),
        )
        counts["inactive"] = Animal.objects.filter(is_active=False).count()
        return Response(counts)

    @extend_schema(
        parameters=[OpenApiParameter("format", str, enum=["csv", "xlsx"])],
        responses={(200, "text/csv"): bytes},
    )
    @action(detail=False)
    def export(self, request: Request) -> HttpResponse:
        qs = self.filter_queryset(self.get_queryset()).select_related("dam", "sire")
        fmt = request.query_params.get("format", "csv")
        stamp = timezone.localdate().isoformat()
        if fmt == "xlsx":
            body = services.export_xlsx(qs, request.farm.name)  # type: ignore[attr-defined]
            content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        else:
            body, content_type, fmt = services.export_csv(qs), "text/csv; charset=utf-8", "csv"
        response = HttpResponse(body, content_type=content_type)
        response["Content-Disposition"] = f'attachment; filename="livestock-register-{stamp}.{fmt}"'
        return response

    @extend_schema(responses=s.TimelineEventSerializer(many=True))
    @action(detail=True)
    def timeline(self, request: Request, pk: str | None = None) -> Response:
        return Response(services.timeline(self.get_object()))

    @extend_schema(methods=["GET"], responses=s.WeightRecordSerializer(many=True))
    @extend_schema(
        methods=["POST"],
        request=s.WeightRecordSerializer,
        responses={201: s.WeightRecordSerializer},
    )
    @action(detail=True, methods=["get", "post"])
    def weights(self, request: Request, pk: str | None = None) -> Response:
        animal = self.get_object()
        if request.method == "POST":
            serializer = s.WeightRecordSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            serializer.save(animal=animal, farm=request.farm, created_by=request.user, updated_by=request.user)  # type: ignore[attr-defined]
            return Response(
                s.WeightRecordSerializer(serializer.instance).data, status=status.HTTP_201_CREATED
            )
        records = list(animal.weights.select_related("created_by").order_by("date", "created_at"))
        previous = {r.pk: records[i - 1].weight_kg for i, r in enumerate(records) if i > 0}
        records.reverse()
        return Response(
            s.WeightRecordSerializer(records, many=True, context={"previous": previous}).data
        )

    @extend_schema(methods=["GET"], responses=s.AnimalPhotoSerializer(many=True))
    @extend_schema(
        methods=["POST"],
        request={"multipart/form-data": s.PhotoUploadSerializer},
        responses={201: s.AnimalPhotoSerializer},
    )
    @action(
        detail=True,
        methods=["get", "post"],
        parser_classes=[MultiPartParser, FormParser, JSONParser],
    )
    def photos(self, request: Request, pk: str | None = None) -> Response:
        animal = self.get_object()
        if request.method == "GET":
            return Response(s.AnimalPhotoSerializer(animal.photos.all(), many=True).data)
        serializer = s.PhotoUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        upload = serializer.validated_data["file"]
        full = process_image(upload, max_size=1600)
        thumb = process_image(upload, max_size=400)
        with transaction.atomic():
            first = not animal.photos.exists()
            primary = serializer.validated_data["is_primary"] or first
            if primary:
                animal.photos.filter(is_primary=True).update(is_primary=False)
            photo = AnimalPhoto(
                animal=animal,
                farm=request.farm,  # type: ignore[attr-defined]
                is_primary=primary,
                caption=serializer.validated_data.get("caption", ""),
            )
            photo.file.save(
                f"{animal.animal_id}.{(full.name or 'x.jpg').rsplit('.', 1)[-1]}", full, save=False
            )
            photo.thumbnail.save(
                f"{animal.animal_id}-thumb.{(thumb.name or 'x.jpg').rsplit('.', 1)[-1]}",
                thumb,
                save=False,
            )
            photo.save()
        return Response(s.AnimalPhotoSerializer(photo).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=s.ExitSerializer, responses=s.AnimalDetailSerializer)
    @action(detail=True, methods=["post"])
    def exit(self, request: Request, pk: str | None = None) -> Response:
        """Record that the animal was sold, died or was culled. Its history stays."""
        animal = self.get_object()
        serializer = s.ExitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        animal.is_active = False
        animal.exit_reason, animal.exit_date, animal.exit_notes = (
            data["reason"],
            data["date"],
            data.get("notes", ""),
        )
        animal.save()
        return self._detail(animal)

    @extend_schema(request=None, responses=s.AnimalDetailSerializer)
    @action(detail=True, methods=["post"])
    def reactivate(self, request: Request, pk: str | None = None) -> Response:
        """Undo an exit recorded by mistake."""
        animal = self.get_object()
        animal.is_active, animal.exit_reason, animal.exit_date, animal.exit_notes = (
            True,
            "",
            None,
            "",
        )
        animal.save()
        return self._detail(animal)


class WeightRecordViewSet(
    FarmContextMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """Correct or remove a weight (managers and administrators). Recording is per animal."""

    model = WeightRecord
    serializer_class = s.WeightRecordSerializer
    permission_module = "livestock"
    filterset_fields = ("animal",)
    ordering = ("-date", "-created_at")

    def get_queryset(self) -> QuerySet:
        return self.farm_queryset().select_related("created_by")

    def perform_update(self, serializer: Any) -> None:
        serializer.save(updated_by=self.request.user)

    def perform_destroy(self, instance: Any) -> None:
        instance.delete()


class AnimalPhotoViewSet(
    FarmContextMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    model = AnimalPhoto
    serializer_class = s.AnimalPhotoSerializer
    permission_module = "livestock"
    filterset_fields = ("animal",)
    action_permissions = {"make_primary": "update"}

    def get_queryset(self) -> QuerySet:
        return self.farm_queryset()

    @extend_schema(request=None, responses=s.AnimalPhotoSerializer)
    @action(detail=True, methods=["post"], url_path="primary")
    def make_primary(self, request: Request, pk: str | None = None) -> Response:
        photo = self.get_object()
        with transaction.atomic():
            AnimalPhoto.objects.filter(animal=photo.animal, is_primary=True).exclude(
                pk=photo.pk
            ).update(is_primary=False)
            photo.is_primary = True
            photo.save(update_fields=["is_primary", "updated_at", "updated_by"])
        return Response(s.AnimalPhotoSerializer(photo).data)

    def perform_destroy(self, instance: Any) -> None:
        was_primary = instance.is_primary
        instance.delete()
        if was_primary:
            nxt = AnimalPhoto.objects.filter(animal=instance.animal).order_by("-created_at").first()
            if nxt:
                nxt.is_primary = True
                nxt.save(update_fields=["is_primary", "updated_at", "updated_by"])


class _CountedViewSet(FarmScopedViewSet):
    permission_module = "livestock"
    # Attendants register and weigh animals; setting up pens and groups is for managers.
    action_permissions = {
        "create": "manage",
        "update": "manage",
        "partial_update": "manage",
        "destroy": "manage",
    }
    ordering = ("name",)
    search_fields = ("name",)
    pagination_class = None  # short lists used in dropdowns

    def get_queryset(self) -> QuerySet:
        return (
            super()
            .get_queryset()
            .annotate(
                animal_count=Count(
                    "animals", filter=Q(animals__deleted_at__isnull=True, animals__is_active=True)
                )
            )
        )

    def perform_destroy(self, instance: Any) -> None:
        # Animals keep their records; they just lose the link to the removed location/group.
        instance.animals.update(**{self.model_fk: None})  # type: ignore[attr-defined]
        instance.delete()


class LocationViewSet(_CountedViewSet):
    model = Location
    serializer_class = s.LocationSerializer
    model_fk = "location"
    filterset_fields = ("type",)


class AnimalGroupViewSet(_CountedViewSet):
    model = AnimalGroup
    serializer_class = s.AnimalGroupSerializer
    model_fk = "group"
