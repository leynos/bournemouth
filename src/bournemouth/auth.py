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
        self._session = session

    async def process_request(self, req: falcon.Request, resp: falcon.Response) -> None:
        if req.path in {"/health", "/login"}:
            return

        cookie = req.cookies.get("session")
        if not cookie:
            raise falcon.HTTPUnauthorized()

        user = self._session.verify_cookie(cookie)
        if user is None:
            raise falcon.HTTPUnauthorized()

        req.context["user"] = user

    async def process_request_ws(
        self, req: falcon.Request, ws: falcon.asgi.WebSocket
    ) -> None:
        if req.path in {"/health", "/login"}:
            return

        cookie = req.cookies.get("session")
        if not cookie:
            raise falcon.HTTPUnauthorized()

        user = self._session.verify_cookie(cookie)
        if user is None:
            raise falcon.HTTPUnauthorized()

        req.context["user"] = user


class LoginResource:
    """Authenticate via Basic Auth and set a signed session cookie."""

    def __init__(self, session: SessionManager, user: str, password: str) -> None:
        self._session = session
        self._user = user
        self._password = password

    async def on_post(self, req: falcon.Request, resp: falcon.Response) -> None:
        auth_header = req.get_header("Authorization") or ""
        prefix = "Basic "
        if not auth_header.startswith(prefix):
            raise falcon.HTTPUnauthorized()

        try:
            encoded = auth_header[len(prefix) :]
            decoded_bytes = base64.b64decode(encoded)
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
