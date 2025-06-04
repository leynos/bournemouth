"""Application factory for the chat API."""

from __future__ import annotations

import base64
import os

from falcon import asgi

from .auth import AuthMiddleware, LoginResource
from .resources import ChatResource, HealthResource, OpenRouterTokenResource
from .session import SessionManager


def create_app(
    *,
    session_secret: str | None = None,
    session_timeout: int | None = None,
    login_user: str | None = None,
    login_password: str | None = None,
) -> asgi.App:
    """Configure and return the Falcon ASGI app.

    Parameters
    ----------
    session_secret:
        Secret used to sign session cookies. If omitted, ``SESSION_SECRET``
        from the environment is used or a random value is generated.
    session_timeout:
        Cookie expiration in seconds. Defaults to ``SESSION_TIMEOUT`` from the
        environment or ``3600`` seconds.
    login_user:
        Expected Basic Auth username. Defaults to ``LOGIN_USER`` or ``admin``.
    login_password:
        Expected Basic Auth password. Defaults to ``LOGIN_PASSWORD`` or
        ``adminpass``.
    """
    secret = session_secret or os.getenv("SESSION_SECRET")
    if secret is None:
        secret_bytes = os.urandom(32)
        secret = base64.urlsafe_b64encode(secret_bytes).decode()
    timeout = session_timeout or int(os.getenv("SESSION_TIMEOUT", "3600"))
    user = login_user or os.getenv("LOGIN_USER", "admin")
    password = login_password or os.getenv("LOGIN_PASSWORD", "adminpass")
    session = SessionManager(secret, timeout)
    middleware = [AuthMiddleware(session)]
    app = asgi.App(middleware=middleware)
    app.add_route("/chat", ChatResource())
    app.add_route("/auth/openrouter-token", OpenRouterTokenResource())
    app.add_route("/health", HealthResource())
    app.add_route("/login", LoginResource(session, user, password))
    return app
