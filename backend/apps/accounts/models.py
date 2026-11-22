import uuid

from django.contrib.auth.models import AbstractUser
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.db.models.functions import Lower

from apps.core.validators import e164_validator


class Language(models.TextChoices):
    ENGLISH = "en", "English"
    KISWAHILI = "sw", "Kiswahili"


class AlertChannel(models.TextChoices):
    IN_APP = "in_app", "In-app"
    WHATSAPP = "whatsapp", "WhatsApp"
    SMS = "sms", "SMS"
    EMAIL = "email", "Email"


def default_alert_channels() -> list[str]:
    return [AlertChannel.IN_APP]


class User(AbstractUser):
    """A person. Farm access and role come from FarmMembership, never from the user row."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField("email address", blank=True)
    phone = models.CharField(max_length=16, blank=True, validators=[e164_validator])
    photo = models.ImageField(upload_to="users/photos/", blank=True)
    language = models.CharField(max_length=5, choices=Language.choices, default=Language.ENGLISH)
    email_verified = models.BooleanField(default=False)
    phone_verified = models.BooleanField(default=False)
    must_change_password = models.BooleanField(default=False)
    # Channels chosen at sign-up (step 3). Phase 6 turns these into notification preferences.
    alert_channels = ArrayField(
        models.CharField(max_length=10, choices=AlertChannel.choices),
        default=default_alert_channels,
        blank=True,
    )
    # Login lockout: 5 failed attempts lock the account for 15 minutes.
    failed_login_count = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                Lower("email"), condition=~models.Q(email=""), name="uniq_user_email_ci"
            ),
            models.UniqueConstraint(
                fields=["phone"], condition=~models.Q(phone=""), name="uniq_user_phone"
            ),
        ]

    @property
    def full_name(self) -> str:
        return self.get_full_name() or self.username


class LivestockType(models.TextChoices):
    GOATS = "goats", "Goats"
    SHEEP = "sheep", "Sheep"
    DAIRY_CATTLE = "dairy_cattle", "Dairy cattle"
    BEEF_CATTLE = "beef_cattle", "Beef cattle"
    POULTRY = "poultry", "Poultry"


class CalendarView(models.TextChoices):
    MONTH = "month", "Month"
    WEEK = "week", "Week"
    DAY = "day", "Day"
    AGENDA = "agenda", "Agenda"


class WeightUnit(models.TextChoices):
    KG = "kg", "Kilograms (kg)"
    LB = "lb", "Pounds (lb)"


class HerdSizeBand(models.TextChoices):
    UP_TO_20 = "1-20", "1–20 animals"
    UP_TO_50 = "21-50", "21–50 animals"
    UP_TO_100 = "51-100", "51–100 animals"
    UP_TO_500 = "101-500", "101–500 animals"
    OVER_500 = "500+", "More than 500 animals"


class FarmStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    SUSPENDED = "suspended", "Suspended"


class Farm(models.Model):
    """A tenant. All farm-owned data hangs off this row."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True)
    logo = models.ImageField(upload_to="farms/logos/", blank=True)
    location = models.CharField(max_length=200, blank=True)
    county = models.CharField(max_length=80, blank=True)
    country = models.CharField(max_length=2, default="UG")
    phone = models.CharField(max_length=16, blank=True, validators=[e164_validator])
    email = models.EmailField(blank=True)
    description = models.TextField(blank=True)
    herd_size_band = models.CharField(max_length=10, choices=HerdSizeBand.choices, blank=True)
    livestock_types = ArrayField(
        models.CharField(max_length=20, choices=LivestockType.choices), default=list, blank=True
    )
    animal_id_prefix = models.CharField(
        max_length=10, default="YPA", help_text="Prefix for suggested animal IDs, e.g. YPA-021."
    )
    timezone = models.CharField(max_length=64, default="Africa/Kampala")
    date_format = models.CharField(max_length=20, default="DD MMM YYYY")
    currency = models.CharField(max_length=3, default="UGX")
    weight_unit = models.CharField(max_length=2, choices=WeightUnit.choices, default=WeightUnit.KG)
    language = models.CharField(max_length=5, choices=Language.choices, default=Language.ENGLISH)
    default_calendar_view = models.CharField(
        max_length=10, choices=CalendarView.choices, default=CalendarView.MONTH
    )
    financial_year_start = models.PositiveSmallIntegerField(
        default=1, help_text="Month the financial year starts (1 = January)."
    )
    status = models.CharField(max_length=12, choices=FarmStatus.choices, default=FarmStatus.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


class Role(models.TextChoices):
    ADMINISTRATOR = "administrator", "Administrator"
    FARM_MANAGER = "farm_manager", "Farm Manager"
    LIVESTOCK_ATTENDANT = "livestock_attendant", "Livestock Attendant"


class MembershipStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    INACTIVE = "inactive", "Inactive"


class FarmMembership(models.Model):
    """A user's access to one farm, with a role that applies only on that farm."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="memberships")
    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=24, choices=Role.choices)
    status = models.CharField(
        max_length=10, choices=MembershipStatus.choices, default=MembershipStatus.ACTIVE
    )
    invited_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    job_title = models.CharField(
        max_length=80, blank=True, help_text="The person's role on the farm, e.g. Owner."
    )
    joined_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "farm"], name="uniq_membership")]
        indexes = [models.Index(fields=["farm", "status"])]

    def __str__(self) -> str:
        return f"{self.user} @ {self.farm} ({self.get_role_display()})"

    @property
    def is_active(self) -> bool:
        return self.status == MembershipStatus.ACTIVE


class DeliveryChannel(models.TextChoices):
    EMAIL = "email", "Email"
    SMS = "sms", "SMS"
    WHATSAPP = "whatsapp", "WhatsApp"


class InvitationStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    ACCEPTED = "accepted", "Accepted"
    REVOKED = "revoked", "Revoked"
    EXPIRED = "expired", "Expired"


class Invitation(models.Model):
    """An invite link to join a farm with a role. Only a hash of the token is stored."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name="invitations")
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=16, blank=True, validators=[e164_validator])
    role = models.CharField(max_length=24, choices=Role.choices)
    channels = ArrayField(
        models.CharField(max_length=10, choices=DeliveryChannel.choices), default=list
    )
    token_hash = models.CharField(max_length=64, unique=True)
    status = models.CharField(
        max_length=10, choices=InvitationStatus.choices, default=InvitationStatus.PENDING
    )
    invited_by = models.ForeignKey(
        User, null=True, on_delete=models.SET_NULL, related_name="sent_invitations"
    )
    accepted_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    expires_at = models.DateTimeField()
    sent_at = models.DateTimeField(null=True, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["farm", "status"])]

    def __str__(self) -> str:
        return f"Invitation for {self.first_name} {self.last_name} to {self.farm}"


class OTPPurpose(models.TextChoices):
    VERIFY_PHONE = "verify_phone", "Verify phone"
    RESET_PASSWORD = "reset_password", "Reset password"


class OTPCode(models.Model):
    """A 6-digit code sent by SMS. Stored hashed; expires after 15 minutes; 5 attempts."""

    MAX_ATTEMPTS = 5

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="otp_codes")
    purpose = models.CharField(max_length=20, choices=OTPPurpose.choices)
    destination = models.CharField(max_length=16)
    code_hash = models.CharField(max_length=64)
    attempts = models.PositiveSmallIntegerField(default=0)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["user", "purpose", "created_at"])]

    def __str__(self) -> str:
        return f"{self.get_purpose_display()} code for {self.user}"


class PasswordResetToken(models.Model):
    """A one-time password reset link sent by email. Stored hashed; expires after 15 minutes."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="reset_tokens")
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"Password reset for {self.user}"
