from collections import OrderedDict
from typing import Any

from rest_framework.pagination import CursorPagination
from rest_framework.response import Response


class DefaultCursorPagination(CursorPagination):
    """Cursor pagination plus a total count so tables can show "Showing 1–25 of 140"."""

    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 200
    ordering = "-created_at"

    def paginate_queryset(self, queryset: Any, request: Any, view: Any = None) -> Any:
        self.count = queryset.count()
        return super().paginate_queryset(queryset, request, view)

    def get_paginated_response(self, data: Any) -> Response:
        return Response(
            OrderedDict(
                [
                    ("count", self.count),
                    ("next", self.get_next_link()),
                    ("previous", self.get_previous_link()),
                    ("results", data),
                ]
            )
        )

    def get_paginated_response_schema(self, schema: dict[str, Any]) -> dict[str, Any]:
        base = super().get_paginated_response_schema(schema)
        base["properties"] = {"count": {"type": "integer", "example": 140}, **base["properties"]}
        base["required"] = ["count", "results"]
        return base
