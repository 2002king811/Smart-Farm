"""Dashboard and reports API."""

from __future__ import annotations

from typing import Any

from django.core.files.storage import default_storage
from django.http import FileResponse, HttpRequest, HttpResponse
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from apps.accounts.models import Role
from apps.accounts.services import normalise_phone
from apps.calendar.services import farm_today
from apps.core.views import FarmContextMixin, FarmScopedAPIView, FarmScopedViewSet

from . import dashboard, exports, services
from . import metrics as m
from .builders import catalog
from .models import ReportRun, ReportSchedule, RunStatus

PERIOD_PARAMS = [
    OpenApiParameter("from", OpenApiTypes.DATE),
    OpenApiParameter("to", OpenApiTypes.DATE),
    OpenApiParameter("group", str, enum=["day", "week", "month"]),
]


def params_of(request: Request) -> dict[str, str]:
    return {k: v for k, v in request.query_params.items() if v}  # type: ignore[misc]


# --- Dashboard ------------------------------------------------------------------------------------


class DashboardMixin(FarmScopedAPIView):
    permission_module = "dashboard"

    @property
    def own(self) -> bool:
        return self.scope == "own"


class DashboardSummaryView(DashboardMixin):
    @extend_schema(parameters=PERIOD_PARAMS[:2], responses=OpenApiTypes.OBJECT)
    def get(self, request: Request) -> Response:
        farm: Any = request.farm  # type: ignore[attr-defined]
        start = services.parse_date(request.query_params.get("from"), "from")
        end = services.parse_date(request.query_params.get("to"), "to")
        period = m.month_period(farm_today(farm))
        if start or end:
            period = m.Period(start or period.start, end or period.end)
            if period.end < period.start:
                raise ValidationError({"to": ["The end date must be on or after the start date."]})
        return Response(dashboard.summary(farm, request.user, self.own, period))


class DashboardChartsView(DashboardMixin):
    @extend_schema(
        parameters=[OpenApiParameter("range", str, enum=["3m", "6m", "12m"])],
        responses=OpenApiTypes.OBJECT,
    )
    def get(self, request: Request) -> Response:
        if self.own:
            raise PermissionDenied("Farm charts are for administrators and managers.")
        months = {"3m": 3, "6m": 6, "12m": 12}.get(request.query_params.get("range", "6m"))
        if months is None:
            raise ValidationError({"range": ["Use 3m, 6m or 12m."]})
        return Response(dashboard.charts(request.farm, months))  # type: ignore[attr-defined]


class DashboardUpcomingView(DashboardMixin):
    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request: Request) -> Response:
        return Response(dashboard.upcoming(request.farm, request.user, self.own))  # type: ignore[attr-defined]


class DashboardRecentHealthView(DashboardMixin):
    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request: Request) -> Response:
        return Response(dashboard.recent_health())


# --- Reports --------------------------------------------------------------------------------------


class ReportCatalogView(FarmScopedAPIView):
    """The 15 reports, with their filters and default period."""

    permission_module = "reports"

    @extend_schema(operation_id="reports_catalog", responses=OpenApiTypes.OBJECT)
    def get(self, request: Request) -> Response:
        return Response(catalog())


class ReportPreviewView(FarmScopedAPIView):
    permission_module = "reports"

    @extend_schema(parameters=PERIOD_PARAMS, responses=OpenApiTypes.OBJECT)
    def get(self, request: Request, report_type: str) -> Response:
        data = services.build(request.farm, report_type, params_of(request))  # type: ignore[attr-defined]
        return Response(data.as_dict())


class ReportExportView(FarmScopedAPIView):
    """The file straight away, or – over 2,000 rows – 202 with a run that finishes in the
    background and notifies you (in-app and by email) with a link valid for 24 hours."""

    permission_module = "reports"

    @extend_schema(
        parameters=[*PERIOD_PARAMS, OpenApiParameter("format", str, enum=["pdf", "xlsx", "csv"])],
        responses={
            (200, "application/octet-stream"): OpenApiTypes.BINARY,
            202: OpenApiTypes.OBJECT,
        },
    )
    def get(self, request: Request, report_type: str) -> HttpResponse:
        fmt = request.query_params.get("format", "pdf")
        if fmt not in exports.RENDERERS:
            raise ValidationError({"format": ["Use pdf, xlsx or csv."]})
        farm: Any = request.farm  # type: ignore[attr-defined]
        params = params_of(request)
        run = services.new_run(farm, request.user, report_type, params, fmt)
        data = services.build(farm, report_type, services.run_params(run))
        if data.row_count > services.LARGE_ROWS:
            run.row_count = data.row_count
            run.save(update_fields=["row_count"])
            services.start_large(run)
            return Response(
                {
                    "id": str(run.pk),
                    "status": RunStatus.QUEUED,
                    "row_count": data.row_count,
                    "message": "This report is large. We'll notify you when the file is ready.",
                },
                status=status.HTTP_202_ACCEPTED,
            )
        content, ctype, name = exports.render(data, fmt, farm, request.user)
        run.status, run.row_count, run.finished_at = RunStatus.DONE, data.row_count, timezone.now()
        run.save(update_fields=["status", "row_count", "finished_at"])
        response = HttpResponse(content, content_type=ctype)
        response["Content-Disposition"] = f'attachment; filename="{name}"'
        return response


class ShareSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=20)

    def validate_phone(self, value: str) -> str:
        try:
            return normalise_phone(value)
        except Exception as exc:
            raise serializers.ValidationError(
                "Enter a valid mobile number, e.g. +256 772 123456."
            ) from exc


class ReportShareView(FarmScopedAPIView):
    """Send a short summary and a 24-hour link to the PDF by WhatsApp."""

    permission_module = "reports"
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "report_share"

    @extend_schema(
        parameters=PERIOD_PARAMS, request=ShareSerializer, responses={202: OpenApiTypes.OBJECT}
    )
    def post(self, request: Request, report_type: str) -> Response:
        body = ShareSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        out = services.share(request.farm, request.user, report_type, params_of(request), body.validated_data["phone"])  # type: ignore[attr-defined]
        out.refresh_from_db()
        return Response(
            {"id": str(out.pk), "status": out.status, "error": out.error, "to": out.to},
            status=status.HTTP_202_ACCEPTED,
        )


class ReportRunSerializer(serializers.ModelSerializer):
    download_url = serializers.SerializerMethodField()
    title = serializers.SerializerMethodField()

    class Meta:
        model = ReportRun
        fields = (
            "id",
            "report_type",
            "title",
            "filters",
            "date_from",
            "date_to",
            "format",
            "status",
            "row_count",
            "error",
            "purpose",
            "created_at",
            "finished_at",
            "download_url",
        )

    def get_title(self, obj: ReportRun) -> str:
        from .builders import REPORTS

        cls = REPORTS.get(obj.report_type)
        return cls.title if cls else obj.report_type

    def get_download_url(self, obj: ReportRun) -> str | None:
        if obj.status != RunStatus.DONE or not obj.file:
            return None
        if (
            obj.finished_at
            and (timezone.now() - obj.finished_at).total_seconds() > services.LINK_HOURS * 3600
        ):
            return None
        return services.download_url(obj)


class ReportRunViewSet(
    FarmContextMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """Your exports on this farm (the background ones keep a file for 24 hours)."""

    serializer_class = ReportRunSerializer
    permission_module = "reports"
    model = ReportRun

    def get_queryset(self) -> Any:
        if getattr(self, "swagger_fake_view", False):
            return ReportRun.objects.none()
        return self.farm_queryset().filter(requested_by=self.request.user)


def download_run(request: HttpRequest, pk: str) -> HttpResponse | FileResponse:
    """Signed link from the "report ready" message; works without signing in for 24 hours."""
    token = request.GET.get("token", "")
    if not services.check_token(pk, token):
        return HttpResponse(
            "This link has expired or is not valid. Export the report again.",
            status=403,
            content_type="text/plain",
        )
    run = ReportRun.unscoped.filter(pk=pk, status=RunStatus.DONE).first()
    if run is None or not run.file:
        raise NotFound()
    name = run.file.name.rsplit("/", 1)[-1]
    return FileResponse(
        default_storage.open(run.file.name, "rb"), as_attachment=True, filename=name
    )


# --- Schedules ------------------------------------------------------------------------------------


class ScheduleSerializer(serializers.ModelSerializer):
    report_label = serializers.CharField(source="get_report_type_display", read_only=True)

    class Meta:
        model = ReportSchedule
        fields = (
            "id",
            "report_type",
            "report_label",
            "recipients",
            "format",
            "enabled",
            "last_period",
            "last_sent_at",
        )
        read_only_fields = ("last_period", "last_sent_at")

    def validate_recipients(self, value: list[str]) -> list[str]:
        clean = sorted({v.strip().lower() for v in value if v.strip()})
        if not clean:
            raise serializers.ValidationError("Add at least one email address.")
        if len(clean) > 20:
            raise serializers.ValidationError("Up to 20 people.")
        return clean


class ReportScheduleViewSet(FarmScopedViewSet):
    """Monthly activities / quarterly health report by email. Administrators only."""

    serializer_class = ScheduleSerializer
    permission_module = "reports"
    model = ReportSchedule
    pagination_class = None

    def check_permissions(self, request: Request) -> None:
        super().check_permissions(request)
        if request.membership.role != Role.ADMINISTRATOR:  # type: ignore[attr-defined]
            raise PermissionDenied("Only administrators can schedule reports.")


# --- Export all farm data -------------------------------------------------------------------------


class FarmDataExportView(FarmScopedAPIView):
    permission_module = "settings"

    @extend_schema(responses={(200, "application/zip"): OpenApiTypes.BINARY})
    def get(self, request: Request) -> HttpResponse:
        farm: Any = request.farm  # type: ignore[attr-defined]
        response = HttpResponse(services.farm_data_zip(farm), content_type="application/zip")
        response["Content-Disposition"] = (
            f'attachment; filename="{farm.slug}-data-{timezone.localdate():%Y%m%d}.zip"'
        )
        return response
