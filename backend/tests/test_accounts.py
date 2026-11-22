"""Phase 2: sign-up, login, sessions, verification, password reset, members, invitations, farm."""

import re
from datetime import timedelta
from io import BytesIO
from typing import Any

import pytest
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient

from apps.accounts import services
from apps.accounts.models import (
    Farm,
    FarmMembership,
    Invitation,
    InvitationStatus,
    MembershipStatus,
    OTPCode,
    Role,
    User,
)
from apps.audit.models import AuditLog
from apps.notifications import messaging
from tests.factories import MembershipFactory, UserFactory

pytestmark = pytest.mark.django_db

SIGNUP = {
    "first_name": "Daniel",
    "last_name": "Mwangi",
    "email": "Daniel@YPA.co.ke",
    "phone": "0712 345 678",
    "password": "Green-Pasture-27",
    "farm_name": "YPA FARM",
    "county": "Nakuru",
    "herd_size_band": "1-20",
    "livestock_types": ["goats"],
    "job_title": "Owner",
    "alert_channels": ["whatsapp", "email"],
}


def sent(channel: str, to: str | None = None) -> list[messaging.SentMessage]:
    return [m for m in messaging.SENT if m.channel == channel and (to is None or m.to == to)]


def token_in(body: str, param: str = "token") -> str:
    match = re.search(rf"{param}=([\w\-:]+)", body)
    assert match, body
    return match.group(1)


def code_in(body: str) -> str:
    match = re.search(r"\b(\d{6})\b", body)
    assert match, body
    return match.group(1)


def signup(client: APIClient, **overrides: Any) -> Any:
    return client.post("/api/v1/auth/signup", {**SIGNUP, **overrides}, format="json")


def login(client: APIClient, identifier: str, password: str, **extra: Any) -> Any:
    return client.post(
        "/api/v1/auth/login",
        {"identifier": identifier, "password": password, **extra},
        format="json",
    )


def authed(access: str, farm: Farm | None = None) -> APIClient:
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    if farm is not None:
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}", HTTP_X_FARM_ID=str(farm.pk))
    return client


def refresh(client: APIClient) -> Any:
    csrf = client.cookies["sf_csrf"].value
    return client.post("/api/v1/auth/refresh", HTTP_X_CSRF_TOKEN=csrf)


# --- Sign-up ------------------------------------------------------------------------------------


def test_signup_creates_user_farm_and_admin_in_one_go():  # type: ignore[no-untyped-def]
    client = APIClient()
    res = signup(client)
    assert res.status_code == 201, res.content
    body = res.json()
    assert body["access"]
    assert body["user"]["email"] == "daniel@ypa.co.ke"
    assert body["user"]["phone"] == "+254712345678"
    assert body["user"]["alert_channels"] == ["email", "in_app", "whatsapp"]

    user = User.objects.get(email="daniel@ypa.co.ke")
    farm = Farm.objects.get(name="YPA FARM")
    assert farm.animal_id_prefix == "YPA" and farm.county == "Nakuru"
    membership = FarmMembership.objects.get(user=user, farm=farm)
    assert membership.role == Role.ADMINISTRATOR and membership.job_title == "Owner"
    assert user.check_password("Green-Pasture-27")
    assert user.password.startswith("md5") or user.password.startswith("argon2")

    cookie = res.cookies["sf_refresh"]
    assert cookie["httponly"] and cookie["path"] == "/api/v1/auth"
    assert res.cookies["sf_csrf"].value

    # Verification messages go out straight away; the user can use the app meanwhile.
    assert sent("email", "daniel@ypa.co.ke")[0].subject == "Confirm your email address"
    assert len(mail.outbox) == 1
    assert sent("sms", "+254712345678")
    farms = authed(body["access"]).get("/api/v1/me/farms").json()
    assert farms[0]["farm"]["name"] == "YPA FARM" and farms[0]["role"] == "administrator"


def test_signup_sends_farm_created_signal():  # type: ignore[no-untyped-def]
    from apps.accounts.signals import farm_created

    seen = []

    def receiver(sender, farm, created_by, **kwargs):  # type: ignore[no-untyped-def]
        seen.append((farm.name, created_by.email))

    farm_created.connect(receiver)
    try:
        signup(APIClient())
    finally:
        farm_created.disconnect(receiver)
    assert seen == [("YPA FARM", "daniel@ypa.co.ke")]


