"""Application factory for the chat API."""

from __future__ import annotations

from falcon import asgi

import os

from .resources import ChatResource, OpenRouterTokenResource, HealthResource
from .auth import AuthMiddleware, LoginResource
from .session import SessionManager


def create_app() -> asgi.App:
    """Configure and return the Falcon ASGI app."""

    secret = os.getenv("SESSION_SECRET", "dev-secret")
    timeout = int(os.getenv("SESSION_TIMEOUT", "3600"))
    login_user = os.getenv("LOGIN_USER", "admin")
    login_password = os.getenv("LOGIN_PASSWORD", "adminpass")

    session = SessionManager(secret, timeout)
    middleware = [AuthMiddleware(session)]
    app = asgi.App(middleware=middleware)

    app.add_route("/chat", ChatResource())
    app.add_route("/auth/openrouter-token", OpenRouterTokenResource())
    app.add_route("/health", HealthResource())
    app.add_route("/login", LoginResource(session, login_user, login_password))
    return app
