"""All /api/v1/ routes. Each phase registers its viewsets here."""

from django.urls import include, path

from apps.accounts.views import InvitationViewSet, MemberViewSet
from apps.audit.views import AuditLogViewSet
from apps.calendar.views import (
    ActivityViewSet,
    AssigneesView,
    CalendarView,
    CategoryViewSet,
    TemplateApplyView,
    TemplateListView,
)
from apps.core.routers import router
from apps.health.views import (
    DewormingViewSet,
    HealthInspectionViewSet,
    HealthObservationViewSet,
    HealthSummaryView,
    MedicineViewSet,
    ParasiteControlViewSet,
    TreatmentViewSet,
    VaccinationViewSet,
    VaccineViewSet,
    VetVisitViewSet,
)
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
router.register("vaccinations", VaccinationViewSet, basename="vaccination")
router.register("dewormings", DewormingViewSet, basename="deworming")
router.register("treatments", TreatmentViewSet, basename="treatment")
router.register("vet-visits", VetVisitViewSet, basename="vet-visit")
router.register("observations", HealthObservationViewSet, basename="observation")
router.register("inspections", HealthInspectionViewSet, basename="inspection")
router.register("parasite-control", ParasiteControlViewSet, basename="parasite-control")
router.register("vaccines", VaccineViewSet, basename="vaccine")
router.register("medicines", MedicineViewSet, basename="medicine")
router.register("activities", ActivityViewSet, basename="activity")
router.register("activity-categories", CategoryViewSet, basename="activity-category")

urlpatterns = [
    path("", include("apps.accounts.urls")),
    path("health/summary", HealthSummaryView.as_view(), name="health-summary"),
    path("activities/calendar", CalendarView.as_view(), name="activity-calendar"),
    path("activities/assignees", AssigneesView.as_view(), name="activity-assignees"),
    path("activity-templates", TemplateListView.as_view(), name="activity-templates"),
    path(
        "activity-templates/<str:key>/apply",
        TemplateApplyView.as_view(),
        name="activity-template-apply",
    ),
    path("", include(router.urls)),
]