def test_signup_validation():  # type: ignore[no-untyped-def]
    client = APIClient()
    res = signup(client, password="password", phone="12", livestock_types=[], email="nope")
    assert res.status_code == 400
    errors = res.json()["errors"]
    assert set(errors) >= {"password", "phone", "livestock_types", "email"}
    assert not User.objects.exists() and not Farm.objects.exists()

    assert signup(client).status_code == 201
    dup = signup(client, phone="+254700000001")
    assert dup.status_code == 400
    assert dup.json()["errors"]["email"] == ["An account with this email already exists."]


def test_second_farm_gets_unique_slug():  # type: ignore[no-untyped-def]
    signup(APIClient())
    signup(APIClient(), email="b@example.com", phone="+254700000002")
    assert sorted(Farm.objects.values_list("slug", flat=True)) == ["ypa-farm", "ypa-farm-2"]
    assert services.id_prefix_for("Green Valley Farm") == "GVF"
    assert services.id_prefix_for("!!") == "FARM"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("0712345678", "+254712345678"),
        ("712 345 678", "+254712345678"),
        ("+254 712-345-678", "+254712345678"),
        ("00256712345678", "+256712345678"),
        ("110345678", "+254110345678"),
    ],
)
def test_phone_normalisation(raw, expected):  # type: ignore[no-untyped-def]
    assert services.normalise_phone(raw) == expected


# --- Login, lockout, sessions ---------------------------------------------------------------------


@pytest.fixture
def daniel() -> User:
    user = UserFactory(username="daniel", email="daniel@ypa.co.ke", phone="+254712345678")
    user.set_password("Green-Pasture-27")
    user.save()
    return user


@pytest.mark.parametrize(
    "identifier", ["daniel", "DANIEL@ypa.co.ke", "+254712345678", "0712345678"]
)
def test_login_with_username_email_or_phone(daniel, identifier):  # type: ignore[no-untyped-def]
    res = login(APIClient(), identifier, "Green-Pasture-27")
    assert res.status_code == 200, res.content
    assert res.json()["user"]["username"] == "daniel"


def test_wrong_password_is_generic_then_locks(daniel):  # type: ignore[no-untyped-def]
    client = APIClient()
    unknown = login(client, "nobody", "x").json()["errors"]["detail"]
    for _ in range(4):
        res = login(client, "daniel", "wrong")
        assert res.status_code == 400
        assert res.json()["errors"]["detail"] == unknown  # same message: no account probing
    res = login(client, "daniel", "wrong")
    assert "locked for 15 minutes" in res.json()["errors"]["detail"][0]
    # Even the right password is refused while locked.
    res = login(client, "daniel", "Green-Pasture-27")
    assert res.status_code == 400 and "Try again in" in res.json()["errors"]["detail"][0]
    daniel.refresh_from_db()
    daniel.locked_until = timezone.now() - timedelta(seconds=1)
    daniel.save()
    assert login(client, "daniel", "Green-Pasture-27").status_code == 200


def test_inactive_user_cannot_log_in(daniel):  # type: ignore[no-untyped-def]
    daniel.is_active = False
    daniel.save()
    res = login(APIClient(), "daniel", "Green-Pasture-27")
    assert res.json()["errors"]["detail"] == ["This account has been deactivated."]


def test_login_is_rate_limited_per_identifier(daniel, settings):  # type: ignore[no-untyped-def]
    statuses = [login(APIClient(), "daniel", "wrong").status_code for _ in range(11)]
    assert statuses[-1] == 429


def test_remember_me_sets_30_day_cookie(daniel):  # type: ignore[no-untyped-def]
    short = login(APIClient(), "daniel", "Green-Pasture-27")
    long = login(APIClient(), "daniel", "Green-Pasture-27", remember=True)
    assert short.cookies["sf_refresh"]["max-age"] == 24 * 3600
    assert long.cookies["sf_refresh"]["max-age"] == 30 * 24 * 3600


def test_refresh_rotates_and_needs_csrf(daniel):  # type: ignore[no-untyped-def]
    client = APIClient()
    login(client, "daniel", "Green-Pasture-27", remember=True)
    old = client.cookies["sf_refresh"].value
    assert client.post("/api/v1/auth/refresh").status_code == 403  # no CSRF header
    res = refresh(client)
    assert res.status_code == 200 and res.json()["access"]
    assert res.cookies["sf_refresh"]["max-age"] == 30 * 24 * 3600  # remember-me kept
    # The old refresh token is now blacklisted.
    replay = APIClient()
    replay.cookies["sf_refresh"] = old
    replay.cookies["sf_csrf"] = "x"
    assert replay.post("/api/v1/auth/refresh", HTTP_X_CSRF_TOKEN="x").status_code == 403


