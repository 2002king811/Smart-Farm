"""All /api/v1/ routes. Each phase registers its viewsets here."""

from django.urls import include, path

from apps.accounts.views import InvitationViewSet, MemberViewSet
from apps.audit.views import AuditLogViewSet
from apps.core.routers import router

router.register("audit-logs", AuditLogViewSet, basename="audit-log")
router.register("members", MemberViewSet, basename="member")
router.register("invitations", InvitationViewSet, basename="invitation")

urlpatterns = [
    path("", include("apps.accounts.urls")),
    path("", include(router.urls)),
]
