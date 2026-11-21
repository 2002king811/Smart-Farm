from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.serializers import FarmScopedModelSerializer
from apps.core.views import FarmScopedViewSet

from .models import Goat, Pen


class GoatSerializer(FarmScopedModelSerializer):
    class Meta(FarmScopedModelSerializer.Meta):
        model = Goat
        fields = ("id", "name", "status", "pen", "created_at", "updated_at")


class PenSerializer(FarmScopedModelSerializer):
    class Meta(FarmScopedModelSerializer.Meta):
        model = Pen
        fields = ("id", "name")


class GoatViewSet(FarmScopedViewSet):
    model = Goat
    serializer_class = GoatSerializer
    permission_module = "livestock"
    search_fields = ("name",)
    ordering_fields = ("name", "created_at")
    filterset_fields = ("status",)

    @action(detail=True, methods=["post"], url_path="weights")
    def record_weight(self, request, pk=None):  # type: ignore[no-untyped-def]
        return Response({"ok": True})


class PenViewSet(FarmScopedViewSet):
    model = Pen
    serializer_class = PenSerializer
    permission_module = "livestock"
