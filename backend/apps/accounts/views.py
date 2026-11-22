from __future__ import annotations

import contextlib
import secrets
from typing import Any

from django.conf import settings
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.generics import ListAPIView
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.models import AuditAction
from apps.audit.services import diff, record_event
from apps.core.images import process_image
from apps.core.views import FarmContextMixin

from . import serializers as s
from . import services
from .models import (
    FarmMembership,
    FarmStatus,
    Invitation,
    InvitationStatus,
    MembershipStatus,
    OTPPurpose,
)
from .throttles import AuthIdentifierThrottle, AuthIPThrottle

# --- Cookie helpers -------------------------------------------------------------------------------

REFRESH_COOKIE_PATH = "/api/v1/auth"


def _set_session_cookies(response: Response, tokens: services.IssuedTokens) -> None:
    """Refresh token in an httpOnly cookie; a readable CSRF cookie for the double-submit check."""
    response.set_cookie(
        settings.JWT_REFRESH_COOKIE_NAME,
        tokens.refresh,
        max_age=tokens.refresh_max_age,
        httponly=True,
        secure=settings.JWT_COOKIE_SECURE,
        samesite="Lax",
        path=REFRESH_COOKIE_PATH,
    )
    response.set_cookie(
        settings.JWT_CSRF_COOKIE_NAME,
        secrets.token_urlsafe(24),
        max_age=tokens.refresh_max_age,
        httponly=False,
        secure=settings.JWT_COOKIE_SECURE,
        samesite="Lax",
        path="/",
    )


def _clear_session_cookies(response: Response) -> None:
    response.delete_cookie(settings.JWT_REFRESH_COOKIE_NAME, path=REFRESH_COOKIE_PATH)
    response.delete_cookie(settings.JWT_CSRF_COOKIE_NAME, path="/")


def _check_csrf(request: Request) -> None:
    cookie = request.COOKIES.get(settings.JWT_CSRF_COOKIE_NAME)
    header = request.headers.get("X-CSRF-Token")
    if not cookie or not header or not secrets.compare_digest(cookie, header):
        raise PermissionDenied("Your session has ended. Please log in again.")


def _session_response(user: Any, tokens: services.IssuedTokens, code: int = 200) -> Response:
    response = Response({"access": tokens.access, "user": s.MeSerializer(user).data}, status=code)
    _set_session_cookies(response, tokens)
    return response


class PublicAuthView(APIView):
    authentication_classes: list[Any] = []
    permission_classes = [permissions.AllowAny]
    throttle_classes = [AuthIPThrottle]


# --- Sign-up, login, session ------------------------------------------------------------------------


class SignupView(PublicAuthView):
    @extend_schema(request=s.SignupSerializer, responses={201: s.AuthResponseSerializer})
    def post(self, request: Request) -> Response:
        serializer = s.SignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user, _farm = services.signup(serializer.validated_data)
        return _session_response(user, services.issue_tokens(user), status.HTTP_201_CREATED)


class LoginView(PublicAuthView):
    throttle_classes = [AuthIPThrottle, AuthIdentifierThrottle]

    @extend_schema(request=s.LoginSerializer, responses=s.AuthResponseSerializer)
    def post(self, request: Request) -> Response:
        serializer = s.LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = services.authenticate(data["identifier"], data["password"])
        return _session_response(user, services.issue_tokens(user, remember=data["remember"]))


class RefreshView(PublicAuthView):
    """Swaps the refresh cookie for a new access token (and a rotated refresh cookie)."""

    throttle_classes: list[Any] = []

    @extend_schema(request=None, responses=s.AuthResponseSerializer)
    def post(self, request: Request) -> Response:
        _check_csrf(request)
        raw = request.COOKIES.get(settings.JWT_REFRESH_COOKIE_NAME)
        if not raw:
            raise PermissionDenied("Your session has ended. Please log in again.")
        user, tokens = services.rotate_refresh(raw)
        return _session_response(user, tokens)


