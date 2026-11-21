from typing import Any

from drf_spectacular.openapi import AutoSchema
from drf_spectacular.utils import OpenApiParameter


class FarmAutoSchema(AutoSchema):
    """Documents the X-Farm-ID header on every farm-scoped endpoint."""

    def get_override_parameters(self) -> list[Any]:
        from .views import FarmContextMixin

        params = list(super().get_override_parameters())
        if isinstance(self.view, FarmContextMixin):
            params.append(
                OpenApiParameter(
                    name="X-Farm-ID",
                    type=str,
                    location=OpenApiParameter.HEADER,
                    required=True,
                    description="ID of the active farm. Must be a farm the user belongs to.",
                )
            )
        return params
