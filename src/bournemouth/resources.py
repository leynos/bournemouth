"""Falcon resource classes for the chat API."""

from __future__ import annotations

import asyncio
import contextlib
import typing

import falcon
import falcon.asgi
import msgspec
from msgspec import json as msgspec_json
from sqlalchemy import select, update

if typing.TYPE_CHECKING:  # pragma: no cover
    from sqlalchemy.ext.asyncio import AsyncSession

from .models import UserAccount
from .openrouter import ChatMessage, Role, StreamChoice
from .openrouter_service import (
    OpenRouterService,
    OpenRouterServiceBadGatewayError,
    OpenRouterServiceTimeoutError,
    chat_with_service,
    stream_chat_with_service,
)


class HttpMessage(msgspec.Struct):
    role: Role
    content: str


class ChatRequest(msgspec.Struct):
    """Request body for the chat endpoint."""

    message: str
    history: list[HttpMessage] | None = None
    model: str | None = None


class ChatWsRequest(msgspec.Struct):
    transaction_id: str
    message: str
    model: str | None = None
    history: list[HttpMessage] | None = None


class ChatWsResponse(msgspec.Struct):
    transaction_id: str
    fragment: str
    finished: bool = False


class TokenRequest(msgspec.Struct):
    api_key: str


class ChatResource:
    """Handle chat requests.

    The WebSocket API multiplexes chat streams so multiple requests may be
    processed concurrently over a single connection.
    """

    POST_SCHEMA = ChatRequest

    def __init__(
        self,
        service: OpenRouterService,
        session_factory: typing.Callable[[], AsyncSession],
    ) -> None:
        self._service = service
        self._session_factory = session_factory

    def _build_history(self, request: ChatWsRequest) -> list[ChatMessage]:
        hist = request.history or []
        history = [ChatMessage(role=m.role, content=m.content) for m in hist]
        history.append(ChatMessage(role="user", content=request.message))
        return history

    async def _get_api_key(self, user: str) -> str | None:
        async with self._session_factory() as session:
            stmt = select(UserAccount.openrouter_token_enc).where(
                UserAccount.google_sub == user
            )
            result = await session.execute(stmt)
            token: bytes | str | None = typing.cast(
                "bytes | str | None", result.scalar_one_or_none()
            )
        if token is None:
            return None
        return token.decode() if isinstance(token, bytes) else token

    async def _stream_chat(
        self,
        ws: falcon.asgi.WebSocket,
        encoder: msgspec_json.Encoder,
        send_lock: asyncio.Lock,
        transaction_id: str,
        api_key: str,
        history: list[ChatMessage],
        model: str | None,
    ) -> None:
        """Stream chat completions back to the client."""

        try:
            async for chunk in stream_chat_with_service(
                self._service,
                api_key,
                history,
                model=model,
            ):
                choice: StreamChoice = chunk.choices[0]
                if choice.delta.content:
                    async with send_lock:
                        raw = encoder.encode(
                            ChatWsResponse(
                                transaction_id=transaction_id,
                                fragment=choice.delta.content,
                            )
                        )
                        await ws.send_text(raw.decode())
                if choice.finish_reason is not None:
                    async with send_lock:
                        raw = encoder.encode(
                            ChatWsResponse(
                                transaction_id=transaction_id,
                                fragment="",
                                finished=True,
                            )
                        )
                        await ws.send_text(raw.decode())
                    break
        except OpenRouterServiceTimeoutError:
            await ws.close(code=1011)
        except OpenRouterServiceBadGatewayError:
            await ws.close(code=1011)

    async def on_post(
        self,
        req: falcon.Request,
        resp: falcon.Response,
        *,
        body: ChatRequest,
    ) -> None:
        msg = body.message
        history = [
            ChatMessage(role=m.role, content=m.content) for m in (body.history or [])
        ]
        history.append(ChatMessage(role="user", content=msg))
        model = body.model

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

    async def on_websocket(
        self, req: falcon.asgi.Request, ws: falcon.asgi.WebSocket
    ) -> None:
        encoder = typing.cast("msgspec_json.Encoder", req.context.msgspec_encoder)
        decoder_cls = typing.cast(
            "type[msgspec_json.Decoder[ChatWsRequest]]",
            req.context.msgspec_decoder_cls,
        )
        decoder = decoder_cls(ChatWsRequest)
        await ws.accept()
        send_lock = asyncio.Lock()
        tasks: set[asyncio.Task[None]] = set()

        def _finalize_task(task: asyncio.Task[None]) -> None:
            tasks.discard(task)
            with contextlib.suppress(Exception):
                task.result()

        async def handle(request: ChatWsRequest) -> None:
            history = self._build_history(request)
            user = typing.cast("str", req.context["user"])
            api_key = await self._get_api_key(user)
            if api_key is None:
                async with send_lock:
                    raw = encoder.encode(
                        ChatWsResponse(
                            transaction_id=request.transaction_id,
                            fragment="missing OpenRouter token",
                            finished=True,
                        )
                    )
                    await ws.send_text(raw.decode())
                return
            await self._stream_chat(
                ws,  # pyright: ignore[reportUnknownArgumentType]
                encoder,
                send_lock,
                request.transaction_id,
                api_key,
                history,
                request.model,
            )

        try:
            while True:
                raw = await ws.receive_text()
                raw_bytes: bytes = raw.encode()
                request = decoder.decode(typing.cast("bytes", raw_bytes))
                task = asyncio.create_task(handle(request))
                tasks.add(task)
                task.add_done_callback(_finalize_task)
        except falcon.WebSocketDisconnected:
            pass
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)


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
        body: TokenRequest,
    ) -> None:
        api_key = body.api_key

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
