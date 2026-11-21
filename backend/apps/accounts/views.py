from drf_spectacular.utils import extend_schema
from rest_framework import permissions
from rest_framework.generics import ListAPIView, RetrieveAPIView

from .models import FarmMembership, FarmStatus, MembershipStatus
from .serializers import MeSerializer, MyFarmSerializer


class MeView(RetrieveAPIView):
    """The signed-in user. Not farm-scoped."""

    serializer_class = MeSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):  # type: ignore[no-untyped-def]
        return self.request.user


@extend_schema(summary="Farms the signed-in user can switch to")
class MyFarmsView(ListAPIView):
    serializer_class = MyFarmSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None

    def get_queryset(self):  # type: ignore[no-untyped-def]
        return (
            FarmMembership.objects.select_related("farm")  # type: ignore[misc]
            .filter(
                user_id=self.request.user.pk,
                status=MembershipStatus.ACTIVE,
                farm__status=FarmStatus.ACTIVE,
            )
            .order_by("farm__name")
        )
