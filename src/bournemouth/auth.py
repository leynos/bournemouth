"""Authentication middleware and login resource."""

from __future__ import annotations

import base64
import binascii
import typing
from http import HTTPStatus

import falcon
import falcon.asgi

if typing.TYPE_CHECKING:
    from .session import SessionManager

__all__ = ["AuthMiddleware", "LoginResource"]


class AuthMiddleware:
    """Require a valid session cookie for all routes except health and login."""

    def __init__(self, session: SessionManager) -> None:
        """Create middleware with a session manager.

        Parameters
        ----------
        session : SessionManager
            Object used to verify signed session cookies.
        """
        self._session = session

    async def process_request(self, req: falcon.Request, resp: falcon.Response) -> None:
        """Validate a session cookie for HTTP requests.

        Parameters
        ----------
        req : falcon.Request
            The incoming request.
        resp : falcon.Response
            The outgoing response.

        Raises
        ------
        falcon.HTTPUnauthorized
            If the session cookie is missing or invalid.
        """
        if req.path in {"/health", "/login"}:
            return

        cookie_obj = req.cookies.get("session")
        if not cookie_obj:
            raise falcon.HTTPUnauthorized()

        cookie = typing.cast("str", cookie_obj)  # pyright: ignore[reportUnnecessaryCast]
        user = self._session.verify_cookie(cookie)
        if user is None:
            raise falcon.HTTPUnauthorized()

        req.context["user"] = user

    async def process_request_ws(
        self, req: falcon.Request, ws: falcon.asgi.WebSocket
    ) -> None:
        """Validate a session cookie for WebSocket connections.

        Parameters
        ----------
        req : falcon.Request
            The HTTP request associated with the WebSocket.
        ws : falcon.asgi.WebSocket
            The WebSocket connection.

        Raises
        ------
        falcon.HTTPUnauthorized
            If the session cookie is missing or invalid.
        """
        if req.path in {"/health", "/login"}:
            return

        cookie_obj = req.cookies.get("session")
        if not cookie_obj:
            raise falcon.HTTPUnauthorized()

        cookie = typing.cast("str", cookie_obj)  # pyright: ignore[reportUnnecessaryCast]
        user = self._session.verify_cookie(cookie)
        if user is None:
            raise falcon.HTTPUnauthorized()

        req.context["user"] = user


class LoginResource:
    """Authenticate via Basic Auth and set a signed session cookie."""

    def __init__(self, session: SessionManager, user: str, password: str) -> None:
        """Initialize the resource with credentials and session manager.

        Parameters
        ----------
        session : SessionManager
            Manager used to create signed cookies.
        user : str
            Username permitted to log in.
        password : str
            Password for ``user``.
        """
        self._session = session
        self._user = user
        self._password = password

    async def on_post(self, req: falcon.Request, resp: falcon.Response) -> None:
        """Authenticate using Basic Auth and set a session cookie.

        Parameters
        ----------
        req : falcon.Request
            The incoming request containing the ``Authorization`` header.
        resp : falcon.Response
            The HTTP response object to populate.

        Raises
        ------
        falcon.HTTPUnauthorized
            If credentials are missing or invalid.
        """
        auth_header: str = req.get_header("Authorization") or ""
        prefix = "Basic "
        if not auth_header.startswith(prefix):
            raise falcon.HTTPUnauthorized()

        try:
            encoded = typing.cast("str", auth_header[len(prefix) :])  # pyright: ignore[reportUnnecessaryCast]
            decoded_bytes = base64.b64decode(encoded.encode())
            decoded = decoded_bytes.decode()
            username, password = decoded.split(":", 1)
        except (binascii.Error, ValueError):
            raise falcon.HTTPUnauthorized() from None

        if username != self._user or password != self._password:
            raise falcon.HTTPUnauthorized()

        token = self._session.create_cookie(username)
        resp.set_cookie(
            "session",
            token,
            max_age=self._session.timeout,
            http_only=True,
            same_site="Lax",
        )
        resp.status = HTTPStatus.OK
        resp.media = {"status": "logged_in"}
