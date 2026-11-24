from __future__ import annotations

import calendar as cal
from datetime import date, timedelta
from typing import Any

import django_filters
from django.db import transaction
from django.db.models import QuerySet
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response

from apps.core.views import FarmScopedAPIView, FarmScopedViewSet
from apps.notifications.events import emit

from . import serializers as s
from . import services
from .models import Activity, ActivityCategory, ActivityNote, ActivityStatus


class ActivityFilter(django_filters.FilterSet):
    date_from = django_filters.DateFilter(field_name="date", lookup_expr="gte")
    date_to = django_filters.DateFilter(field_name="date", lookup_expr="lte")
    category = django_filters.CharFilter(method="filter_category", help_text="Category id or key")
    assignee = django_filters.CharFilter(
        method="filter_assignee", help_text="User id, 'me' or 'none'"
    )
    status = django_filters.CharFilter(method="filter_status", help_text="Comma-separated")
    priority = django_filters.CharFilter()
    animal = django_filters.UUIDFilter(field_name="animals")
    source = django_filters.CharFilter()

    class Meta:
        model = Activity
        fields: list[str] = []

    def filter_category(self, qs: QuerySet, name: str, value: str) -> QuerySet:
        import uuid

        try:
            return qs.filter(category_id=uuid.UUID(value))
        except ValueError:
            return qs.filter(category__key=value)

    def filter_assignee(self, qs: QuerySet, name: str, value: str) -> QuerySet:
        if value == "me":
            return qs.filter(assigned_to=self.request.user)  # type: ignore[union-attr]
        if value == "none":
            return qs.filter(assigned_to__isnull=True)
        return qs.filter(assigned_to_id=value)

    def filter_status(self, qs: QuerySet, name: str, value: str) -> QuerySet:
        return qs.filter(status__in=[v.strip() for v in value.split(",") if v.strip()])


def _with_relations(qs: QuerySet) -> QuerySet:
    return qs.select_related(
        "category", "assigned_to", "group", "completed_by", "created_by", "source_type", "series"
    ).prefetch_related("animals")


def _from_param(value: str | None) -> date:
    """Accepts both from/to (spec) and date_from/date_to."""
    try:
        return date.fromisoformat(value) if value else date.today()
    except ValueError as exc:
        raise ValidationError({"date": ["Use the format YYYY-MM-DD."]}) from exc


