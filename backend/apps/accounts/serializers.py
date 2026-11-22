from typing import Any
from zoneinfo import available_timezones

from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from apps.core import regions
from apps.core.context import current_farm_id
from apps.core.permissions import load_matrix

from . import services
from .models import (
    AlertChannel,
    DeliveryChannel,
    Farm,
    FarmMembership,
    HerdSizeBand,
    Invitation,
    LivestockType,
    Role,
    User,
)


class FileUrlField(serializers.ReadOnlyField):
    """URL of a stored file: relative for local storage, signed for S3. Null when empty."""

    def to_representation(self, value: Any) -> str | None:
        return value.url if value else None


class PhoneField(serializers.CharField):
    """Accepts 0772 123 456, 772123456 or +256772123456 and stores E.164.

    A local number gets the prefix of the country in the same form (sign-up), else of the
    active farm, else the platform default."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("max_length", 20)
        super().__init__(**kwargs)

    def _prefix(self) -> str:
        data = getattr(self.parent, "initial_data", None)
        if isinstance(data, dict) and data.get("country"):
            return regions.phone_prefix(str(data["country"]))
        # Editing someone who already has a number: keep its country code.
        existing = getattr(getattr(self.parent, "instance", None), "phone", "") or ""
        for c in regions.COUNTRIES:
            if existing.startswith(c["phone_prefix"]):
                return c["phone_prefix"]
        farm_id = current_farm_id()
        if farm_id:
            code = Farm.objects.filter(pk=farm_id).values_list("country", flat=True).first()
            return regions.phone_prefix(code)
        return regions.phone_prefix(None)

    def to_internal_value(self, data: Any) -> str:
        value = super().to_internal_value(data)
        return services.normalise_phone(value, prefix=self._prefix()) if value else ""


def _password_errors(password: str, user: User | None = None) -> None:
    try:
        validate_password(password, user)
    except Exception as exc:
        raise serializers.ValidationError(list(getattr(exc, "messages", [str(exc)]))) from exc


# --- Me, farms ----------------------------------------------------------------------------------


class FarmSummarySerializer(serializers.ModelSerializer):
    logo = FileUrlField()

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
            "animal_id_prefix",
        )


class MyFarmSerializer(serializers.ModelSerializer):
    """One entry in the sidebar farm switcher, with the role table for that farm."""

    farm = FarmSummarySerializer()
    role_label = serializers.CharField(source="get_role_display")
    permissions = serializers.SerializerMethodField()

    class Meta:
        model = FarmMembership
        fields = (
            "id",
            "farm",
            "role",
            "role_label",
            "status",
            "job_title",
            "joined_at",
            "permissions",
        )

    def get_permissions(self, obj: FarmMembership) -> dict:
        return load_matrix()["roles"].get(obj.role, {})


class MeSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    photo = FileUrlField()

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
            "alert_channels",
            "last_login",
        )
        read_only_fields = fields


class MeUpdateSerializer(serializers.ModelSerializer):
    phone = PhoneField(required=False, allow_blank=True)

    class Meta:
        model = User
        fields = ("first_name", "last_name", "email", "phone", "language")
        extra_kwargs = {"first_name": {"required": False}, "last_name": {"required": False}}

    def update(self, instance: User, validated: dict[str, Any]) -> User:
        changed = services.set_profile_contacts(
            instance, validated.pop("email", None), validated.pop("phone", None)
        )
        for key, value in validated.items():
            setattr(instance, key, value)
        instance.save()
        if "email" in changed:
            services.send_email_verification(instance)
        return instance


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(trim_whitespace=False)
    password = serializers.CharField(trim_whitespace=False, min_length=8)


# --- Auth ---------------------------------------------------------------------------------------


class SignupSerializer(serializers.Serializer):
    # Step 1: account
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    phone = PhoneField()
    password = serializers.CharField(trim_whitespace=False, min_length=8)
    # Step 2: farm
    farm_name = serializers.CharField(max_length=120)
    country = serializers.CharField(max_length=2, required=False, default=regions.DEFAULT_COUNTRY)
    county = serializers.CharField(
        max_length=80, required=False, allow_blank=True, help_text="District / county / region"
    )
    herd_size_band = serializers.ChoiceField(
        choices=HerdSizeBand.choices, required=False, allow_blank=True
    )
    livestock_types = serializers.ListField(
        child=serializers.ChoiceField(choices=LivestockType.choices), allow_empty=False
    )
    job_title = serializers.CharField(max_length=80, required=False, allow_blank=True)
    # Step 3: alert channels (in-app is always on)
    alert_channels = serializers.ListField(
        child=serializers.ChoiceField(choices=AlertChannel.choices), required=False
    )

    def validate_password(self, value: str) -> str:
        _password_errors(value)
        return value

    def validate_country(self, value: str) -> str:
        value = value.upper()
        if not value.isalpha() or len(value) != 2:
            raise serializers.ValidationError("Choose a country.")
        return value

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        problem = regions.validate_region(attrs.get("country", ""), attrs.get("county", ""))
        if problem:
            raise serializers.ValidationError({"county": [problem]})
        return attrs


class LoginSerializer(serializers.Serializer):
    identifier = serializers.CharField(help_text="Username, email or phone number")
    password = serializers.CharField(trim_whitespace=False)
    remember = serializers.BooleanField(default=False)


class AuthResponseSerializer(serializers.Serializer):
    access = serializers.CharField()
    user = MeSerializer()


class TokenSerializer(serializers.Serializer):
    token = serializers.CharField()

    def validate_token(self, value: str) -> str:
        # Copied links sometimes bring a trailing "\\n" or text after a space; keep the token only.
        return value.split("\\n")[0].split()[0] if value.strip() else value


class CodeSerializer(serializers.Serializer):
    code = serializers.RegexField(
        r"^\s*\d{6}\s*$", error_messages={"invalid": "Enter the 6-digit code."}
    )


class ForgotPasswordSerializer(serializers.Serializer):
    identifier = serializers.CharField()
    channel = serializers.ChoiceField(choices=[("email", "Email"), ("sms", "SMS")], default="email")


class ResetPasswordSerializer(serializers.Serializer):
    password = serializers.CharField(trim_whitespace=False, min_length=8)
    token = serializers.CharField(required=False)
    identifier = serializers.CharField(required=False)
    code = serializers.CharField(required=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if not attrs.get("token") and not (attrs.get("identifier") and attrs.get("code")):
            raise serializers.ValidationError(
                "Use the link from the email or the code from the SMS."
            )
        return attrs


class DetailSerializer(serializers.Serializer):
    detail = serializers.CharField()


# --- Farm settings ------------------------------------------------------------------------------

DATE_FORMATS = ["DD MMM YYYY", "DD/MM/YYYY", "MM/DD/YYYY", "YYYY-MM-DD"]


class FarmSerializer(serializers.ModelSerializer):
    logo = FileUrlField()
    phone = PhoneField(required=False, allow_blank=True)
    date_format = serializers.ChoiceField(choices=[(f, f) for f in DATE_FORMATS], required=False)
    livestock_types = serializers.ListField(
        child=serializers.ChoiceField(choices=LivestockType.choices), required=False
    )

    class Meta:
        model = Farm
        fields = (
            "id",
            "name",
            "slug",
            "logo",
            "location",
            "county",
            "country",
            "phone",
            "email",
            "description",
            "herd_size_band",
            "livestock_types",
            "animal_id_prefix",
            "timezone",
            "date_format",
            "currency",
            "weight_unit",
            "language",
            "default_calendar_view",
            "financial_year_start",
            "status",
            "created_at",
        )
        read_only_fields = ("id", "slug", "logo", "status", "created_at")

    def validate_country(self, value: str) -> str:
        value = value.upper()
        if not value.isalpha() or len(value) != 2:
            raise serializers.ValidationError("Choose a country.")
        return value

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        code = attrs.get("country", getattr(self.instance, "country", ""))
        region = attrs.get("county", getattr(self.instance, "county", ""))
        if "country" in attrs or "county" in attrs:
            problem = regions.validate_region(code, region)
            if problem:
                raise serializers.ValidationError({"county": [problem]})
        return attrs

    def validate_timezone(self, value: str) -> str:
        if value not in available_timezones():
            raise serializers.ValidationError("Choose a valid time zone, e.g. Africa/Nairobi.")
        return value

    def validate_currency(self, value: str) -> str:
        if len(value) != 3 or not value.isalpha():
            raise serializers.ValidationError("Use a 3-letter currency code, e.g. KES.")
        return value.upper()

    def validate_financial_year_start(self, value: int) -> int:
        if not 1 <= value <= 12:
            raise serializers.ValidationError("Choose a month from 1 (January) to 12 (December).")
        return value

    def validate_animal_id_prefix(self, value: str) -> str:
        value = value.strip().upper()
        if not value.replace("-", "").isalnum():
            raise serializers.ValidationError("Use letters and numbers only, e.g. YPA.")
        return value


class UploadSerializer(serializers.Serializer):
    file = serializers.FileField()


# --- Members and invitations --------------------------------------------------------------------

CHANNEL_LIST = serializers.ListField(
    child=serializers.ChoiceField(choices=DeliveryChannel.choices), allow_empty=False
)


class MemberSerializer(serializers.ModelSerializer):
    user_id = serializers.UUIDField(source="user.id", read_only=True)
    username = serializers.CharField(source="user.username", read_only=True)
    first_name = serializers.CharField(source="user.first_name", read_only=True)
    last_name = serializers.CharField(source="user.last_name", read_only=True)
    full_name = serializers.CharField(source="user.full_name", read_only=True)
    email = serializers.CharField(source="user.email", read_only=True)
    phone = serializers.CharField(source="user.phone", read_only=True)
    photo = FileUrlField(source="user.photo")
    email_verified = serializers.BooleanField(source="user.email_verified", read_only=True)
    phone_verified = serializers.BooleanField(source="user.phone_verified", read_only=True)
    last_login = serializers.DateTimeField(source="user.last_login", read_only=True)
    role_label = serializers.CharField(source="get_role_display", read_only=True)
    invited_by_name = serializers.SerializerMethodField()

    class Meta:
        model = FarmMembership
        fields = (
            "id",
            "user_id",
            "username",
            "first_name",
            "last_name",
            "full_name",
            "email",
            "phone",
            "photo",
            "email_verified",
            "phone_verified",
            "last_login",
            "role",
            "role_label",
            "status",
            "job_title",
            "joined_at",
            "invited_by_name",
        )
        read_only_fields = ("id", "status", "joined_at")

    def get_invited_by_name(self, obj: FarmMembership) -> str | None:
        return obj.invited_by.full_name if obj.invited_by else None


class MemberUpdateSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=Role.choices, required=False)
    job_title = serializers.CharField(max_length=80, required=False, allow_blank=True)


class MemberCreateSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    email = serializers.EmailField(required=False, allow_blank=True)
    phone = PhoneField(required=False, allow_blank=True)
    username = serializers.RegexField(r"^[\w.@+-]{3,150}$", required=False, allow_blank=True)
    role = serializers.ChoiceField(choices=Role.choices)
    job_title = serializers.CharField(max_length=80, required=False, allow_blank=True)
    channels = CHANNEL_LIST

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if not attrs.get("email") and not attrs.get("phone"):
            raise serializers.ValidationError(
                {"email": ["Add an email address or a mobile number."]}
            )
        return attrs


class MemberCreatedSerializer(serializers.Serializer):
    member = MemberSerializer()
    temporary_password = serializers.CharField()


class ResetMemberPasswordSerializer(serializers.Serializer):
    channels = CHANNEL_LIST


class InvitationSerializer(serializers.ModelSerializer):
    phone = PhoneField(required=False, allow_blank=True)
    role_label = serializers.CharField(source="get_role_display", read_only=True)
    invited_by_name = serializers.SerializerMethodField()
    channels = CHANNEL_LIST

    class Meta:
        model = Invitation
        fields = (
            "id",
            "first_name",
            "last_name",
            "email",
            "phone",
            "role",
            "role_label",
            "channels",
            "status",
            "invited_by_name",
            "expires_at",
            "sent_at",
            "accepted_at",
            "created_at",
        )
        read_only_fields = ("id", "status", "expires_at", "sent_at", "accepted_at", "created_at")
        extra_kwargs = {"email": {"required": False, "allow_blank": True}}

    def get_invited_by_name(self, obj: Invitation) -> str | None:
        return obj.invited_by.full_name if obj.invited_by else None

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if not attrs.get("email") and not attrs.get("phone"):
            raise serializers.ValidationError(
                {"email": ["Add an email address or a mobile number."]}
            )
        return attrs


class InvitationLookupSerializer(serializers.Serializer):
    farm_name = serializers.CharField()
    role = serializers.CharField()
    role_label = serializers.CharField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    email = serializers.CharField()
    phone = serializers.CharField()
    invited_by_name = serializers.CharField(allow_null=True)
    has_account = serializers.BooleanField()


class AcceptInvitationSerializer(serializers.Serializer):
    token = serializers.CharField()
    first_name = serializers.CharField(max_length=150, required=False)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    username = serializers.RegexField(r"^[\w.@+-]{3,150}$", required=False, allow_blank=True)
    password = serializers.CharField(trim_whitespace=False, required=False, min_length=8)


class CountrySerializer(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()
    currency = serializers.CharField()
    phone_prefix = serializers.CharField()
    timezone = serializers.CharField()
    region_label = serializers.CharField()
    regions = serializers.ListField(child=serializers.CharField())