class LogoutView(PublicAuthView):
    throttle_classes: list[Any] = []

    @extend_schema(request=None, responses={204: None})
    def post(self, request: Request) -> Response:
        raw = request.COOKIES.get(settings.JWT_REFRESH_COOKIE_NAME)
        if raw:
            _check_csrf(request)
            from rest_framework_simplejwt.exceptions import TokenError
            from rest_framework_simplejwt.tokens import RefreshToken

            with contextlib.suppress(TokenError):
                RefreshToken(raw).blacklist()  # type: ignore[arg-type]
        response = Response(status=status.HTTP_204_NO_CONTENT)
        _clear_session_cookies(response)
        return response


# --- Verification and password reset -------------------------------------------------------------


class VerifyEmailView(PublicAuthView):
    @extend_schema(request=s.TokenSerializer, responses=s.DetailSerializer)
    def post(self, request: Request) -> Response:
        serializer = s.TokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.verify_email(serializer.validated_data["token"])
        return Response({"detail": "Your email address is confirmed."})


class ResendEmailVerificationView(APIView):
    throttle_classes = [AuthIPThrottle]

    @extend_schema(request=None, responses=s.DetailSerializer)
    def post(self, request: Request) -> Response:
        services.send_email_verification(request.user)  # type: ignore[arg-type]
        return Response({"detail": "We have sent a new confirmation link."})


class SendPhoneCodeView(APIView):
    throttle_classes = [AuthIPThrottle]

    @extend_schema(request=None, responses=s.DetailSerializer)
    def post(self, request: Request) -> Response:
        services.send_phone_code(request.user, OTPPurpose.VERIFY_PHONE)  # type: ignore[arg-type]
        return Response({"detail": "We have sent a 6-digit code by SMS."})


class VerifyPhoneView(APIView):
    throttle_classes = [AuthIPThrottle]

    @extend_schema(request=s.CodeSerializer, responses=s.MeSerializer)
    def post(self, request: Request) -> Response:
        serializer = s.CodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.verify_phone(request.user, serializer.validated_data["code"])  # type: ignore[arg-type]
        return Response(s.MeSerializer(request.user).data)


class ForgotPasswordView(PublicAuthView):
    throttle_classes = [AuthIPThrottle, AuthIdentifierThrottle]

    @extend_schema(request=s.ForgotPasswordSerializer, responses=s.DetailSerializer)
    def post(self, request: Request) -> Response:
        serializer = s.ForgotPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.request_password_reset(**serializer.validated_data)
        return Response({"detail": services.RESET_ACK})


class ResetPasswordView(PublicAuthView):
    @extend_schema(request=s.ResetPasswordSerializer, responses=s.DetailSerializer)
    def post(self, request: Request) -> Response:
        serializer = s.ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if data.get("token"):
            services.reset_password_with_token(data["token"], data["password"])
        else:
            services.reset_password_with_code(data["identifier"], data["code"], data["password"])
        return Response({"detail": "Your password has been changed. You can log in now."})


# --- Me ------------------------------------------------------------------------------------------


class MeView(APIView):
    """The signed-in user. Not farm-scoped."""

    @extend_schema(responses=s.MeSerializer)
    def get(self, request: Request) -> Response:
        return Response(s.MeSerializer(request.user).data)

    @extend_schema(request=s.MeUpdateSerializer, responses=s.MeSerializer)
    def patch(self, request: Request) -> Response:
        serializer = s.MeUpdateSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(s.MeSerializer(user).data)


class MePhotoView(APIView):
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(request={"multipart/form-data": s.UploadSerializer}, responses=s.MeSerializer)
    def post(self, request: Request) -> Response:
        serializer = s.UploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        user.photo.save("photo.jpg", process_image(serializer.validated_data["file"]), save=True)  # type: ignore[union-attr]
        return Response(s.MeSerializer(user).data)


class MePasswordView(APIView):
    """Change password. Signs out other devices and returns a fresh session for this one."""

    throttle_classes = [AuthIPThrottle]

    @extend_schema(request=s.ChangePasswordSerializer, responses=s.AuthResponseSerializer)
    def post(self, request: Request) -> Response:
        serializer = s.ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        services.change_password(
            user,  # type: ignore[arg-type]
            serializer.validated_data["current_password"],
            serializer.validated_data["password"],
        )
        return _session_response(user, services.issue_tokens(user))  # type: ignore[arg-type]


