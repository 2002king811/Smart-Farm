"""Base API views. Every farm-owned endpoint extends FarmScopedViewSet or FarmScopedAPIView."""

from __future__ import annotations

from typing import Any

from django.db import models
from rest_framework import mixins, permissions, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .context import reset_context, set_context
from .permissions import FarmModulePermission, role_scope
from .tenancy import resolve_membership


class FarmContextMixin:
    """Resolves request.farm / request.membership before permission checks run.

    The active farm is also put into the request context, so FarmScopedModel managers
    scope every query in this request, including ones inside serializers and services.
    """

    permission_classes: Any = [permissions.IsAuthenticated, FarmModulePermission]
    permission_module: str | None = None
    action_permissions: dict[str, str] = {}
    model: type[models.Model] | None = None
    _farm_ctx_token: Any = None

    def check_permissions(self, request: Request) -> None:
        if getattr(request.user, "must_change_password", False):
            raise PermissionDenied("Choose a new password before continuing.")
        if request.user and request.user.is_authenticated and not hasattr(request, "membership"):
            membership = resolve_membership(request)
            request.membership = membership  # type: ignore[attr-defined]
            request.farm = membership.farm  # type: ignore[attr-defined]
            self._farm_ctx_token = set_context(farm_id=membership.farm_id, user_id=request.user.pk)
        super().check_permissions(request)  # type: ignore[misc]

    def finalize_response(
        self, request: Request, response: Response, *args: Any, **kwargs: Any
    ) -> Response:
        response = super().finalize_response(request, response, *args, **kwargs)  # type: ignore[misc]
        token = getattr(self, "_farm_ctx_token", None)
        if token is not None:
            reset_context(token)
            self._farm_ctx_token = None
        return response

    def farm_queryset(self) -> models.QuerySet:
        model: Any = self.model or self.queryset.model  # type: ignore[attr-defined]
        if getattr(self, "swagger_fake_view", False):  # OpenAPI schema generation
            return model.objects.none()
        return model.objects.for_farm(self.request.farm)  # type: ignore[attr-defined]

    @property
    def scope(self) -> str | None:
        """'all' or 'own' for the user's role on this module (used by "own tasks" filters)."""
        membership = getattr(self.request, "membership", None)  # type: ignore[attr-defined]
        if membership is None or self.permission_module is None:
            return None
        return role_scope(membership.role, self.permission_module)


class FarmScopedViewSet(FarmContextMixin, viewsets.ModelViewSet):
    """CRUD for a farm-owned model. Queries are filtered by the active farm twice: explicitly
    here and implicitly by the model manager. Deletes are soft deletes."""

    def get_queryset(self) -> models.QuerySet:
        return self.farm_queryset()

    def perform_create(self, serializer: Any) -> None:
        serializer.save(farm=self.request.farm, created_by=self.request.user, updated_by=self.request.user)  # type: ignore[attr-defined]

    def perform_update(self, serializer: Any) -> None:
        serializer.save(updated_by=self.request.user)

    def perform_destroy(self, instance: Any) -> None:
        instance.delete()


class FarmScopedReadOnlyViewSet(
    FarmContextMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    def get_queryset(self) -> models.QuerySet:
        return self.farm_queryset()


class FarmScopedAPIView(FarmContextMixin, APIView):
    """Non-model endpoints (dashboard, reports) that still need the active farm."""