class ActivityViewSet(FarmScopedViewSet):
    """Farm activities and tasks. Attendants see and act on their own tasks only."""

    model = Activity
    permission_module = "activities"
    filterset_class = ActivityFilter
    search_fields = ("title", "description")
    ordering_fields = ("date", "priority", "status", "created_at")
    ordering = ("date", "start_time", "created_at")
    action_permissions = {
        "start": "start",
        "complete": "complete",
        "cancel": "cancel",
        "reopen": "update",
        "assign": "assign",
        "notes": {"GET": "view", "POST": "add_note"},
        "history": "view",
    }

    def get_queryset(self) -> QuerySet:
        qs = _with_relations(super().get_queryset())
        params = self.request.query_params
        if params.get("from"):
            qs = qs.filter(date__gte=_from_param(params["from"]))
        if params.get("to"):
            qs = qs.filter(date__lte=_from_param(params["to"]))
        if self.scope == "own":
            qs = qs.filter(assigned_to=self.request.user)
        return qs

    def get_serializer_class(self) -> Any:
        if self.action in ("create", "update", "partial_update"):
            return s.ActivityWriteSerializer
        return s.ActivitySerializer

    def _out(self, activity: Activity, code: int = status.HTTP_200_OK) -> Response:
        fresh = _with_relations(Activity.objects.filter(pk=activity.pk)).get()
        return Response(s.ActivitySerializer(fresh).data, status=code)

    @extend_schema(request=s.ActivityWriteSerializer, responses={201: s.ActivitySerializer})
    @transaction.atomic
    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = s.ActivityWriteSerializer(
            data=request.data, context=self.get_serializer_context()
        )
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        data.pop("scope", None)
        animals = data.pop("animals", [])
        past = data["date"] < services.farm_today(request.farm)  # type: ignore[attr-defined]
        activity = Activity.objects.create(
            farm=request.farm,  # type: ignore[attr-defined]
            created_by=request.user,
            updated_by=request.user,
            status=ActivityStatus.OVERDUE if past else ActivityStatus.PENDING,
            **data,
        )
        activity.animals.set(animals)
        services.extend_series(activity)
        if activity.assigned_to_id and activity.assigned_to_id != request.user.pk:
            emit(
                "task.assigned",
                activity.farm_id,
                activity_id=str(activity.pk),
                recipient_id=str(activity.assigned_to_id),
                actor_id=str(request.user.pk),
            )
        return self._out(activity, status.HTTP_201_CREATED)

    @extend_schema(request=s.ActivityWriteSerializer, responses=s.ActivitySerializer)
    @transaction.atomic
    def update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        activity = self.get_object()
        serializer = s.ActivityWriteSerializer(
            activity, data=request.data, partial=True, context=self.get_serializer_context()
        )
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        scope = data.pop("scope", "this")
        animals = data.pop("animals", None)
        old_assignee = activity.assigned_to_id
        is_series = bool(activity.recurrence_rule or activity.series_id)
        rule_changed = (
            "recurrence_rule" in data and data["recurrence_rule"] != activity.recurrence_rule
        )
        if is_series and (scope == "following" or rule_changed):
            activity = services.update_following(activity, data, animals)
        else:
            services.apply_changes(activity, data, animals)
            if rule_changed and activity.recurrence_rule:
                services.extend_series(activity)  # a one-off now repeats
        if (
            "date" in data
            and activity.status == ActivityStatus.OVERDUE
            and activity.date >= services.farm_today(activity.farm)
        ):
            services.set_status(activity, ActivityStatus.PENDING, request.user, "Rescheduled")
        if activity.assigned_to_id and activity.assigned_to_id != old_assignee:
            emit(
                "task.assigned",
                activity.farm_id,
                activity_id=str(activity.pk),
                recipient_id=str(activity.assigned_to_id),
                actor_id=str(request.user.pk),
            )
        return self._out(activity)

    @extend_schema(parameters=[OpenApiParameter("scope", str, enum=["this", "following"])])
    def destroy(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        services.delete_with_scope(self.get_object(), request.query_params.get("scope", "this"))
        return Response(status=status.HTTP_204_NO_CONTENT)

    def _transition(self, request: Request, name: str) -> Response:
        body = s.ActionSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        activity = services.transition(
            self.get_object(),
            name,
            request.user,
            body.validated_data.get("note", ""),
            offline_at=body.validated_data.get("offline_at"),
        )
        return self._out(activity)

    @extend_schema(request=s.ActionSerializer, responses=s.ActivitySerializer)
    @action(detail=True, methods=["post"])
    def start(self, request: Request, pk: str | None = None) -> Response:
        return self._transition(request, "start")

    @extend_schema(request=s.ActionSerializer, responses=s.ActivitySerializer)
    @action(detail=True, methods=["post"])
    def complete(self, request: Request, pk: str | None = None) -> Response:
        return self._transition(request, "complete")

    @extend_schema(request=s.ActionSerializer, responses=s.ActivitySerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request: Request, pk: str | None = None) -> Response:
        return self._transition(request, "cancel")

    @extend_schema(request=s.ActionSerializer, responses=s.ActivitySerializer)
    @action(detail=True, methods=["post"])
    def reopen(self, request: Request, pk: str | None = None) -> Response:
        return self._transition(request, "reopen")

    @extend_schema(request=s.AssignSerializer, responses=s.ActivitySerializer)
    @action(detail=True, methods=["post"])
    def assign(self, request: Request, pk: str | None = None) -> Response:
        activity = self.get_object()
        body = s.AssignSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        activity.assigned_to = body.validated_data["assigned_to"]
        activity.save()
        if activity.assigned_to_id and activity.assigned_to_id != request.user.pk:
            emit(
                "task.assigned",
                activity.farm_id,
                activity_id=str(activity.pk),
                recipient_id=str(activity.assigned_to_id),
                actor_id=str(request.user.pk),
            )
        return self._out(activity)

    @extend_schema(methods=["GET"], responses=s.NoteSerializer(many=True))
    @extend_schema(methods=["POST"], request=s.NoteSerializer, responses={201: s.NoteSerializer})
    @action(detail=True, methods=["get", "post"])
    def notes(self, request: Request, pk: str | None = None) -> Response:
        activity = self.get_object()
        if request.method == "POST":
            body = s.NoteSerializer(data=request.data)
            body.is_valid(raise_exception=True)
            note = ActivityNote.objects.create(
                farm=request.farm,  # type: ignore[attr-defined]
                activity=activity,
                text=body.validated_data["text"],
                created_by=request.user,
                updated_by=request.user,
            )
            return Response(s.NoteSerializer(note).data, status=status.HTTP_201_CREATED)
        return Response(
            s.NoteSerializer(activity.notes.select_related("created_by"), many=True).data
        )

    @extend_schema(responses=s.HistorySerializer(many=True))
    @action(detail=True)
    def history(self, request: Request, pk: str | None = None) -> Response:
        activity = self.get_object()
        return Response(
            s.HistorySerializer(activity.history.select_related("created_by"), many=True).data
        )


class AssigneesView(FarmScopedAPIView):
    """Active members of the farm, for the "Assign to" list (names and roles only)."""

    permission_module = "activities"

    @extend_schema(responses=s.AssigneeSerializer(many=True))
    def get(self, request: Request) -> Response:
        from apps.accounts.models import FarmMembership, MembershipStatus

        rows = (
            FarmMembership.objects.filter(farm=request.farm, status=MembershipStatus.ACTIVE)  # type: ignore[attr-defined]
            .select_related("user")
            .order_by("user__first_name", "user__last_name")
        )
        return Response(
            [
                {
                    "id": str(m.user_id),
                    "name": m.user.full_name,
                    "role": m.role,
                    "role_label": m.get_role_display(),
                }
                for m in rows
            ]
        )


class CategoryViewSet(FarmScopedViewSet):
    model = ActivityCategory
    serializer_class = s.CategorySerializer
    permission_module = "calendar"
    pagination_class = None
    ordering = ("name",)


def calendar_range(view: str, day: date) -> tuple[date, date]:
    """The dates a calendar view covers. Weeks start on Monday."""
    if view == "day":
        return day, day
    if view == "week":
        start = day - timedelta(days=day.weekday())
        return start, start + timedelta(days=6)
    if view == "agenda":
        return day, day + timedelta(days=30)
    first = day.replace(day=1)
    last = day.replace(day=cal.monthrange(day.year, day.month)[1])
    return first - timedelta(days=first.weekday()), last + timedelta(days=6 - last.weekday())


class CalendarView(FarmScopedAPIView):
    """The health calendar: every activity in the range (attendants can view it)."""

    permission_module = "calendar"

    @extend_schema(
        parameters=[
            OpenApiParameter("view", str, enum=["month", "week", "day", "agenda"]),
            OpenApiParameter("date", str, description="YYYY-MM-DD; defaults to today"),
            OpenApiParameter("category", str),
            OpenApiParameter("assignee", str),
            OpenApiParameter("status", str),
        ],
        responses=s.CalendarSerializer,
    )
    def get(self, request: Request) -> Response:
        params = request.query_params
        view = params.get("view") or request.farm.default_calendar_view  # type: ignore[attr-defined]
        if view not in ("month", "week", "day", "agenda"):
            raise ValidationError({"view": ["Use month, week, day or agenda."]})
        farm: Any = request.farm  # type: ignore[attr-defined]
        day = _from_param(params.get("date")) if params.get("date") else services.farm_today(farm)
        start, end = calendar_range(view, day)
        qs = _with_relations(Activity.objects.filter(date__range=(start, end)))
        qs = ActivityFilter(params, queryset=qs, request=request).qs
        if view == "agenda":
            qs = qs.exclude(status__in=[ActivityStatus.CANCELLED])
        return Response(
            {
                "view": view,
                "start": start,
                "end": end,
                "activities": s.ActivitySerializer(
                    qs.order_by("date", "start_time", "created_at"), many=True
                ).data,
            }
        )


class TemplateListView(FarmScopedAPIView):
    permission_module = "calendar"

    @extend_schema(responses=s.TemplateSerializer(many=True))
    def get(self, request: Request) -> Response:
        out = []
        for key, t in services.TEMPLATES.items():
            keys = [item[0] for item in t["items"]]
            out.append(
                {
                    "key": key,
                    "name": t["name"],
                    "description": t["description"],
                    "count": len(keys),
                    "applied": Activity.objects.filter(template_key__in=keys).count(),
                }
            )
        return Response(out)


class TemplateApplyView(FarmScopedAPIView):
    permission_module = "calendar"
    action_permissions = {"create": "create"}

    @extend_schema(request=None, responses=s.ApplyResultSerializer)
    def post(self, request: Request, key: str) -> Response:
        created, skipped = services.apply_template(request.farm, key, request.user)  # type: ignore[attr-defined]
        return Response({"created": created, "skipped": skipped})