@extend_schema(summary="Farms the signed-in user can switch to")
class MyFarmsView(ListAPIView):
    serializer_class = s.MyFarmSerializer
    pagination_class = None

    def get_queryset(self):  # type: ignore[no-untyped-def]
        return (
            FarmMembership.objects.select_related("farm")
            .filter(
                user_id=self.request.user.pk,  # type: ignore[misc]
                status=MembershipStatus.ACTIVE,
                farm__status=FarmStatus.ACTIVE,
            )
            .order_by("farm__name")
        )


# --- Farm settings --------------------------------------------------------------------------------

FARM_FIELDS = [
    f for f in s.FarmSerializer.Meta.fields if f not in s.FarmSerializer.Meta.read_only_fields
]


class FarmView(FarmContextMixin, APIView):
    permission_module = "settings"

    @extend_schema(responses=s.FarmSerializer)
    def get(self, request: Request) -> Response:
        return Response(s.FarmSerializer(request.farm).data)  # type: ignore[attr-defined]

    @extend_schema(request=s.FarmSerializer, responses=s.FarmSerializer)
    def patch(self, request: Request) -> Response:
        farm = request.farm  # type: ignore[attr-defined]
        old = {f: getattr(farm, f) for f in FARM_FIELDS}
        serializer = s.FarmSerializer(farm, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        before, after = diff(farm, old, FARM_FIELDS)
        if before:
            record_event(farm.pk, farm, AuditAction.UPDATE, before, after)
        return Response(serializer.data)


class FarmLogoView(FarmContextMixin, APIView):
    permission_module = "settings"
    parser_classes = [MultiPartParser, FormParser]
    action_permissions = {"create": "update"}

    @extend_schema(request={"multipart/form-data": s.UploadSerializer}, responses=s.FarmSerializer)
    def post(self, request: Request) -> Response:
        serializer = s.UploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        farm = request.farm  # type: ignore[attr-defined]
        farm.logo.save("logo.png", process_image(serializer.validated_data["file"]), save=True)
        record_event(farm.pk, farm, AuditAction.UPDATE, None, {"logo": farm.logo.name})
        return Response(s.FarmSerializer(farm).data)


# --- Members ------------------------------------------------------------------------------------


class MemberViewSet(
    FarmContextMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """User Management. Deactivate rather than delete, so records and history stay intact."""

    model = FarmMembership
    serializer_class = s.MemberSerializer
    permission_module = "users"
    action_permissions = {"deactivate": "update", "activate": "update", "reset_password": "update"}
    filterset_fields = ("role", "status")
    search_fields = (
        "user__first_name",
        "user__last_name",
        "user__email",
        "user__phone",
        "user__username",
    )
    ordering_fields = ("joined_at", "user__first_name", "user__last_name", "role", "status")
    ordering = ("user__first_name", "user__last_name", "id")
    http_method_names = ["get", "post", "put", "patch", "head", "options"]

    def get_queryset(self):  # type: ignore[no-untyped-def]
        if getattr(self, "swagger_fake_view", False):
            return FarmMembership.objects.none()
        return FarmMembership.objects.filter(farm=self.request.farm).select_related(  # type: ignore[attr-defined]
            "user", "invited_by"
        )

    @extend_schema(request=s.MemberCreateSerializer, responses={201: s.MemberCreatedSerializer})
    def create(self, request: Request) -> Response:
        serializer = s.MemberCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        membership, password = services.create_member(
            request.farm, request.user, serializer.validated_data  # type: ignore[attr-defined,arg-type]
        )
        return Response(
            {"member": s.MemberSerializer(membership).data, "temporary_password": password},
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(request=s.MemberUpdateSerializer, responses=s.MemberSerializer)
    def partial_update(self, request: Request, pk: str | None = None) -> Response:
        serializer = s.MemberUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        membership = services.update_membership(
            self.get_object(), request.user, serializer.validated_data  # type: ignore[arg-type]
        )
        return Response(s.MemberSerializer(membership).data)

    def update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return self.partial_update(request, kwargs.get("pk"))

    @extend_schema(request=None, responses=s.MemberSerializer)
    @action(detail=True, methods=["post"])
    def deactivate(self, request: Request, pk: str | None = None) -> Response:
        m = services.set_membership_status(self.get_object(), request.user, MembershipStatus.INACTIVE)  # type: ignore[arg-type]
        return Response(s.MemberSerializer(m).data)

    @extend_schema(request=None, responses=s.MemberSerializer)
    @action(detail=True, methods=["post"])
    def activate(self, request: Request, pk: str | None = None) -> Response:
        m = services.set_membership_status(self.get_object(), request.user, MembershipStatus.ACTIVE)  # type: ignore[arg-type]
        return Response(s.MemberSerializer(m).data)

    @extend_schema(request=s.ResetMemberPasswordSerializer, responses=s.DetailSerializer)
    @action(detail=True, methods=["post"], url_path="reset-password")
    def reset_password(self, request: Request, pk: str | None = None) -> Response:
        serializer = s.ResetMemberPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.admin_reset_password(
            self.get_object(), request.user, serializer.validated_data["channels"]  # type: ignore[arg-type]
        )
        return Response({"detail": "A temporary password has been sent."})


# --- Invitations ----------------------------------------------------------------------------------


class InvitationViewSet(
    FarmContextMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    model = Invitation
    serializer_class = s.InvitationSerializer
    permission_module = "users"
    action_permissions = {"resend": "create", "revoke": "update"}
    filterset_fields = ("status", "role")
    search_fields = ("first_name", "last_name", "email", "phone")
    ordering = ("-created_at",)

    def get_queryset(self):  # type: ignore[no-untyped-def]
        if getattr(self, "swagger_fake_view", False):
            return Invitation.objects.none()
        return Invitation.objects.filter(farm=self.request.farm).select_related("invited_by", "farm")  # type: ignore[attr-defined]

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invitation = services.invite(request.farm, request.user, serializer.validated_data)  # type: ignore[attr-defined,arg-type]
        return Response(s.InvitationSerializer(invitation).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=None, responses=s.InvitationSerializer)
    @action(detail=True, methods=["post"])
    def resend(self, request: Request, pk: str | None = None) -> Response:
        invitation = self.get_object()
        if invitation.status not in (InvitationStatus.PENDING, InvitationStatus.EXPIRED):
            return Response(
                {"errors": {"detail": ["Only pending invitations can be resent."]}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        services.check_channels(request.user, invitation.channels, invitation.email, invitation.phone)  # type: ignore[arg-type]
        invitation.status = InvitationStatus.PENDING
        services.send_invitation(invitation, request.user)  # type: ignore[arg-type]
        return Response(s.InvitationSerializer(invitation).data)

    @extend_schema(request=None, responses=s.InvitationSerializer)
    @action(detail=True, methods=["post"])
    def revoke(self, request: Request, pk: str | None = None) -> Response:
        invitation = self.get_object()
        if invitation.status == InvitationStatus.PENDING:
            invitation.status = InvitationStatus.REVOKED
            invitation.save(update_fields=["status"])
            record_event(
                invitation.farm_id,
                invitation,
                AuditAction.STATUS_CHANGE,
                {"status": InvitationStatus.PENDING},
                {"status": InvitationStatus.REVOKED},
            )
        return Response(s.InvitationSerializer(invitation).data)


class InvitationLookupView(PublicAuthView):
    """What the invite page shows before accepting: farm, role, who invited you."""

    @extend_schema(parameters=[], responses=s.InvitationLookupSerializer)
    def get(self, request: Request) -> Response:
        invitation = services.find_invitation(request.query_params.get("token", ""))
        return Response(
            {
                "farm_name": invitation.farm.name,
                "role": invitation.role,
                "role_label": invitation.get_role_display(),
                "first_name": invitation.first_name,
                "last_name": invitation.last_name,
                "email": invitation.email,
                "phone": invitation.phone,
                "invited_by_name": (
                    invitation.invited_by.full_name if invitation.invited_by else None
                ),
                "has_account": services.invitation_account(invitation) is not None,
            }
        )


class AcceptInvitationView(APIView):
    """New people choose a password here; people with an account accept while logged in."""

    permission_classes = [permissions.AllowAny]
    throttle_classes = [AuthIPThrottle]

    @extend_schema(request=s.AcceptInvitationSerializer, responses=s.AuthResponseSerializer)
    def post(self, request: Request) -> Response:
        serializer = s.AcceptInvitationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        current = request.user if request.user.is_authenticated else None
        user = services.accept_invitation(data.pop("token"), current, data)  # type: ignore[arg-type]
        return _session_response(user, services.issue_tokens(user))