def test_logout_revokes_refresh(daniel):  # type: ignore[no-untyped-def]
    client = APIClient()
    login(client, "daniel", "Green-Pasture-27")
    token = client.cookies["sf_refresh"].value
    csrf = client.cookies["sf_csrf"].value
    assert client.post("/api/v1/auth/logout", HTTP_X_CSRF_TOKEN=csrf).status_code == 204
    again = APIClient()
    again.cookies["sf_refresh"] = token
    again.cookies["sf_csrf"] = "y"
    assert again.post("/api/v1/auth/refresh", HTTP_X_CSRF_TOKEN="y").status_code == 403
    assert APIClient().post("/api/v1/auth/logout").status_code == 204


def test_refresh_without_cookie_or_for_inactive_user(daniel):  # type: ignore[no-untyped-def]
    client = APIClient()
    client.cookies["sf_csrf"] = "z"
    assert client.post("/api/v1/auth/refresh", HTTP_X_CSRF_TOKEN="z").status_code == 403
    login(client, "daniel", "Green-Pasture-27")
    User.objects.filter(pk=daniel.pk).update(is_active=False)
    assert refresh(client).status_code == 403


# --- Verification ---------------------------------------------------------------------------------


def test_email_verification_link():  # type: ignore[no-untyped-def]
    res = signup(APIClient())
    token = token_in(sent("email")[0].body)
    assert APIClient().post("/api/v1/auth/verify-email", {"token": "bad"}).status_code == 400
    ok = APIClient().post("/api/v1/auth/verify-email", {"token": token})
    assert ok.status_code == 200
    assert User.objects.get(email="daniel@ypa.co.ke").email_verified
    me = authed(res.json()["access"])
    assert me.post("/api/v1/auth/verify-email/resend").status_code == 200
    assert len(sent("email")) == 1  # already verified: nothing new sent


def test_email_verification_link_expires(daniel, monkeypatch):  # type: ignore[no-untyped-def]
    monkeypatch.setattr(services, "EMAIL_VERIFY_MAX_AGE", -1)
    services.send_email_verification(daniel)
    res = APIClient().post("/api/v1/auth/verify-email", {"token": token_in(sent("email")[0].body)})
    assert res.json()["errors"]["token"] == ["This link has expired. Request a new one."]


def test_phone_verification_with_attempt_limit():  # type: ignore[no-untyped-def]
    access = signup(APIClient()).json()["access"]
    client = authed(access)
    code = code_in(sent("sms")[0].body)
    wrong = "000000" if code != "000000" else "111111"
    res = client.post("/api/v1/auth/verify-phone", {"code": wrong})
    assert res.json()["errors"]["code"] == ["That code is not right. 4 tries left."]
    assert client.post("/api/v1/auth/verify-phone", {"code": "12"}).status_code == 400
    ok = client.post("/api/v1/auth/verify-phone", {"code": code})
    assert ok.status_code == 200 and ok.json()["phone_verified"] is True
    # Codes are single-use.
    assert client.post("/api/v1/auth/verify-phone", {"code": code}).status_code == 400


def test_phone_code_locks_after_five_wrong_tries_and_expires(daniel):  # type: ignore[no-untyped-def]
    services.send_phone_code(daniel, "verify_phone", enforce_interval=False)
    code = code_in(sent("sms")[0].body)
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(5):
        with pytest.raises(Exception):  # noqa: B017
            services.verify_phone(daniel, wrong)
    with pytest.raises(Exception) as exc:
        services.verify_phone(daniel, code)
    assert "Too many wrong attempts" in str(exc.value)

    services.send_phone_code(daniel, "verify_phone", enforce_interval=False)
    OTPCode.objects.filter(user=daniel, used_at__isnull=True).update(
        expires_at=timezone.now() - timedelta(seconds=1)
    )
    with pytest.raises(Exception) as exc:
        services.verify_phone(daniel, code_in(sent("sms")[-1].body))
    assert "expired" in str(exc.value)


