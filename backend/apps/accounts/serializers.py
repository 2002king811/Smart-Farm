from rest_framework import serializers

from apps.core.permissions import load_matrix

from .models import Farm, FarmMembership, User


class FarmSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Farm
        fields = (
            "id",
            "name",
            "slug",
            "logo",
            "county",
            "country",
            "timezone",
            "currency",
            "weight_unit",
            "language",
            "date_format",
            "default_calendar_view",
            "status",
        )


class MyFarmSerializer(serializers.ModelSerializer):
    """One entry in the sidebar farm switcher, with the role table for that farm."""

    farm = FarmSummarySerializer()
    role_label = serializers.CharField(source="get_role_display")
    permissions = serializers.SerializerMethodField()

    class Meta:
        model = FarmMembership
        fields = ("id", "farm", "role", "role_label", "status", "joined_at", "permissions")

    def get_permissions(self, obj: FarmMembership) -> dict:
        return load_matrix()["roles"].get(obj.role, {})


class MeSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "first_name",
            "last_name",
            "full_name",
            "email",
            "phone",
            "photo",
            "language",
            "email_verified",
            "phone_verified",
            "must_change_password",
        )
        read_only_fields = fields
