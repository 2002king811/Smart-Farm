from typing import Any

from rest_framework.throttling import AnonRateThrottle, SimpleRateThrottle


class AuthIPThrottle(AnonRateThrottle):
    """Per-IP limit on login, sign-up, codes and password reset (signed in or not)."""

    scope = "auth"

    def get_cache_key(self, request: Any, view: Any) -> str:
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class AuthIdentifierThrottle(SimpleRateThrottle):
    """Per-account limit, keyed by the username/email/phone being tried."""

    scope = "auth_identifier"

    def get_cache_key(self, request: Any, view: Any) -> str | None:
        identifier = str(request.data.get("identifier", "")).strip().lower()
        if not identifier:
            return None
        return self.cache_format % {"scope": self.scope, "ident": identifier}