def test_phone_code_resend_interval_and_hashing():  # type: ignore[no-untyped-def]
    access = signup(APIClient()).json()["access"]
    client = authed(access)
    res = client.post("/api/v1/auth/verify-phone/send")
    assert res.status_code == 400 and "wait a minute" in res.json()["errors"]["detail"][0]
    otp = OTPCode.objects.get()
    assert code_in(sent("sms")[0].body) not in otp.code_hash
    OTPCode.objects.update(created_at=timezone.now() - timedelta(minutes=2))
    assert client.post("/api/v1/auth/verify-phone/send").status_code == 200


# --- Password reset -------------------------------------------------------------------------------


def test_forgot_password_by_email(daniel):  # type: ignore[no-untyped-def]
    client = APIClient()
    login(client, "daniel", "Green-Pasture-27")
    unknown = APIClient().post("/api/v1/auth/password/forgot", {"identifier": "ghost"})
    res = APIClient().post("/api/v1/auth/password/forgot", {"identifier": "daniel"})
    assert res.json() == unknown.json()  # same answer either way
    token = token_in(sent("email")[0].body)
    bad = APIClient().post("/api/v1/auth/password/reset", {"token": token, "password": "short"})
    assert bad.status_code == 400
    ok = APIClient().post(
        "/api/v1/auth/password/reset", {"token": token, "password": "New-Grazing-Land-9"}
    )
    assert ok.status_code == 200
    assert login(APIClient(), "daniel", "New-Grazing-Land-9").status_code == 200
    # Single use, and other sessions are signed out.
    again = APIClient().post(
        "/api/v1/auth/password/reset", {"token": token, "password": "Other-Field-11x"}
    )
    assert again.status_code == 400
    assert refresh(client).status_code == 403


def test_forgot_password_by_sms_code(daniel):  # type: ignore[no-untyped-def]
    APIClient().post("/api/v1/auth/password/forgot", {"identifier": "0712345678", "channel": "sms"})
    code = code_in(sent("sms")[0].body)
    res = APIClient().post(
        "/api/v1/auth/password/reset",
        {"identifier": "daniel", "code": code, "password": "New-Grazing-Land-9"},
    )
    assert res.status_code == 200, res.content
    assert login(APIClient(), "daniel", "New-Grazing-Land-9").status_code == 200
    missing = APIClient().post("/api/v1/auth/password/reset", {"password": "New-Grazing-Land-9"})
    assert missing.status_code == 400
    ghost = APIClient().post(
        "/api/v1/auth/password/reset",
        {"identifier": "ghost", "code": "123456", "password": "New-Grazing-Land-9"},
    )
    assert ghost.status_code == 400


def test_reset_link_expires(daniel):  # type: ignore[no-untyped-def]
    from apps.accounts.models import PasswordResetToken

    APIClient().post("/api/v1/auth/password/forgot", {"identifier": "daniel"})
    PasswordResetToken.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
    res = APIClient().post(
        "/api/v1/auth/password/reset",
        {"token": token_in(sent("email")[0].body), "password": "New-Grazing-Land-9"},
    )
    assert res.status_code == 400


# --- Me -------------------------------------------------------------------------------------------


def test_profile_update_resets_verification(daniel, client_for):  # type: ignore[no-untyped-def]
    User.objects.filter(pk=daniel.pk).update(email_verified=True, phone_verified=True)
    daniel.refresh_from_db()
    client = client_for(daniel)
    res = client.patch("/api/v1/me", {"first_name": "Dan", "email": "dan@new.ke", "language": "sw"})
    assert res.status_code == 200
    assert res.json()["email_verified"] is False and res.json()["language"] == "sw"
    assert sent("email", "dan@new.ke")
    res = client.patch("/api/v1/me", {"phone": "0700111222"})
    assert res.json()["phone"] == "+254700111222" and res.json()["phone_verified"] is False
    UserFactory(email="taken@x.ke")
    assert client.patch("/api/v1/me", {"email": "TAKEN@x.ke"}).status_code == 400


def test_change_password_clears_forced_change(farm_a, client_for):  # type: ignore[no-untyped-def]
    m = MembershipFactory(farm=farm_a, role=Role.LIVESTOCK_ATTENDANT)
    user = m.user
    user.set_password("Temp-Pass-123")
    user.must_change_password = True
    user.save()
    client = client_for(user, farm_a)
    blocked = client.get("/api/v1/members")
    assert blocked.status_code == 403
    assert blocked.json()["errors"]["detail"] == ["Choose a new password before continuing."]
    wrong = client.post(
        "/api/v1/me/password", {"current_password": "x", "password": "Brand-New-Pass-1"}
    )
    assert wrong.json()["errors"]["current_password"]
    same = client.post(
        "/api/v1/me/password", {"current_password": "Temp-Pass-123", "password": "Temp-Pass-123"}
    )
    assert same.status_code == 400
    ok = client.post(
        "/api/v1/me/password", {"current_password": "Temp-Pass-123", "password": "Brand-New-Pass-1"}
    )
    assert ok.status_code == 200 and ok.json()["user"]["must_change_password"] is False
    assert ok.cookies["sf_refresh"].value
    assert (
        client_for(User.objects.get(pk=user.pk), farm_a).get("/api/v1/test-goats").status_code
        == 200
    )


