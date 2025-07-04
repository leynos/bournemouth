"""Utility for managing signed session cookies."""

from __future__ import annotations

import typing

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

__all__ = ["SessionManager"]


class SessionManager:
    """Create and verify session cookies."""

    def __init__(self, secret: str, timeout: int) -> None:
        """Initialize the manager with a secret and timeout.

        Parameters
        ----------
        secret : str
            Secret key used to sign cookies.
        timeout : int
            Expiration time in seconds.
        """
        self._serializer = URLSafeTimedSerializer(secret)
        self.timeout = timeout

    def create_cookie(self, username: str) -> str:
        """Return a signed cookie value for *username*."""
        return self._serializer.dumps({"u": username})

    def verify_cookie(self, cookie: str) -> str | None:
        """Return the username if *cookie* is valid and not expired."""
        try:
            data = typing.cast(
                "dict[str, typing.Any]",
                self._serializer.loads(cookie, max_age=self.timeout),
            )
        except SignatureExpired:
            return None
        except BadSignature:
            return None
        user = data.get("u")
        if isinstance(user, str):
            return user
        return None
