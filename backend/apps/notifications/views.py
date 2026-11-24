"""Notifications API: the bell, the Notifications page and Settings → Notifications.

Everyone sees only their own notifications on the active farm (scope "own")."""

from __future__ import annotations

from typing import Any

from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from apps.accounts.models import Role
from apps.core.views import FarmContextMixin, FarmScopedAPIView

from . import serializers as s
from . import services
from .models import EXTERNAL_CHANNELS, Channel, Notification


class NotificationViewSet(
    FarmContextMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    serializer_class = s.NotificationSerializer
    permission_module = "notifications"
    model = Notification
    throttle_scope = "message_test"  # used only by the test action (ScopedRateThrottle)
    action_permissions = {
        "read": "view",
        "read_all": "view",
        "unread_count": "view",
        "test": "view",
        "usage": "view",
    }

    def get_queryset(self) -> Any:
        if getattr(self, "swagger_fake_view", False):
            return Notification.objects.none()
        qs = (
            self.farm_queryset()
            .filter(recipient=self.request.user, show_in_app=True)
            .prefetch_related("deliveries")
        )
        params = self.request.query_params
        if params.get("unread") in ("1", "true"):
            qs = qs.filter(read_at__isnull=True)
        if params.get("urgent") in ("1", "true"):
            qs = qs.filter(urgent=True)
        if params.get("event_type"):
            qs = qs.filter(event_type=params["event_type"])
        return qs

    @extend_schema(
        parameters=[
            OpenApiParameter("unread", bool),
            OpenApiParameter("urgent", bool),
            OpenApiParameter("event_type", str),
        ]
    )
    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return super().list(request, *args, **kwargs)

    @extend_schema(request=None, responses=s.NotificationSerializer)
    @action(detail=True, methods=["post"])
    def read(self, request: Request, pk: str | None = None) -> Response:
        note = self.get_object()
        if note.read_at is None:
            note.read_at = timezone.now()
            note.save(update_fields=["read_at"])
        return Response(self.get_serializer(note).data)

    @extend_schema(request=None, responses=s.UnreadCountSerializer)
    @action(detail=False, methods=["post"], url_path="read-all")
    def read_all(self, request: Request) -> Response:
        self.get_queryset().filter(read_at__isnull=True).update(read_at=timezone.now())
        return Response({"unread": 0, "urgent": 0})

    @extend_schema(responses=s.UnreadCountSerializer)
    @action(detail=False, methods=["get"], url_path="unread-count")
    def unread_count(self, request: Request) -> Response:
        unread = self.farm_queryset().filter(
            recipient=request.user, show_in_app=True, read_at__isnull=True
        )
        return Response({"unread": unread.count(), "urgent": unread.filter(urgent=True).count()})

    @extend_schema(request=s.TestSendSerializer, responses={201: s.NotificationSerializer})
    @action(detail=False, methods=["post"], throttle_classes=[ScopedRateThrottle])
    def test(self, request: Request) -> Response:
        body = s.TestSendSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        note = services.send_test(request.user, request.farm, body.validated_data["channel"])  # type: ignore[attr-defined]
        note = Notification.objects.prefetch_related("deliveries").get(pk=note.pk)  # type: ignore[union-attr]
        return Response(self.get_serializer(note).data, status=status.HTTP_201_CREATED)

    @extend_schema(responses=s.UsageSerializer(many=True))
    @action(detail=False, methods=["get"])
    def usage(self, request: Request) -> Response:
        if request.membership.role != Role.ADMINISTRATOR:  # type: ignore[attr-defined]
            raise PermissionDenied("Only administrators see message usage.")
        return Response(s.usage_payload(services.usage(request.farm)))  # type: ignore[attr-defined]


class PreferencesView(FarmScopedAPIView):
    """The event × channel matrix and quiet hours / digest / language for the signed-in person."""

    permission_module = "notifications"

    def _data(self, request: Request) -> dict[str, Any]:
        prefs = services.settings_for(request.user, request.farm)  # type: ignore[attr-defined]
        return {
            "matrix": services.matrix(request.user, request.farm),  # type: ignore[attr-defined]
            "settings": s.NotificationSettingsSerializer(prefs).data,
        }

    @extend_schema(responses=s.PreferencesSerializer)
    def get(self, request: Request) -> Response:
        return Response(self._data(request))

    @extend_schema(request=s.PreferencesSerializer, responses=s.PreferencesSerializer)
    def put(self, request: Request) -> Response:
        body = s.PreferencesSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        services.save_matrix(request.user, request.farm, body.validated_data["matrix"])  # type: ignore[attr-defined]
        prefs = services.settings_for(request.user, request.farm)  # type: ignore[attr-defined]
        for key, value in body.validated_data["settings"].items():
            setattr(prefs, key, value)
        prefs.save()
        return Response(self._data(request))


class ContactsView(FarmScopedAPIView):
    """Where the signed-in person receives email, SMS and WhatsApp, and their consent."""

    permission_module = "notifications"

    @extend_schema(responses=s.ContactSerializer(many=True))
    def get(self, request: Request) -> Response:
        rows = [services.contact_for(request.user, c) for c in EXTERNAL_CHANNELS]
        return Response(s.ContactSerializer([r for r in rows if r is not None], many=True).data)


class ContactDetailView(FarmScopedAPIView):
    permission_module = "notifications"

    @extend_schema(request=s.ContactUpdateSerializer, responses=s.ContactSerializer)
    def patch(self, request: Request, channel: str) -> Response:
        if channel not in EXTERNAL_CHANNELS:
            raise NotFound()
        contact = services.contact_for(request.user, channel)
        if contact is None:
            raise NotFound("Add this contact to your profile first.")
        body = s.ContactUpdateSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        now = timezone.now()
        if body.validated_data["opted_in"]:
            contact.opted_out_at = None
            contact.bounced_at = None
            if channel == Channel.WHATSAPP:
                contact.opted_in_at = now
        else:
            contact.opted_out_at = now
        contact.save()
        return Response(s.ContactSerializer(contact).data)