def _png(size: tuple[int, int] = (1200, 800), fmt: str = "PNG") -> SimpleUploadedFile:
    buf = BytesIO()
    Image.new("RGB", size, "green").save(buf, format=fmt)
    return SimpleUploadedFile(
        f"x.{fmt.lower()}", buf.getvalue(), content_type=f"image/{fmt.lower()}"
    )


def test_profile_photo_upload(daniel, client_for):  # type: ignore[no-untyped-def]
    res = client_for(daniel).post("/api/v1/me/photo", {"file": _png()}, format="multipart")
    assert res.status_code == 200, res.content
    assert res.json()["photo"]


# --- Farm settings ----------------------------------------------------------------------------------


def test_farm_settings_admin_only_and_audited(farm_a, member, client_for):  # type: ignore[no-untyped-def]
    admin = member(farm_a, Role.ADMINISTRATOR)
    manager = member(farm_a, Role.FARM_MANAGER)
    client = client_for(admin, farm_a)
    assert client.get("/api/v1/farm").json()["name"] == "YPA FARM"
    assert client_for(manager, farm_a).get("/api/v1/farm").status_code == 403
    res = client.patch(
        "/api/v1/farm",
        {
            "county": "Nakuru",
            "currency": "kes",
            "timezone": "Africa/Nairobi",
            "animal_id_prefix": "ypa",
        },
    )
    assert res.status_code == 200, res.content
    assert res.json()["currency"] == "KES" and res.json()["animal_id_prefix"] == "YPA"
    bad = client.patch(
        "/api/v1/farm", {"timezone": "Mars/Base", "financial_year_start": 13, "currency": "KE1"}
    )
    assert set(bad.json()["errors"]) == {"timezone", "financial_year_start", "currency"}
    entry = AuditLog.unscoped.filter(farm=farm_a, object_id=str(farm_a.pk)).latest("at")
    assert entry.after == {"county": "Nakuru"} and entry.before == {"county": ""}


def test_farm_logo_upload_strips_exif_and_validates(farm_a, admin_a, client_for):  # type: ignore[no-untyped-def]
    client = client_for(admin_a, farm_a)
    buf = BytesIO()
    image = Image.new("RGB", (900, 600), "green")
    exif = Image.Exif()
    exif[0x8825] = {2: (1.0, 17.0, 0.0)}  # GPS block
    image.save(buf, format="JPEG", exif=exif)
    upload = SimpleUploadedFile("logo.jpg", buf.getvalue(), content_type="image/jpeg")
    res = client.post("/api/v1/farm/logo", {"file": upload}, format="multipart")
    assert res.status_code == 200, res.content
    farm_a.refresh_from_db()
    stored = Image.open(farm_a.logo)
    assert max(stored.size) == 400
    assert not stored.getexif()

    gif = BytesIO()
    Image.new("RGB", (10, 10)).save(gif, format="GIF")
    res = client.post(
        "/api/v1/farm/logo",
        {"file": SimpleUploadedFile("a.gif", gif.getvalue(), content_type="image/gif")},
        format="multipart",
    )
    assert res.json()["errors"]["file"] == ["Upload a JPG, PNG or WebP image."]
    junk = SimpleUploadedFile("a.png", b"not an image", content_type="image/png")
    assert client.post("/api/v1/farm/logo", {"file": junk}, format="multipart").status_code == 400


def test_image_size_limit(monkeypatch):  # type: ignore[no-untyped-def]
    from rest_framework.exceptions import ValidationError

    from apps.core import images

    monkeypatch.setattr(images, "MAX_BYTES", 10)
    with pytest.raises(ValidationError):
        images.process_image(_png())


# --- Members -------------------------------------------------------------------------------------


