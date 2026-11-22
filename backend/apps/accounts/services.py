"""Account rules: sign-up, login and lockout, verification, password reset, invitations and
farm membership management. Views stay thin and call these functions."""

from __future__ import annotations

import contextlib
import re
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.core import signing
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.text import slugify
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from apps.audit.models import AuditAction
from apps.audit.services import record_event
from apps.notifications import messaging

from . import security
from .models import (
    AlertChannel,
    DeliveryChannel,
    Farm,
    FarmMembership,
    Invitation,
    InvitationStatus,
    MembershipStatus,
    OTPCode,
    OTPPurpose,
    PasswordResetToken,
    Role,
    User,
)
from .signals import farm_created

MAX_FAILED_LOGINS = 5
LOCKOUT = timedelta(minutes=15)
CODE_LIFETIME = timedelta(minutes=15)
RESET_LINK_LIFETIME = timedelta(minutes=15)
OTP_RESEND_INTERVAL = timedelta(seconds=60)
INVITATION_LIFETIME = timedelta(days=7)
EMAIL_VERIFY_MAX_AGE = 60 * 60 * 24 * 3  # 3 days
EMAIL_VERIFY_SALT = "smartfarm.verify-email"


# --- Tokens -----------------------------------------------------------------------------------


@dataclass
class IssuedTokens:
    access: str
    refresh: str
    refresh_max_age: int


def issue_tokens(user: User, remember: bool = False) -> IssuedTokens:
    """Access token (15 min) + refresh token (1 day, or 30 days with "Remember me")."""
    refresh = RefreshToken.for_user(user)
    lifetime = (
        settings.JWT_REMEMBER_ME_REFRESH_LIFETIME
        if remember
        else settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"]
    )
    refresh.set_exp(lifetime=lifetime)
    refresh["remember"] = remember
    # The blacklist table records the token's expiry from the outstanding row; keep it in step.
    OutstandingToken.objects.filter(jti=refresh["jti"]).update(expires_at=timezone.now() + lifetime)
    return IssuedTokens(str(refresh.access_token), str(refresh), int(lifetime.total_seconds()))


def rotate_refresh(raw: str) -> tuple[User, IssuedTokens]:
    """Validate a refresh token, blacklist it and issue a new pair with the same lifetime rule."""
    from rest_framework_simplejwt.exceptions import TokenError

    try:
        token = RefreshToken(raw)  # type: ignore[arg-type]  # also rejects blacklisted tokens
    except TokenError as exc:
        raise PermissionDenied("Your session has ended. Please log in again.") from exc
    user = User.objects.filter(pk=token["user_id"], is_active=True).first()
    if user is None:
        raise PermissionDenied("Your session has ended. Please log in again.")
    token.blacklist()
    return user, issue_tokens(user, remember=bool(token.get("remember", False)))


def revoke_refresh_tokens(user: User) -> None:
    """Log the user out everywhere. Access tokens die within 15 minutes; farm access is also
    re-checked on every request, so a deactivated member loses farm data immediately."""
    for token in OutstandingToken.objects.filter(user=user, expires_at__gt=timezone.now()):
        BlacklistedToken.objects.get_or_create(token=token)


# --- Login and lockout --------------------------------------------------------------------------


GENERIC_LOGIN_ERROR = "Incorrect username, email, phone or password."


def find_user(identifier: str) -> User | None:
    identifier = identifier.strip()
    if not identifier:
        return None
    query = Q(username__iexact=identifier) | Q(email__iexact=identifier)
    phone = normalise_phone(identifier, strict=False)
    if phone:
        query |= Q(phone=phone)
    return User.objects.filter(query).first()


