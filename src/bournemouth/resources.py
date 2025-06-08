"""Falcon resource classes for the chat API."""

from __future__ import annotations

import typing

import falcon
import msgspec
from sqlalchemy import select, update

if typing.TYPE_CHECKING:  # pragma: no cover
    from sqlalchemy.ext.asyncio import AsyncSession

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
        self,
        service: OpenRouterService,
        session_factory: typing.Callable[[], AsyncSession],
    ) -> None:
        self._service = service
        self._session_factory = session_factory

    async def on_post(self, req: falcon.Request, resp: falcon.Response) -> None:
        raw = await typing.cast("typing.Awaitable[bytes]", req.bounded_stream.read())
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
                        history.append(
                            ChatMessage(
                                role=typing.cast("Role", role),
                                content=content,
                            )
                        )
                    case _:
                        raise falcon.HTTPBadRequest(description="invalid history item")

        history.append(ChatMessage(role="user", content=msg))

        model = typing.cast("str | None", extra.get("model"))

        async with self._session_factory() as session:
            stmt = select(UserAccount.openrouter_token_enc).where(
                UserAccount.google_sub == typing.cast("str", req.context["user"])
            )
            result = await session.execute(stmt)
            token = typing.cast("bytes | str | None", result.scalar_one_or_none())
        if not token:
            raise falcon.HTTPBadRequest(description="missing OpenRouter token")

        api_key = token.decode() if isinstance(token, bytes) else token

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

        if not completion.choices:
            raise falcon.HTTPBadGateway(description="no completion choices")

        answer = completion.choices[0].message.content or ""
        resp.media = {"answer": answer}


class OpenRouterTokenResource:
    """Store user's OpenRouter API token."""

    def __init__(self, session_factory: typing.Callable[[], AsyncSession]) -> None:
        self._session_factory = session_factory

    async def on_post(self, req: falcon.Request, resp: falcon.Response) -> None:
        data = await req.get_media()
        api_key = data.get("api_key") if isinstance(data, dict) else None
        if not isinstance(api_key, str):
            raise falcon.HTTPBadRequest(description="`api_key` field required")

        async with self._session_factory() as session:
            stmt = (
                update(UserAccount)
                .where(
                    UserAccount.google_sub == typing.cast("str", req.context["user"])
                )
                .values(openrouter_token_enc=api_key.encode())
            )
            result = await session.execute(stmt)
            if result.rowcount == 0:
                resp.status = falcon.HTTP_404
                return
            await session.commit()
        resp.status = falcon.HTTP_NO_CONTENT


class HealthResource:
    """Basic health check."""

    async def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        resp.media = {"status": "ok"}
