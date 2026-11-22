from datetime import timedelta

import factory
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from apps.accounts.models import Farm, FarmMembership, Invitation, Role, User
from apps.accounts.security import hash_token
from apps.audit.models import AuditLog
from apps.breeding.models import Birth, Mating, Mortality
from apps.calendar.models import Activity, ActivityCategory, ActivityNote, ActivityStatusHistory
from apps.health.models import (
    Deworming,
    HealthInspection,
    HealthObservation,
    Medicine,
    ParasiteControl,
    Treatment,
    Vaccination,
    Vaccine,
    VetVisit,
)
from apps.livestock.models import Animal, AnimalGroup, AnimalPhoto, Location, WeightRecord
from apps.notifications.models import (
    Notification,
    NotificationPreference,
    NotificationSettings,
    OutboundMessage,
)
from apps.nutrition.models import (
    FeedingRecord,
    FeedItem,
    FeedStockMovement,
    NutritionAssessment,
    Supplementation,
    WaterHygieneCheck,
)
from apps.reports.models import ReportRun, ReportSchedule
from tests.testapp.models import Goat, Pen


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
        skip_postgeneration_save = True

    username = factory.Sequence(lambda n: f"user{n}")
    first_name = "Test"
    last_name = factory.Sequence(lambda n: f"User{n}")
    email = factory.LazyAttribute(lambda o: f"{o.username}@example.com")
    password = factory.PostGenerationMethodCall("set_password", "Str0ng-pass!")

    @factory.post_generation
    def _save(obj, create, extracted, **kwargs):  # type: ignore[no-untyped-def]
        if create:
            obj.save()


class FarmFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Farm

    name = factory.Sequence(lambda n: f"Farm {n}")
    slug = factory.Sequence(lambda n: f"farm-{n}")
    # The test farms are Kenyan (YPA FARM); Uganda is covered by its own tests.
    country = "KE"
    currency = "KES"
    timezone = "Africa/Nairobi"
    livestock_types = ["goats"]


class MembershipFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = FarmMembership

    user = factory.SubFactory(UserFactory)
    farm = factory.SubFactory(FarmFactory)
    role = Role.ADMINISTRATOR


class InvitationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Invitation

    farm = factory.SubFactory(FarmFactory)
    first_name = "Peter"
    last_name = "Otieno"
    email = factory.Sequence(lambda n: f"invitee{n}@example.com")
    role = Role.LIVESTOCK_ATTENDANT
    channels = ["email"]
    token_hash = factory.Sequence(lambda n: hash_token(f"token-{n}"))
    expires_at = factory.LazyFunction(lambda: timezone.now() + timedelta(days=7))


class PenFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Pen

    farm = factory.SubFactory(FarmFactory)
    name = factory.Sequence(lambda n: f"Pen {n}")


class GoatFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Goat

    farm = factory.SubFactory(FarmFactory)
    name = factory.Sequence(lambda n: f"Goat {n}")


class AuditLogFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = AuditLog

    farm = factory.SubFactory(FarmFactory)
    action = "create"
    content_type = factory.LazyFunction(lambda: ContentType.objects.get_for_model(Farm))
    object_id = factory.Faker("uuid4")
    object_repr = "Something"


class LocationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Location

    farm = factory.SubFactory(FarmFactory)
    name = factory.Sequence(lambda n: f"Paddock {n}")


class AnimalGroupFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = AnimalGroup

    farm = factory.SubFactory(FarmFactory)
    name = factory.Sequence(lambda n: f"Group {n}")


class AnimalFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Animal

    farm = factory.SubFactory(FarmFactory)
    animal_id = factory.Sequence(lambda n: f"YPA-{n + 1:03d}")
    ear_tag = factory.Sequence(lambda n: f"KE{n + 1000}")
    name = factory.Sequence(lambda n: f"Goat {n}")
    sex = "female"
    breed = "Galla"
    date_of_birth = factory.LazyFunction(lambda: timezone.localdate() - timedelta(days=500))


class WeightRecordFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = WeightRecord

    farm = factory.SubFactory(FarmFactory)
    animal = factory.LazyAttribute(lambda o: AnimalFactory(farm=o.farm))
    weight_kg = "32.50"


class AnimalPhotoFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = AnimalPhoto

    farm = factory.SubFactory(FarmFactory)
    animal = factory.LazyAttribute(lambda o: AnimalFactory(farm=o.farm))
    file = factory.django.ImageField(color="green")
    thumbnail = factory.django.ImageField(color="green", width=40, height=40)


def _animal(o):  # type: ignore[no-untyped-def]
    return AnimalFactory(farm=o.farm)


class VaccineFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Vaccine

    farm = factory.SubFactory(FarmFactory)
    name = factory.Sequence(lambda n: f"Vaccine {n}")
    disease_category = "ppr"


class MedicineFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Medicine

    farm = factory.SubFactory(FarmFactory)
    name = factory.Sequence(lambda n: f"Medicine {n}")
    withdrawal_days = 14


class VaccinationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Vaccination

    farm = factory.SubFactory(FarmFactory)
    animal = factory.LazyAttribute(_animal)
    disease_category = "ppr"
    vaccine_name = "PPR vaccine"


class DewormingFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Deworming

    farm = factory.SubFactory(FarmFactory)
    animal = factory.LazyAttribute(_animal)
    product_name = "Albendazole"


class TreatmentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Treatment

    farm = factory.SubFactory(FarmFactory)
    animal = factory.LazyAttribute(_animal)
    diagnosis = "Pneumonia"


class VetVisitFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = VetVisit

    farm = factory.SubFactory(FarmFactory)
    vet_name = "Dr. Samuel Mutua"
    reason = "Routine check"


class HealthObservationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = HealthObservation

    farm = factory.SubFactory(FarmFactory)
    animal = factory.LazyAttribute(_animal)
    symptoms = "Coughing"


class HealthInspectionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = HealthInspection

    farm = factory.SubFactory(FarmFactory)
    inspector = "Grace Wanjiru"


class ParasiteControlFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ParasiteControl

    farm = factory.SubFactory(FarmFactory)
    method = "spraying"
    target = "Ticks"


class ActivityCategoryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ActivityCategory

    farm = factory.SubFactory(FarmFactory)
    name = factory.Sequence(lambda n: f"Category {n}")


class ActivityFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Activity

    farm = factory.SubFactory(FarmFactory)
    title = factory.Sequence(lambda n: f"Task {n}")
    date = factory.LazyFunction(lambda: timezone.localdate() + timedelta(days=3))


class ActivityNoteFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ActivityNote

    farm = factory.SubFactory(FarmFactory)
    activity = factory.LazyAttribute(lambda o: ActivityFactory(farm=o.farm))
    text = "Note"


class ActivityStatusHistoryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ActivityStatusHistory

    farm = factory.SubFactory(FarmFactory)
    activity = factory.LazyAttribute(lambda o: ActivityFactory(farm=o.farm))
    to_status = "completed"


class MatingFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Mating

    farm = factory.SubFactory(FarmFactory)
    doe = factory.LazyAttribute(lambda o: AnimalFactory(farm=o.farm, sex="female"))
    buck = factory.LazyAttribute(lambda o: AnimalFactory(farm=o.farm, sex="male"))
    date = factory.LazyFunction(lambda: timezone.localdate() - timedelta(days=40))


class BirthFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Birth

    farm = factory.SubFactory(FarmFactory)
    dam = factory.LazyAttribute(lambda o: AnimalFactory(farm=o.farm, sex="female"))


class MortalityFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Mortality

    farm = factory.SubFactory(FarmFactory)
    animal = factory.LazyAttribute(lambda o: AnimalFactory(farm=o.farm))
    cause = "Pneumonia"


class KidFactory(AnimalFactory):
    date_of_birth = factory.LazyFunction(lambda: timezone.localdate() - timedelta(days=30))


class FeedItemFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = FeedItem

    farm = factory.SubFactory(FarmFactory)
    name = factory.Sequence(lambda n: f"Feed {n}")
    unit = "kg"


class FeedStockMovementFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = FeedStockMovement

    farm = factory.SubFactory(FarmFactory)
    feed_item = factory.LazyAttribute(lambda o: FeedItemFactory(farm=o.farm))
    kind = "purchase"
    quantity = "100"


class FeedingRecordFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = FeedingRecord

    farm = factory.SubFactory(FarmFactory)
    feed_item = factory.LazyAttribute(lambda o: FeedItemFactory(farm=o.farm))
    quantity = "5"


class NutritionAssessmentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = NutritionAssessment

    farm = factory.SubFactory(FarmFactory)
    findings = "Good condition"


class SupplementationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Supplementation

    farm = factory.SubFactory(FarmFactory)
    supplement = "Mineral lick"


class WaterHygieneCheckFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = WaterHygieneCheck

    farm = factory.SubFactory(FarmFactory)


class NotificationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Notification

    farm = factory.SubFactory(FarmFactory)
    recipient = factory.SubFactory(UserFactory)
    event_type = "test"
    title = "Test message"
    message = "Hello"


class OutboundMessageFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = OutboundMessage

    farm = factory.SubFactory(FarmFactory)
    notification = factory.SubFactory(NotificationFactory, farm=factory.SelfAttribute("..farm"))
    channel = "sms"
    to = "+256772000001"
    template = "test"


class NotificationPreferenceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = NotificationPreference

    farm = factory.SubFactory(FarmFactory)
    user = factory.SubFactory(UserFactory)
    event_type = "activity.overdue"
    channel = "sms"
    enabled = False


class NotificationSettingsFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = NotificationSettings

    farm = factory.SubFactory(FarmFactory)
    user = factory.SubFactory(UserFactory)


class ReportRunFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ReportRun

    farm = factory.SubFactory(FarmFactory)
    report_type = "vaccination"
    date_from = factory.LazyFunction(timezone.localdate)
    date_to = factory.LazyFunction(timezone.localdate)
    format = "pdf"


class ReportScheduleFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ReportSchedule

    farm = factory.SubFactory(FarmFactory)
    report_type = "monthly_activities"
    recipients = ["owner@example.com"]


# Endpoints whose list shows only some rows of a model need a matching factory.
FACTORY_FOR_ROUTE = {"kids": KidFactory}
# Endpoints that list only the signed-in person's rows: {route: field}. The isolation test
# points this field at its user, on both farms.
OWNER_FIELD_FOR_ROUTE = {"notifications": "recipient", "report-runs": "requested_by"}

# Farm-scoped endpoints whose model is not a FarmOwnedModel.
FACTORY_FOR_ENDPOINT_MODEL = {
    FarmMembership: MembershipFactory,
    Invitation: InvitationFactory,
}

# Every farm-owned model needs an entry here: the tenancy isolation test uses it to create one
# record in each of two farms. Add new models as each phase introduces them.
FACTORY_FOR_MODEL = {
    Pen: PenFactory,
    Goat: GoatFactory,
    AuditLog: AuditLogFactory,
    Location: LocationFactory,
    AnimalGroup: AnimalGroupFactory,
    Animal: AnimalFactory,
    WeightRecord: WeightRecordFactory,
    AnimalPhoto: AnimalPhotoFactory,
    Vaccine: VaccineFactory,
    Medicine: MedicineFactory,
    Vaccination: VaccinationFactory,
    Deworming: DewormingFactory,
    Treatment: TreatmentFactory,
    VetVisit: VetVisitFactory,
    HealthObservation: HealthObservationFactory,
    HealthInspection: HealthInspectionFactory,
    ParasiteControl: ParasiteControlFactory,
    ActivityCategory: ActivityCategoryFactory,
    Activity: ActivityFactory,
    ActivityNote: ActivityNoteFactory,
    ActivityStatusHistory: ActivityStatusHistoryFactory,
    Mating: MatingFactory,
    Birth: BirthFactory,
    Mortality: MortalityFactory,
    FeedItem: FeedItemFactory,
    FeedStockMovement: FeedStockMovementFactory,
    FeedingRecord: FeedingRecordFactory,
    NutritionAssessment: NutritionAssessmentFactory,
    Supplementation: SupplementationFactory,
    WaterHygieneCheck: WaterHygieneCheckFactory,
    Notification: NotificationFactory,
    OutboundMessage: OutboundMessageFactory,
    NotificationPreference: NotificationPreferenceFactory,
    NotificationSettings: NotificationSettingsFactory,
    ReportRun: ReportRunFactory,
    ReportSchedule: ReportScheduleFactory,
}
