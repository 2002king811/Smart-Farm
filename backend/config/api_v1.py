"""All /api/v1/ routes. Each phase registers its viewsets here."""

from django.urls import include, path

from apps.accounts.views import InvitationViewSet, MemberViewSet
from apps.audit.views import AuditLogViewSet
from apps.breeding.views import (
    BirthViewSet,
    KidViewSet,
    MatingViewSet,
    MortalityViewSet,
    PregnancyListView,
)
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
from apps.nutrition.views import (
    FeedingRecordViewSet,
    FeedItemViewSet,
    FeedStockViewSet,
    NutritionAssessmentViewSet,
    NutritionSummaryView,
    SupplementationViewSet,
    WaterHygieneViewSet,
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
router.register("matings", MatingViewSet, basename="mating")
router.register("births", BirthViewSet, basename="birth")
router.register("kids", KidViewSet, basename="kid")
router.register("mortality", MortalityViewSet, basename="mortality")
router.register("feed-items", FeedItemViewSet, basename="feed-item")
router.register("feed-stock", FeedStockViewSet, basename="feed-stock")
router.register("feeding-records", FeedingRecordViewSet, basename="feeding-record")
router.register(
    "nutrition-assessments", NutritionAssessmentViewSet, basename="nutrition-assessment"
)
router.register("supplementation", SupplementationViewSet, basename="supplementation")
router.register("water-hygiene", WaterHygieneViewSet, basename="water-hygiene")

urlpatterns = [
    path("", include("apps.accounts.urls")),
    path("health/summary", HealthSummaryView.as_view(), name="health-summary"),
    path("pregnancies", PregnancyListView.as_view(), name="pregnancies"),
    path("nutrition/summary", NutritionSummaryView.as_view(), name="nutrition-summary"),
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
