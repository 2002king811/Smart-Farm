import factory
from django.contrib.contenttypes.models import ContentType

from apps.accounts.models import Farm, FarmMembership, Role, User
from apps.audit.models import AuditLog
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
    livestock_types = ["goats"]


class MembershipFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = FarmMembership

    user = factory.SubFactory(UserFactory)
    farm = factory.SubFactory(FarmFactory)
    role = Role.ADMINISTRATOR


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


# Every farm-owned model needs an entry here: the tenancy isolation test uses it to create one
# record in each of two farms. Add new models as each phase introduces them.
FACTORY_FOR_MODEL = {
    Pen: PenFactory,
    Goat: GoatFactory,
    AuditLog: AuditLogFactory,
}
