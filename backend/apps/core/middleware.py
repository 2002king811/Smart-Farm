import uuid
from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

from .context import reset_context, set_context

REQUEST_ID_HEADER = "HTTP_X_REQUEST_ID"


def client_ip(request: HttpRequest) -> str | None:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


class RequestIDMiddleware:
    """Accepts or creates an X-Request-ID and echoes it back, for log correlation."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        incoming = request.META.get(REQUEST_ID_HEADER, "")
        request_id = incoming[:64] if incoming else uuid.uuid4().hex
        request.request_id = request_id  # type: ignore[attr-defined]
        token = set_context(request_id=request_id, ip=client_ip(request))
        try:
            response = self.get_response(request)
        finally:
            reset_context(token)
        response["X-Request-ID"] = request_id
        return response


class RequestContextMiddleware:
    """Records the session-authenticated user (Django admin). API views set farm and JWT user."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        user = getattr(request, "user", None)
        token = None
        if user is not None and user.is_authenticated:
            token = set_context(user_id=user.pk)
        try:
            return self.get_response(request)
        finally:
            if token is not None:
                reset_context(token)
