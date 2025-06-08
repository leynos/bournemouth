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


class SimpleMessage(msgspec.Struct):
    role: Role
    content: str


class ChatRequest(msgspec.Struct):
    """Request body for the chat endpoint."""

    message: str
    history: list[SimpleMessage] | None = None
    model: str | None = None


class TokenRequest(msgspec.Struct):
    api_key: str


class ChatResource:
    """Handle chat requests."""

    POST_SCHEMA = ChatRequest

    def __init__(
        self,
        service: OpenRouterService,
        session_factory: typing.Callable[[], AsyncSession],
    ) -> None:
        self._service = service
        self._session_factory = session_factory

    async def on_post(
        self,
        req: falcon.Request,
        resp: falcon.Response,
        *,
        chatrequest: ChatRequest,
    ) -> None:
        match chatrequest:
            case ChatRequest(message=msg, history=hist, model=model):
                history = [
                    ChatMessage(role=m.role, content=m.content)
                    for m in (hist or [])
                ]
            case _:
                raise falcon.HTTPBadRequest(description="invalid payload")
        history.append(ChatMessage(role="user", content=msg))

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

    POST_SCHEMA = TokenRequest

    def __init__(self, session_factory: typing.Callable[[], AsyncSession]) -> None:
        self._session_factory = session_factory

    async def on_post(
        self,
        req: falcon.Request,
        resp: falcon.Response,
        *,
        tokenrequest: TokenRequest,
    ) -> None:
        api_key = tokenrequest.api_key

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
