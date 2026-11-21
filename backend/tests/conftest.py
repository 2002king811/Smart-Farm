from collections.abc import Callable

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Farm, FarmMembership, Role, User
from tests.factories import FarmFactory, MembershipFactory, UserFactory


@pytest.fixture
def farm_a() -> Farm:
    return FarmFactory(name="YPA FARM", slug="ypa-farm")


@pytest.fixture
def farm_b() -> Farm:
    return FarmFactory(name="Other Farm", slug="other-farm")


@pytest.fixture
def member() -> Callable[..., User]:
    def make(farm: Farm, role: str = Role.ADMINISTRATOR, **kwargs: object) -> User:
        membership: FarmMembership = MembershipFactory(farm=farm, role=role, **kwargs)
        return membership.user

    return make


@pytest.fixture
def client_for() -> Callable[..., APIClient]:
    """An API client signed in as ``user`` with X-Farm-ID set to ``farm`` (if given)."""

    def make(user: User | None = None, farm: Farm | None = None) -> APIClient:
        client = APIClient()
        if user is not None:
            client.force_authenticate(user)
        if farm is not None:
            client.credentials(HTTP_X_FARM_ID=str(farm.pk))
        return client

    return make


@pytest.fixture
def admin_a(farm_a: Farm, member: Callable[..., User]) -> User:
    return member(farm_a, Role.ADMINISTRATOR)


@pytest.fixture
def user_factory() -> type[UserFactory]:
    return UserFactory