def test_admin_creates_member_with_temporary_password(farm_a, admin_a, client_for):  # type: ignore[no-untyped-def]
    client = client_for(admin_a, farm_a)
    res = client.post(
        "/api/v1/members",
        {
            "first_name": "Peter",
            "last_name": "Otieno",
            "email": "peter@ypa.co.ke",
            "role": "livestock_attendant",
            "channels": ["email"],
        },
        format="json",
    )
    assert res.status_code == 201, res.content
    temp = res.json()["temporary_password"]
    assert res.json()["member"]["role_label"] == "Livestock Attendant"
    message = sent("email", "peter@ypa.co.ke")[0]
    assert temp in message.body and "peter.otieno" in message.body
    logged_in = login(APIClient(), "peter.otieno", temp)
    assert logged_in.json()["user"]["must_change_password"] is True

    # Existing accounts must be invited instead; members must be reachable.
    dup = client.post(
        "/api/v1/members",
        {
            "first_name": "P",
            "last_name": "O",
            "email": "PETER@ypa.co.ke",
            "role": "farm_manager",
            "channels": ["email"],
        },
        format="json",
    )
    assert "invitation" in dup.json()["errors"]["detail"][0]
    none = client.post(
        "/api/v1/members",
        {"first_name": "A", "last_name": "B", "role": "farm_manager", "channels": ["email"]},
        format="json",
    )
    assert none.json()["errors"]["email"] == ["Add an email address or a mobile number."]


def test_sms_needs_actor_phone_verified(farm_a, admin_a, client_for):  # type: ignore[no-untyped-def]
    client = client_for(admin_a, farm_a)
    payload = {
        "first_name": "Mary",
        "last_name": "Achieng",
        "phone": "0722000111",
        "role": "livestock_attendant",
        "channels": ["sms"],
    }
    res = client.post("/api/v1/members", payload, format="json")
    assert res.json()["errors"]["channels"] == [
        "Verify your own mobile number before sending SMS or WhatsApp."
    ]
    User.objects.filter(pk=admin_a.pk).update(phone_verified=True)
    res = client_for(User.objects.get(pk=admin_a.pk), farm_a).post(
        "/api/v1/members", payload, format="json"
    )
    assert res.status_code == 201
    assert sent("sms", "+254722000111")
    no_email = {**payload, "phone": "0722000999", "channels": ["email"]}
    res = client.post("/api/v1/members", no_email, format="json")
    assert res.json()["errors"]["channels"] == ["Add an email address to send by email."]


def test_only_admins_manage_members(farm_a, member, client_for):  # type: ignore[no-untyped-def]
    manager = member(farm_a, Role.FARM_MANAGER)
    attendant = member(farm_a, Role.LIVESTOCK_ATTENDANT)
    for user in (manager, attendant):
        assert client_for(user, farm_a).get("/api/v1/members").status_code == 403
        assert client_for(user, farm_a).get("/api/v1/invitations").status_code == 403


def test_member_list_filters_and_search(farm_a, admin_a, member, client_for):  # type: ignore[no-untyped-def]
    member(farm_a, Role.FARM_MANAGER, user__first_name="Grace", user__last_name="Wanjiru")
    member(
        farm_a, Role.LIVESTOCK_ATTENDANT, status=MembershipStatus.INACTIVE, user__first_name="Ali"
    )
    client = client_for(admin_a, farm_a)
    assert client.get("/api/v1/members").json()["count"] == 3
    assert (
        client.get("/api/v1/members?role=farm_manager").json()["results"][0]["first_name"]
        == "Grace"
    )
    assert client.get("/api/v1/members?status=inactive").json()["count"] == 1
    assert client.get("/api/v1/members?search=wanj").json()["count"] == 1


def test_deactivate_cuts_access_immediately_and_keeps_records(farm_a, admin_a, member, client_for):  # type: ignore[no-untyped-def]
    attendant = member(farm_a, Role.LIVESTOCK_ATTENDANT)
    attendant.set_password("Field-Hand-2027")
    attendant.save()
    session = APIClient()
    access = login(session, attendant.username, "Field-Hand-2027").json()["access"]
    assert authed(access, farm_a).get("/api/v1/test-goats").status_code == 200

    m = FarmMembership.objects.get(user=attendant)
    admin = client_for(admin_a, farm_a)
    res = admin.post(f"/api/v1/members/{m.pk}/deactivate")
    assert res.status_code == 200 and res.json()["status"] == "inactive"
    # Same (still unexpired) access token: the farm is gone at once, the session can't renew.
    assert authed(access, farm_a).get("/api/v1/test-goats").status_code == 404
    assert refresh(session).status_code == 403
    assert User.objects.filter(pk=attendant.pk).exists()
    assert admin.get("/api/v1/members?status=inactive").json()["count"] == 1

    assert admin.post(f"/api/v1/members/{m.pk}/activate").json()["status"] == "active"
    assert authed(access, farm_a).get("/api/v1/test-goats").status_code == 200


