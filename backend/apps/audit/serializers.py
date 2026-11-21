from rest_framework import serializers

from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()
    object_type = serializers.CharField(source="content_type.model", read_only=True)

    class Meta:
        model = AuditLog
        fields = (
            "id",
            "at",
            "action",
            "user",
            "user_name",
            "object_type",
            "object_id",
            "object_repr",
            "changed_fields",
            "before",
            "after",
            "ip",
        )
        read_only_fields = fields

    def get_user_name(self, obj: AuditLog) -> str | None:
        return obj.user.full_name if obj.user else None
