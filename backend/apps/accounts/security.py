"""Tokens and one-time codes. Only hashes are ever stored."""

import hashlib
import hmac
import secrets
import string

from django.conf import settings


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_code() -> str:
    return f"{secrets.randbelow(10**6):06d}"


def hash_code(code: str, salt: str) -> str:
    key = settings.SECRET_KEY.encode()
    return hmac.new(key, f"{salt}:{code}".encode(), hashlib.sha256).hexdigest()


def codes_match(code: str, salt: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_code(code.strip(), salt), stored_hash)


def temporary_password() -> str:
    """Readable temporary password, e.g. "Farm-7kq2-Hm9x". The user must change it."""
    alphabet = string.ascii_letters + string.digits
    alphabet = "".join(c for c in alphabet if c not in "0O1lI")
    part = lambda: "".join(secrets.choice(alphabet) for _ in range(4))  # noqa: E731
    return f"Farm-{part()}-{part()}"
