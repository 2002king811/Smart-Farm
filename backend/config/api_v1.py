"""All /api/v1/ routes. Each phase registers its viewsets here."""

from django.urls import include, path

from apps.audit.views import AuditLogViewSet
from apps.core.routers import router

router.register("audit-logs", AuditLogViewSet, basename="audit-log")

urlpatterns = [
    path("", include("apps.accounts.urls")),
    path("", include(router.urls)),
]
