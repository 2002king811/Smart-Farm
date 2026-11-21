from apps.core.views import FarmScopedReadOnlyViewSet

from .models import AuditLog
from .serializers import AuditLogSerializer


class AuditLogViewSet(FarmScopedReadOnlyViewSet):
    model = AuditLog
    serializer_class = AuditLogSerializer
    permission_module = "audit"
    filterset_fields = ("action", "object_id", "user")
    search_fields = ("object_repr",)
    ordering_fields = ("at",)
    ordering = ("-at",)

    def get_queryset(self):  # type: ignore[no-untyped-def]
        return super().get_queryset().select_related("user", "content_type")