def authenticate(identifier: str, password: str) -> User:
    user = find_user(identifier)
    now = timezone.now()
    if user is None:
        raise ValidationError({"detail": [GENERIC_LOGIN_ERROR]})
    if user.locked_until and user.locked_until > now:
        minutes = max(1, int((user.locked_until - now).total_seconds() // 60) + 1)
        raise ValidationError(
            {"detail": [f"Too many failed attempts. Try again in {minutes} minutes."]}
        )
    if not user.check_password(password):
        user.failed_login_count += 1
        if user.failed_login_count >= MAX_FAILED_LOGINS:
            user.failed_login_count = 0
            user.locked_until = now + LOCKOUT
            user.save(update_fields=["failed_login_count", "locked_until"])
            raise ValidationError(
                {"detail": ["Too many failed attempts. Your account is locked for 15 minutes."]}
            )
        user.save(update_fields=["failed_login_count"])
        raise ValidationError({"detail": [GENERIC_LOGIN_ERROR]})
    if not user.is_active:
        raise ValidationError({"detail": ["This account has been deactivated."]})
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login = now
    user.save(update_fields=["failed_login_count", "locked_until", "last_login"])
    return user


# --- Phone numbers and usernames ------------------------------------------------------------------


def normalise_phone(value: str, strict: bool = True) -> str:
    """Kenya-first phone normalisation to E.164: 0712 345 678 → +254712345678."""
    raw = re.sub(r"[\s\-()]", "", value or "")
    if not raw:
        return ""
    if raw.startswith("00"):
        raw = "+" + raw[2:]
    elif raw.startswith("0") and len(raw) == 10:
        raw = settings.DEFAULT_PHONE_REGION + raw[1:]
    elif re.fullmatch(r"[17]\d{8}", raw):
        raw = settings.DEFAULT_PHONE_REGION + raw
    if not re.fullmatch(r"\+[1-9]\d{7,14}", raw):
        if strict:
            raise ValidationError(["Enter a valid mobile number, for example +254712345678."])
        return ""
    return raw


def unique_username(*parts: str) -> str:
    base = ".".join(slugify(p).replace("-", ".") for p in parts if slugify(p))[:30] or "user"
    candidate, n = base, 1
    while User.objects.filter(username__iexact=candidate).exists():
        n += 1
        candidate = f"{base}{n}"
    return candidate


def unique_slug(name: str) -> str:
    base = slugify(name)[:120] or "farm"
    candidate, n = base, 1
    while Farm.objects.filter(slug=candidate).exists():
        n += 1
        candidate = f"{base}-{n}"
    return candidate


def id_prefix_for(name: str) -> str:
    """ "YPA FARM" → "YPA"; "Green Valley Farm" → "GVF"."""
    words = re.findall(r"[A-Za-z0-9]+", name)
    if not words:
        return "FARM"
    if len(words[0]) >= 2 and words[0].isupper():
        return words[0][:6]
    return "".join(w[0] for w in words).upper()[:6]


def ensure_unique_contact(email: str, phone: str, exclude: User | None = None) -> None:
    errors: dict[str, list[str]] = {}
    users = User.objects.exclude(pk=exclude.pk) if exclude else User.objects.all()
    if email and users.filter(email__iexact=email).exists():
        errors["email"] = ["An account with this email already exists."]
    if phone and users.filter(phone=phone).exists():
        errors["phone"] = ["An account with this mobile number already exists."]
    if errors:
        raise ValidationError(errors)


# --- Sign-up ------------------------------------------------------------------------------------


@transaction.atomic
def signup(data: dict[str, Any]) -> tuple[User, Farm]:
    """Creates the user, the farm and an Administrator membership in one transaction."""
    email = data["email"].strip().lower()
    phone = data["phone"]
    ensure_unique_contact(email, phone)
    channels = sorted(set(data.get("alert_channels") or []) | {AlertChannel.IN_APP})

    user = User(
        username=unique_username(email.split("@")[0]),
        first_name=data["first_name"].strip(),
        last_name=data["last_name"].strip(),
        email=email,
        phone=phone,
        alert_channels=channels,
    )
    user.set_password(data["password"])
    user.save()

    farm = Farm.objects.create(
        name=data["farm_name"].strip(),
        slug=unique_slug(data["farm_name"]),
        county=data.get("county", "").strip(),
        herd_size_band=data.get("herd_size_band", ""),
        livestock_types=data.get("livestock_types", []),
        animal_id_prefix=id_prefix_for(data["farm_name"]),
        email=email,
        phone=phone,
    )
    membership = FarmMembership.objects.create(
        user=user, farm=farm, role=Role.ADMINISTRATOR, job_title=data.get("job_title", "")
    )
    record_event(farm.pk, membership, AuditAction.CREATE, None, {"role": membership.role})
    farm_created.send(sender=Farm, farm=farm, created_by=user)

    send_email_verification(user)
    if phone:
        send_phone_code(user, OTPPurpose.VERIFY_PHONE, enforce_interval=False)
    return user, farm


# --- Verification -------------------------------------------------------------------------------


def send_email_verification(user: User) -> None:
    if not user.email or user.email_verified:
        return
    token = signing.dumps({"u": str(user.pk), "e": user.email}, salt=EMAIL_VERIFY_SALT)
    link = f"{settings.FRONTEND_URL}/verify-email?token={token}"
    messaging.queue(
        "email",
        user.email,
        f"Hello {user.first_name},\n\nConfirm your email address for Smart Farm:\n{link}\n\n"
        "This link works for 3 days. If you did not create an account, ignore this email.",
        subject="Confirm your email address",
    )


def verify_email(token: str) -> User:
    try:
        data = signing.loads(token, salt=EMAIL_VERIFY_SALT, max_age=EMAIL_VERIFY_MAX_AGE)
    except signing.SignatureExpired as exc:
        raise ValidationError({"token": ["This link has expired. Request a new one."]}) from exc
    except signing.BadSignature as exc:
        raise ValidationError({"token": ["This link is not valid."]}) from exc
    user = User.objects.filter(pk=data.get("u"), email__iexact=data.get("e", "")).first()
    if user is None:
        raise ValidationError({"token": ["This link is not valid."]})
    if not user.email_verified:
        user.email_verified = True
        user.save(update_fields=["email_verified"])
    return user


def send_phone_code(user: User, purpose: str, enforce_interval: bool = True) -> None:
    if not user.phone:
        raise ValidationError({"phone": ["Add a mobile number first."]})
    latest = OTPCode.objects.filter(user=user, purpose=purpose).order_by("-created_at").first()
    if enforce_interval and latest and timezone.now() - latest.created_at < OTP_RESEND_INTERVAL:
        raise ValidationError({"detail": ["Please wait a minute before asking for a new code."]})
    # Only the newest code is valid.
    OTPCode.objects.filter(user=user, purpose=purpose, used_at__isnull=True).update(
        used_at=timezone.now()
    )
    code = security.new_code()
    otp = OTPCode(
        user=user,
        purpose=purpose,
        destination=user.phone,
        expires_at=timezone.now() + CODE_LIFETIME,
    )
    otp.code_hash = security.hash_code(code, str(otp.pk))
    otp.save()
    action = "verify your phone" if purpose == OTPPurpose.VERIFY_PHONE else "reset your password"
    messaging.queue("sms", user.phone, f"{code} is your Smart Farm code to {action}. Valid 15 min.")


def check_code(user: User, purpose: str, code: str) -> OTPCode:
    # No transaction here: a wrong attempt must be saved even though we then raise.
    otp = (
        OTPCode.objects.filter(user=user, purpose=purpose, used_at__isnull=True)
        .order_by("-created_at")
        .first()
    )
    if otp is None or otp.expires_at < timezone.now():
        raise ValidationError({"code": ["This code has expired. Request a new one."]})
    if otp.attempts >= OTPCode.MAX_ATTEMPTS:
        raise ValidationError({"code": ["Too many wrong attempts. Request a new code."]})
    if not security.codes_match(code, str(otp.pk), otp.code_hash):
        otp.attempts += 1
        otp.save(update_fields=["attempts"])
        left = OTPCode.MAX_ATTEMPTS - otp.attempts
        msg = f"That code is not right. {left} tries left." if left else "Too many wrong attempts."
        raise ValidationError({"code": [msg]})
    otp.used_at = timezone.now()
    otp.save(update_fields=["used_at"])
    return otp


def verify_phone(user: User, code: str) -> None:
    otp = check_code(user, OTPPurpose.VERIFY_PHONE, code)
    if otp.destination != user.phone:
        raise ValidationError({"code": ["Your number changed. Request a new code."]})
    user.phone_verified = True
    user.save(update_fields=["phone_verified"])


# --- Password reset -------------------------------------------------------------------------------

RESET_ACK = "If an account matches, we have sent instructions to reset the password."


def request_password_reset(identifier: str, channel: str) -> None:
    """Never reveals whether an account exists."""
    user = find_user(identifier)
    if user is None or not user.is_active:
        return
    if channel == "sms":
        if user.phone:
            with contextlib.suppress(ValidationError):  # resend interval: stay silent
                send_phone_code(user, OTPPurpose.RESET_PASSWORD)
        return
    if not user.email:
        return
    token = security.new_token()
    PasswordResetToken.objects.create(
        user=user,
        token_hash=security.hash_token(token),
        expires_at=timezone.now() + RESET_LINK_LIFETIME,
    )
    link = f"{settings.FRONTEND_URL}/reset-password?token={token}"
    messaging.queue(
        "email",
        user.email,
        f"Hello {user.first_name},\n\nReset your Smart Farm password with this link:\n{link}\n\n"
        "The link works for 15 minutes. If you did not ask for this, ignore this email.",
        subject="Reset your Smart Farm password",
    )


def _finish_password_change(user: User, password: str) -> None:
    from django.contrib.auth.password_validation import validate_password

    try:
        validate_password(password, user)
    except Exception as exc:  # django ValidationError
        raise ValidationError({"password": list(getattr(exc, "messages", [str(exc)]))}) from exc
    user.set_password(password)
    user.must_change_password = False
    user.failed_login_count = 0
    user.locked_until = None
    user.save()
    revoke_refresh_tokens(user)


@transaction.atomic
def reset_password_with_token(token: str, password: str) -> User:
    row = (
        PasswordResetToken.objects.select_for_update()
        .filter(token_hash=security.hash_token(token), used_at__isnull=True)
        .select_related("user")
        .first()
    )
    if row is None or row.expires_at < timezone.now():
        raise ValidationError({"token": ["This link has expired. Request a new one."]})
    row.used_at = timezone.now()
    row.save(update_fields=["used_at"])
    _finish_password_change(row.user, password)
    return row.user


def reset_password_with_code(identifier: str, code: str, password: str) -> User:
    user = find_user(identifier)
    if user is None:
        raise ValidationError({"code": ["This code has expired. Request a new one."]})
    check_code(user, OTPPurpose.RESET_PASSWORD, code)
    _finish_password_change(user, password)
    return user


def change_password(user: User, current: str, new: str) -> None:
    if not user.check_password(current):
        raise ValidationError({"current_password": ["Your current password is not right."]})
    if current == new:
        raise ValidationError({"password": ["Choose a password you have not used here."]})
    _finish_password_change(user, new)


def set_profile_contacts(user: User, email: str | None, phone: str | None) -> list[str]:
    """Changing email or phone clears its verification and sends a new check."""
    changed = []
    email = email.strip().lower() if email is not None else None
    ensure_unique_contact(email or "", phone or "", exclude=user)
    if email is not None and email != user.email:
        user.email, user.email_verified = email, False
        changed += ["email", "email_verified"]
    if phone is not None and phone != user.phone:
        user.phone, user.phone_verified = phone, False
        changed += ["phone", "phone_verified"]
    return changed


# --- Members and invitations ------------------------------------------------------------------------


def check_channels(actor: User, channels: list[str], email: str, phone: str) -> None:
    errors = []
    if DeliveryChannel.EMAIL in channels and not email:
        errors.append("Add an email address to send by email.")
    if {DeliveryChannel.SMS, DeliveryChannel.WHATSAPP} & set(channels):
        if not phone:
            errors.append("Add a mobile number to send by SMS or WhatsApp.")
        elif not actor.phone_verified:
            errors.append("Verify your own mobile number before sending SMS or WhatsApp.")
    if not channels:
        errors.append("Choose at least one way to send it.")
    if errors:
        raise ValidationError({"channels": errors})


def _send_all(channels: list[str], email: str, phone: str, subject: str, body: str) -> None:
    for channel in channels:
        messaging.queue(channel, email if channel == "email" else phone, body, subject=subject)


def active_admins(farm: Farm) -> Any:
    return FarmMembership.objects.filter(
        farm=farm, role=Role.ADMINISTRATOR, status=MembershipStatus.ACTIVE
    )


def guard_last_admin(
    membership: FarmMembership, new_role: str | None, new_status: str | None
) -> None:
    losing_admin = (
        membership.role == Role.ADMINISTRATOR
        and membership.is_active
        and (
            (new_role is not None and new_role != Role.ADMINISTRATOR)
            or (new_status is not None and new_status != MembershipStatus.ACTIVE)
        )
    )
    if losing_admin and active_admins(membership.farm).exclude(pk=membership.pk).count() == 0:
        raise ValidationError(
            {"detail": ["A farm needs at least one active Administrator. Add another one first."]}
        )


@transaction.atomic
def create_member(farm: Farm, actor: User, data: dict[str, Any]) -> tuple[FarmMembership, str]:
    """Admin creates the account directly with a temporary password and sends login details."""
    email = (data.get("email") or "").strip().lower()
    phone = data.get("phone") or ""
    channels = data["channels"]
    check_channels(actor, channels, email, phone)
    existing = User.objects.filter(
        (Q(email__iexact=email) if email else Q(pk__in=[]))
        | (Q(phone=phone) if phone else Q(pk__in=[]))
    ).first()
    if existing:
        raise ValidationError(
            {"detail": ["This person already has a Smart Farm account. Send them an invitation."]}
        )
    password = security.temporary_password()
    user = User(
        username=data.get("username") or unique_username(data["first_name"], data["last_name"]),
        first_name=data["first_name"].strip(),
        last_name=data["last_name"].strip(),
        email=email,
        phone=phone,
        must_change_password=True,
    )
    if User.objects.filter(username__iexact=user.username).exists():
        raise ValidationError({"username": ["This username is taken."]})
    user.set_password(password)
    user.save()
    membership = FarmMembership.objects.create(
        user=user,
        farm=farm,
        role=data["role"],
        invited_by=actor,
        job_title=data.get("job_title", ""),
    )
    record_event(
        farm.pk,
        membership,
        AuditAction.CREATE,
        None,
        {"role": membership.role, "user": user.username},
    )
    _send_all(
        channels,
        email,
        phone,
        f"Your Smart Farm account for {farm.name}",
        f"Hello {user.first_name}, {actor.full_name} added you to {farm.name} on Smart Farm as "
        f"{membership.get_role_display()}.\nLog in at {settings.FRONTEND_URL}/login\n"
        f"Username: {user.username}\nTemporary password: {password}\n"
        "You will choose your own password when you first log in.",
    )
    return membership, password


@transaction.atomic
def invite(farm: Farm, actor: User, data: dict[str, Any]) -> Invitation:
    email = (data.get("email") or "").strip().lower()
    phone = data.get("phone") or ""
    channels = data["channels"]
    check_channels(actor, channels, email, phone)
    already = FarmMembership.objects.filter(farm=farm).filter(
        (Q(user__email__iexact=email) if email else Q(pk__in=[]))
        | (Q(user__phone=phone) if phone else Q(pk__in=[]))
    )
    if already.exists():
        raise ValidationError({"detail": ["This person is already a member of this farm."]})
    invitation = Invitation(
        farm=farm,
        first_name=data["first_name"].strip(),
        last_name=data.get("last_name", "").strip(),
        email=email,
        phone=phone,
        role=data["role"],
        channels=channels,
        invited_by=actor,
        token_hash="pending",  # noqa: S106 (replaced in send_invitation)
        expires_at=timezone.now() + INVITATION_LIFETIME,
    )
    send_invitation(invitation, actor)
    record_event(
        farm.pk,
        invitation,
        AuditAction.CREATE,
        None,
        {"role": invitation.role, "email": email, "phone": phone},
    )
    return invitation


def send_invitation(invitation: Invitation, actor: User) -> None:
    """(Re)issues the token, saves and sends. Resending invalidates the previous link."""
    token = security.new_token()
    invitation.token_hash = security.hash_token(token)
    invitation.expires_at = timezone.now() + INVITATION_LIFETIME
    invitation.sent_at = timezone.now()
    invitation.save()
    link = f"{settings.FRONTEND_URL}/invite?token={token}"
    _send_all(
        invitation.channels,
        invitation.email,
        invitation.phone,
        f"You're invited to {invitation.farm.name} on Smart Farm",
        f"Hello {invitation.first_name}, {actor.full_name} invited you to join "
        f"{invitation.farm.name} on Smart Farm as {invitation.get_role_display()}.\n"
        f"Accept here: {link}\nThe link works for 7 days.",
    )


def find_invitation(token: str) -> Invitation:
    invitation = (
        Invitation.objects.select_related("farm", "invited_by")
        .filter(token_hash=security.hash_token(token))
        .first()
    )
    if invitation is None or invitation.status == InvitationStatus.REVOKED:
        raise ValidationError({"token": ["This invitation is not valid."]})
    if invitation.status == InvitationStatus.ACCEPTED:
        raise ValidationError({"token": ["This invitation has already been used. Log in instead."]})
    if invitation.expires_at < timezone.now():
        raise ValidationError({"token": ["This invitation has expired. Ask for a new one."]})
    return invitation


def invitation_account(invitation: Invitation) -> User | None:
    query = Q(pk__in=[])
    if invitation.email:
        query |= Q(email__iexact=invitation.email)
    if invitation.phone:
        query |= Q(phone=invitation.phone)
    return User.objects.filter(query).first()


@transaction.atomic
def accept_invitation(token: str, request_user: User | None, data: dict[str, Any]) -> User:
    invitation = find_invitation(token)
    existing = invitation_account(invitation)
    if existing is not None:
        if request_user is None or request_user.pk != existing.pk:
            raise ValidationError(
                {"detail": ["You already have a Smart Farm account. Log in to accept."]}
            )
        user = existing
    else:
        if not data.get("password"):
            raise ValidationError({"password": ["Choose a password."]})
        user = User(
            username=data.get("username")
            or unique_username(invitation.first_name, invitation.last_name),
            first_name=data.get("first_name") or invitation.first_name,
            last_name=data.get("last_name") or invitation.last_name,
            email=invitation.email,
            phone=invitation.phone,
            # The link reached them on this channel, so that contact is proven.
            email_verified=bool(invitation.email) and DeliveryChannel.EMAIL in invitation.channels,
            phone_verified=bool(invitation.phone)
            and bool({DeliveryChannel.SMS, DeliveryChannel.WHATSAPP} & set(invitation.channels)),
        )
        if User.objects.filter(username__iexact=user.username).exists():
            raise ValidationError({"username": ["This username is taken."]})
        from django.contrib.auth.password_validation import validate_password

        try:
            validate_password(data["password"], user)
        except Exception as exc:
            raise ValidationError({"password": list(getattr(exc, "messages", [str(exc)]))}) from exc
        user.set_password(data["password"])
        user.save()

    membership, created = FarmMembership.objects.get_or_create(
        user=user,
        farm=invitation.farm,
        defaults={"role": invitation.role, "invited_by": invitation.invited_by},
    )
    if not created:
        membership.role, membership.status = invitation.role, MembershipStatus.ACTIVE
        membership.save(update_fields=["role", "status", "updated_at"])
    invitation.status = InvitationStatus.ACCEPTED
    invitation.accepted_by = user
    invitation.accepted_at = timezone.now()
    invitation.save(update_fields=["status", "accepted_by", "accepted_at"])
    record_event(
        invitation.farm_id,
        invitation,
        AuditAction.STATUS_CHANGE,
        {"status": InvitationStatus.PENDING},
        {"status": InvitationStatus.ACCEPTED},
    )
    return user


@transaction.atomic
def update_membership(
    membership: FarmMembership, actor: User, data: dict[str, Any]
) -> FarmMembership:
    old = {"role": membership.role, "job_title": membership.job_title}
    if "role" in data and membership.user_id == actor.pk and data["role"] != membership.role:
        raise ValidationError({"role": ["You cannot change your own role."]})
    guard_last_admin(membership, data.get("role"), None)
    for field in ("role", "job_title"):
        if field in data:
            setattr(membership, field, data[field])
    membership.save()
    before = {k: v for k, v in old.items() if getattr(membership, k) != v}
    if before:
        after = {k: getattr(membership, k) for k in before}
        record_event(membership.farm_id, membership, AuditAction.UPDATE, before, after)
    return membership


@transaction.atomic
def set_membership_status(membership: FarmMembership, actor: User, status: str) -> FarmMembership:
    if membership.status == status:
        return membership
    if membership.user_id == actor.pk:
        raise ValidationError({"detail": ["You cannot deactivate yourself."]})
    guard_last_admin(membership, None, status)
    before = {"status": membership.status}
    membership.status = status
    membership.save(update_fields=["status", "updated_at"])
    record_event(
        membership.farm_id, membership, AuditAction.STATUS_CHANGE, before, {"status": status}
    )
    if status == MembershipStatus.INACTIVE:
        user = membership.user
        if not user.memberships.filter(status=MembershipStatus.ACTIVE).exists():
            revoke_refresh_tokens(user)
    return membership


@transaction.atomic
def admin_reset_password(membership: FarmMembership, actor: User, channels: list[str]) -> str:
    user = membership.user
    check_channels(actor, channels, user.email, user.phone)
    password = security.temporary_password()
    user.set_password(password)
    user.must_change_password = True
    user.failed_login_count = 0
    user.locked_until = None
    user.save()
    revoke_refresh_tokens(user)
    record_event(membership.farm_id, membership, AuditAction.UPDATE, None, {"password": "reset"})
    _send_all(
        channels,
        user.email,
        user.phone,
        "Your Smart Farm password was reset",
        f"Hello {user.first_name}, {actor.full_name} reset your Smart Farm password.\n"
        f"Username: {user.username}\nTemporary password: {password}\n"
        f"Log in at {settings.FRONTEND_URL}/login and choose a new password.",
    )
    return password
