"""Application factory for the chat API."""

from __future__ import annotations

import base64
import os
import typing

import falcon
import msgspec
from falcon import asgi
from falcon_pachinko import install as install_websockets

if typing.TYPE_CHECKING:  # pragma: no cover - for type checking only
    from sqlalchemy.ext.asyncio import AsyncSession

from .auth import AuthMiddleware, LoginResource
from .chat_service import stream_answer as default_stream_answer
from .errors import handle_http_error, handle_unexpected_error
from .msgspec_support import (
    AsyncMsgspecMiddleware,
    MsgspecWebSocketMiddleware,
    handle_msgspec_validation_error,
    json_handler,
)
from .openrouter_service import OpenRouterService
from .resources import (
    ChatResource,
    ChatStateResource,
    ChatWsPachinkoResource,
    HealthResource,
    OpenRouterTokenResource,
)
from .session import SessionManager


class PachinkoApp(asgi.App):
    """Falcon app subclass with ``falcon-pachinko`` support."""

    __slots__ = ("__dict__",)


def create_app(
    *,
    session_secret: str | None = None,
    session_timeout: int | None = None,
    login_user: str | None = None,
    login_password: str | None = None,
    openrouter_service: OpenRouterService | None = None,
    db_session_factory: typing.Callable[[], AsyncSession] | None = None,
    chat_stream_answer: typing.Callable[
        [OpenRouterService, str, list[typing.Any], typing.Any],
        typing.AsyncIterator[typing.Any],
    ] = default_stream_answer,
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
    db_session_factory:
        Callable that returns an ``AsyncSession``. Required for database access.
    """
    secret = session_secret or os.getenv("SESSION_SECRET")
    if secret is None:
        secret_bytes = os.urandom(32)
        secret = base64.urlsafe_b64encode(secret_bytes).decode()
    timeout = session_timeout or int(os.getenv("SESSION_TIMEOUT", "3600"))
    user = login_user or os.getenv("LOGIN_USER", "admin")
    password = login_password or os.getenv("LOGIN_PASSWORD", "adminpass")
    session = SessionManager(secret, timeout)
    middleware = [
        AuthMiddleware(session),
        AsyncMsgspecMiddleware(),
        MsgspecWebSocketMiddleware(),
    ]
    app = PachinkoApp(middleware=middleware)
    install_websockets(app)
    # Type checker doesn't know about dynamically added methods
    app_with_ws = typing.cast("typing.Any", app)
    app.add_error_handler(falcon.HTTPError, handle_http_error)
    app.add_error_handler(Exception, handle_unexpected_error)
    app.add_error_handler(msgspec.ValidationError, handle_msgspec_validation_error)
    app.req_options.media_handlers["application/json"] = json_handler
    app.resp_options.media_handlers["application/json"] = json_handler
    service = openrouter_service or OpenRouterService.from_env()
    if db_session_factory is None:
        raise ValueError("db_session_factory is required")
    app.add_route(
        "/chat",
        ChatResource(
            service,
            db_session_factory,
            stream_answer_func=chat_stream_answer,
        ),
    )
    app.add_route("/chat/state", ChatStateResource(service, db_session_factory))
    app_with_ws.add_websocket_route(
        "/ws/chat",
        ChatWsPachinkoResource(service, db_session_factory),
    )
    app.add_route("/auth/openrouter-token", OpenRouterTokenResource(db_session_factory))
    app.add_route("/health", HealthResource())
    app.add_route("/login", LoginResource(session, user, password))
    return app
