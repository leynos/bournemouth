"""Falcon resource classes for the chat API."""

from __future__ import annotations

import typing

import falcon
import msgspec
from sqlalchemy import select

if typing.TYPE_CHECKING:  # pragma: no cover
    from sqlalchemy.orm import Session

from .models import UserAccount
from .openrouter import ChatMessage, Role
from .openrouter_service import (
    OpenRouterService,
    OpenRouterServiceBadGatewayError,
    OpenRouterServiceTimeoutError,
    chat_with_service,
)


class ChatRequest(msgspec.Struct):
    """Request body for the chat endpoint."""

    message: str
    history: list[dict[str, typing.Any]] | None = None
    model: str | None = None


class ChatResource:
    """Handle chat requests."""

    def __init__(
        self, service: OpenRouterService, session_factory: typing.Callable[[], Session]
    ) -> None:
        self._service = service
        self._session_factory = session_factory

    async def on_post(self, req: falcon.Request, resp: falcon.Response) -> None:
        raw = await typing.cast(typing.Awaitable[bytes], req.bounded_stream.read())
        try:
            data = msgspec.json.decode(raw)
        except msgspec.DecodeError:
            raise falcon.HTTPBadRequest(description="invalid JSON") from None

        match data:
            case {"message": str(msg), **extra}:
                pass
            case _:
                raise falcon.HTTPBadRequest(description="`message` field required")
        history: list[ChatMessage] = []
        if isinstance(extra.get("history"), list):
            valid_roles = typing.get_args(Role)
            for item in extra["history"]:
                match item:
                    case {"role": role, "content": str(content)} if role in valid_roles:
                        history.append(ChatMessage(role=typing.cast(Role, role), content=content))
                    case _:
                        raise falcon.HTTPBadRequest(description="invalid history item")

        history.append(ChatMessage(role="user", content=msg))

        model = typing.cast("str | None", extra.get("model"))

        with self._session_factory() as session:
            stmt = select(UserAccount.openrouter_token_enc).where(
                UserAccount.google_sub == typing.cast("str", req.context["user"])
            )
            token = typing.cast(bytes | str | None, session.scalar(stmt))
        if not token:
            raise falcon.HTTPBadRequest(description="missing OpenRouter token")

        if isinstance(token, bytes):
            api_key = token.decode()
        else:
            api_key = token

        try:
            completion = await chat_with_service(
                self._service,
                api_key,
                history,
                model=model,
            )
        except OpenRouterServiceTimeoutError:
            raise falcon.HTTPGatewayTimeout() from None
        except OpenRouterServiceBadGatewayError as exc:
            raise falcon.HTTPBadGateway(description=str(exc)) from None  # pyright: ignore[reportUnknownArgumentType]

        answer = completion.choices[0].message.content or ""
        resp.media = {"answer": answer}


class OpenRouterTokenResource:
    """Store user's OpenRouter API token."""

    async def on_post(self, req: falcon.Request, resp: falcon.Response) -> None:
        data = await req.get_media()
        if not data or "api_key" not in data:
            raise falcon.HTTPBadRequest(description="`api_key` field required")

        # TODO(pmcintosh): persist the token for the authenticated user
        # https://github.com/example/repo/issues/2
        raise falcon.HTTPNotImplemented(
            description="This endpoint is not yet implemented."
        )


class HealthResource:
    """Basic health check."""

    async def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        resp.media = {"status": "ok"}