def test_cannot_remove_last_admin_or_self(farm_a, admin_a, member, client_for):  # type: ignore[no-untyped-def]
    own = FarmMembership.objects.get(user=admin_a)
    client = client_for(admin_a, farm_a)
    assert client.post(f"/api/v1/members/{own.pk}/deactivate").status_code == 400
    assert client.patch(f"/api/v1/members/{own.pk}", {"role": "farm_manager"}).status_code == 400

    other_admin = member(farm_a, Role.ADMINISTRATOR)
    other = FarmMembership.objects.get(user=other_admin)
    # other_admin demotes admin_a: allowed while another admin remains…
    c2 = client_for(other_admin, farm_a)
    assert c2.patch(f"/api/v1/members/{own.pk}", {"role": "farm_manager"}).status_code == 200
    # …but admin_a (now a manager) can no longer manage users at all.
    assert client.get("/api/v1/members").status_code == 403
    # and other_admin is the last admin: they can't be demoted by anyone.
    with pytest.raises(Exception):  # noqa: B017
        services.guard_last_admin(other, "farm_manager", None)


def test_role_change_is_audited(farm_a, admin_a, member, client_for):  # type: ignore[no-untyped-def]
    worker = member(farm_a, Role.LIVESTOCK_ATTENDANT)
    m = FarmMembership.objects.get(user=worker)
    res = client_for(admin_a, farm_a).put(
        f"/api/v1/members/{m.pk}", {"role": "farm_manager", "job_title": "Herd manager"}
    )
    assert res.status_code == 200 and res.json()["role"] == "farm_manager"
    entry = AuditLog.unscoped.filter(object_id=str(m.pk)).latest("at")
    assert entry.before == {"role": "livestock_attendant", "job_title": ""}
    assert entry.after == {"role": "farm_manager", "job_title": "Herd manager"}
    assert entry.user == admin_a


def test_admin_resets_member_password(farm_a, admin_a, member, client_for):  # type: ignore[no-untyped-def]
    worker = member(farm_a, Role.LIVESTOCK_ATTENDANT)
    m = FarmMembership.objects.get(user=worker)
    res = client_for(admin_a, farm_a).post(
        f"/api/v1/members/{m.pk}/reset-password", {"channels": ["email"]}, format="json"
    )
    assert res.status_code == 200
    temp = re.search(r"Temporary password: (\S+)", sent("email", worker.email)[0].body).group(1)  # type: ignore[union-attr]
    assert login(APIClient(), worker.username, temp).json()["user"]["must_change_password"]


# --- Invitations ------------------------------------------------------------------------------------


def _invite(client: APIClient, **overrides: Any) -> Any:
    payload = {
        "first_name": "Grace",
        "last_name": "Wanjiru",
        "email": "grace@ypa.co.ke",
        "role": "farm_manager",
        "channels": ["email"],
        **overrides,
    }
    return client.post("/api/v1/invitations", payload, format="json")


def test_invite_lookup_accept_new_person(farm_a, admin_a, client_for):  # type: ignore[no-untyped-def]
    res = _invite(client_for(admin_a, farm_a))
    assert res.status_code == 201, res.content
    assert res.json()["status"] == "pending"
    token = token_in(sent("email", "grace@ypa.co.ke")[0].body)
    assert token not in Invitation.objects.get().token_hash

    info = APIClient().get(f"/api/v1/invitations/lookup?token={token}").json()
    assert info["farm_name"] == "YPA FARM" and info["role_label"] == "Farm Manager"
    assert info["has_account"] is False

    weak = APIClient().post("/api/v1/invitations/accept", {"token": token, "password": "12345678"})
    assert weak.status_code == 400 and "password" in weak.json()["errors"]
    res = APIClient().post(
        "/api/v1/invitations/accept", {"token": token, "password": "Healthy-Herd-2027"}
    )
    assert res.status_code == 200, res.content
    assert res.json()["user"]["email_verified"] is True
    grace = User.objects.get(email="grace@ypa.co.ke")
    assert FarmMembership.objects.get(user=grace, farm=farm_a).role == Role.FARM_MANAGER
    assert Invitation.objects.get().status == InvitationStatus.ACCEPTED
    used = APIClient().get(f"/api/v1/invitations/lookup?token={token}")
    assert "already been used" in used.json()["errors"]["token"][0]


