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


CSP = (
    "default-src 'self'; img-src 'self' data: blob: https:; style-src 'self' 'unsafe-inline'; "
    "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
)


class SecurityHeadersMiddleware:
    """Content Security Policy and related headers for everything Django serves (the API,
    the platform admin, the dev outbox). The web app's own headers are set by Nginx."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        response.headers.setdefault("Content-Security-Policy", CSP)
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault(
            "Permissions-Policy", "geolocation=(), microphone=(), camera=(self)"
        )
        return response


class IdempotencyMiddleware:
    """Offline sync: the phone app sends each queued change with an ``Idempotency-Key``.
    If the same change arrives twice (the first answer was lost on a bad connection), the
    saved answer is returned instead of saving it again. Kept for 24 hours."""

    HEADER = "HTTP_IDEMPOTENCY_KEY"
    TTL = 24 * 3600

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        from django.core.cache import cache

        key = request.META.get(self.HEADER, "")
        if (
            not key
            or request.method not in ("POST", "PATCH", "PUT")
            or not request.path.startswith("/api/")
        ):
            return self.get_response(request)
        cache_key = f"idem:{request.META.get('HTTP_X_FARM_ID', '')}:{request.path}:{key[:80]}"
        saved = cache.get(cache_key)
        if saved is not None:
            response = HttpResponse(
                saved["body"], status=saved["status"], content_type=saved["type"]
            )
            response["Idempotent-Replay"] = "true"
            return response
        response = self.get_response(request)
        if 200 <= response.status_code < 300 and not getattr(response, "streaming", False):
            cache.set(
                cache_key,
                {
                    "body": response.content,
                    "status": response.status_code,
                    "type": response.get("Content-Type", ""),
                },
                self.TTL,
            )
        return response
