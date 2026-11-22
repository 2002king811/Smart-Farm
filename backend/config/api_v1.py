"""All /api/v1/ routes. Each phase registers its viewsets here."""

from django.urls import include, path

from apps.accounts.views import InvitationViewSet, MemberViewSet
from apps.audit.views import AuditLogViewSet
from apps.core.routers import router
from apps.livestock.views import (
    AnimalGroupViewSet,
    AnimalPhotoViewSet,
    AnimalViewSet,
    LocationViewSet,
    WeightRecordViewSet,
)

router.register("audit-logs", AuditLogViewSet, basename="audit-log")
router.register("members", MemberViewSet, basename="member")
router.register("invitations", InvitationViewSet, basename="invitation")
router.register("animals", AnimalViewSet, basename="animal")
router.register("weights", WeightRecordViewSet, basename="weight")
router.register("animal-photos", AnimalPhotoViewSet, basename="animal-photo")
router.register("locations", LocationViewSet, basename="location")
router.register("animal-groups", AnimalGroupViewSet, basename="animal-group")

urlpatterns = [
    path("", include("apps.accounts.urls")),
    path("", include(router.urls)),
]