def test_existing_account_accepts_while_logged_in(farm_a, farm_b, admin_a, member, client_for):  # type: ignore[no-untyped-def]
    other = member(farm_b, Role.ADMINISTRATOR, user__email="faith@ypa.co.ke")
    _invite(client_for(admin_a, farm_a), email="faith@ypa.co.ke", role="administrator")
    token = token_in(sent("email", "faith@ypa.co.ke")[0].body)
    assert APIClient().get(f"/api/v1/invitations/lookup?token={token}").json()["has_account"]
    anon = APIClient().post("/api/v1/invitations/accept", {"token": token, "password": "x" * 10})
    assert "Log in to accept" in anon.json()["errors"]["detail"][0]
    wrong_person = client_for(admin_a).post("/api/v1/invitations/accept", {"token": token})
    assert wrong_person.status_code == 400
    ok = client_for(other).post("/api/v1/invitations/accept", {"token": token})
    assert ok.status_code == 200
    roles = {m["farm"]["name"]: m["role"] for m in client_for(other).get("/api/v1/me/farms").json()}
    assert roles == {"YPA FARM": "administrator", "Other Farm": "administrator"}


def test_invitation_resend_revoke_expire(farm_a, admin_a, member, client_for):  # type: ignore[no-untyped-def]
    client = client_for(admin_a, farm_a)
    inv_id = _invite(client).json()["id"]
    first = token_in(sent("email")[0].body)
    assert client.post(f"/api/v1/invitations/{inv_id}/resend").status_code == 200
    second = token_in(sent("email")[1].body)
    assert APIClient().get(f"/api/v1/invitations/lookup?token={first}").status_code == 400
    assert APIClient().get(f"/api/v1/invitations/lookup?token={second}").status_code == 200

    Invitation.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
    expired = APIClient().get(f"/api/v1/invitations/lookup?token={second}")
    assert "expired" in expired.json()["errors"]["token"][0]

    revoked = client.post(f"/api/v1/invitations/{inv_id}/revoke")
    assert revoked.json()["status"] == "revoked"
    assert client.post(f"/api/v1/invitations/{inv_id}/resend").status_code == 400
    assert APIClient().get(f"/api/v1/invitations/lookup?token={second}").status_code == 400

    member(farm_a, Role.FARM_MANAGER, user__email="already@ypa.co.ke")
    dup = _invite(client, email="already@ypa.co.ke")
    assert dup.json()["errors"]["detail"] == ["This person is already a member of this farm."]


# --- The phase 2 "done when" journey ---------------------------------------------------------------


def test_new_farmer_invites_manager_and_attendant_who_see_only_their_role():  # type: ignore[no-untyped-def]
    owner = APIClient()
    access = signup(owner).json()["access"]
    farm = Farm.objects.get()
    admin = authed(access, farm)
    assert _invite(admin).status_code == 201
    assert (
        _invite(
            admin, first_name="Peter", email="peter@ypa.co.ke", role="livestock_attendant"
        ).status_code
        == 201
    )

    def accept(email: str) -> APIClient:
        token = token_in(sent("email", email)[0].body)
        res = APIClient().post(
            "/api/v1/invitations/accept", {"token": token, "password": "Healthy-Herd-2027"}
        )
        return authed(res.json()["access"], farm)

    manager, attendant = accept("grace@ypa.co.ke"), accept("peter@ypa.co.ke")

    expectations = {
        "/api/v1/members": (200, 403, 403),
        "/api/v1/invitations": (200, 403, 403),
        "/api/v1/farm": (200, 403, 403),
        "/api/v1/audit-logs": (200, 403, 403),
        "/api/v1/test-goats": (200, 200, 200),
    }
    for url, codes in expectations.items():
        got = tuple(c.get(url).status_code for c in (admin, manager, attendant))
        assert got == codes, (url, got)

    perms = {
        m["role"]: m["permissions"]
        for c in (manager, attendant)
        for m in c.get("/api/v1/me/farms").json()
    }
    assert "users" not in perms["farm_manager"] and "reports" in perms["farm_manager"]
    assert "reports" not in perms["livestock_attendant"]
    assert admin.get("/api/v1/members").json()["count"] == 3
