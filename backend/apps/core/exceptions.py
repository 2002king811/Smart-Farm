"""One error shape for the whole API: {"errors": {"field": ["message"]}}.

Errors that are not about a field use the key "detail"; serializer non-field errors keep
DRF's "non_field_errors" key so forms can show them above the inputs.
"""

from typing import Any

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list | tuple):
        out: list[str] = []
        for v in value:
            out.extend(_as_list(v) if isinstance(v, list | tuple) else [str(v)])
        return out
    return [str(value)]


def _normalise(data: Any) -> dict[str, Any]:
    if isinstance(data, dict):
        if set(data) == {"detail"}:
            return {"detail": _as_list(data["detail"])}
        result: dict[str, Any] = {}
        for key, value in data.items():
            # Nested serializers keep their structure; leaves are always lists of strings.
            if isinstance(value, dict):
                result[key] = _normalise(value)
            elif isinstance(value, list) and value and isinstance(value[0], dict):
                result[key] = [_normalise(v) for v in value]
            else:
                result[key] = _as_list(value)
        return result
    return {"detail": _as_list(data)}


def exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    if isinstance(exc, DjangoValidationError):
        payload = exc.message_dict if hasattr(exc, "error_dict") else {"detail": exc.messages}
        exc = exceptions.ValidationError(payload)
    elif isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, DjangoPermissionDenied):
        exc = exceptions.PermissionDenied()

    response = drf_exception_handler(exc, context)
    if response is None:
        return None
    response.data = {"errors": _normalise(response.data)}
    if response.status_code == status.HTTP_401_UNAUTHORIZED:
        response.data["errors"].setdefault("detail", ["Authentication required."])
    return response
