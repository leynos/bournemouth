"""Falcon resource classes for the chat API."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import typing
import uuid  # noqa: TC003

import falcon
import falcon.asgi
import msgspec
from msgspec import json as msgspec_json
from sqlalchemy import update

if typing.TYPE_CHECKING:  # pragma: no cover
    from sqlalchemy.ext.asyncio import AsyncSession

    from .openrouter_service import OpenRouterService

from .chat_service import (
    generate_answer,
    get_or_create_conversation,
    list_conversation_messages,
    load_user_and_api_key,
    stream_answer,
)
from .models import Message, MessageRole, UserAccount
from .openrouter import ChatMessage, Role, StreamChoice

_logger = logging.getLogger(__name__)


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


class ChatStateRequest(msgspec.Struct):
    """Request body for the stateful chat endpoint."""

    message: str
    conversation_id: uuid.UUID | None = None
    model: str | None = None


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
        *,
        stream_answer_func: typing.Callable[
            [OpenRouterService, str, list[ChatMessage], typing.Any],
            typing.AsyncIterator[StreamChunk],
        ] = stream_answer,
    ) -> None:
        self._service = service
        self._session_factory = session_factory
        self._stream_answer = stream_answer_func

    def _build_history(self, request: ChatWsRequest) -> list[ChatMessage]:
        hist = request.history or []
        history = [ChatMessage(role=m.role, content=m.content) for m in hist]
        history.append(ChatMessage(role="user", content=request.message))
        return history

    async def _get_api_key(self, user: str) -> str | None:
        try:
            _, api_key = await load_user_and_api_key(self._session_factory, user)
        except falcon.HTTPUnauthorized:
            return None
        return api_key

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
            async for chunk in self._stream_answer(
                self._service,
                api_key,
                history,
                model,
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
        except (falcon.HTTPGatewayTimeout, falcon.HTTPBadGateway) as exc:
            _logger.exception("closing websocket due to upstream error", exc_info=exc)
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

        user = typing.cast("str", req.context["user"])
        api_key = await self._get_api_key(user)
        if api_key is None:
            raise falcon.HTTPUnauthorized(description="missing OpenRouter token")

        answer = await generate_answer(
            self._service,
            api_key,
            history,
            model,
        )
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
                decoded_request = decoder.decode(raw_bytes)
                task = asyncio.create_task(handle(decoded_request))
                tasks.add(task)
                task.add_done_callback(_finalize_task)
        except falcon.WebSocketDisconnected:
            pass
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)


class ChatStateResource:
    """Handle stateful chat requests."""

    POST_SCHEMA = ChatStateRequest

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
        body: ChatStateRequest,
    ) -> None:
        user_sub = typing.cast("str", req.context["user"])
        user_id, api_key = await load_user_and_api_key(self._session_factory, user_sub)
        if api_key is None:
            raise falcon.HTTPUnauthorized(description="missing OpenRouter token")

        async with self._session_factory() as session:
            async with session.begin():
                conv = await get_or_create_conversation(
                    session, body.conversation_id, user_id
                )
                history_rows = await list_conversation_messages(session, conv.id)
                last_id = history_rows[-1].id if history_rows else None

                user_msg = Message(
                    conversation_id=conv.id,
                    parent_id=last_id,
                    role=MessageRole.USER,
                    content=body.message,
                )
                session.add(user_msg)
                await session.flush()
                if conv.root_message_id is None:
                    conv.root_message_id = user_msg.id

            role_map: dict[MessageRole, Role] = {
                MessageRole.USER: "user",
                MessageRole.ASSISTANT: "assistant",
                MessageRole.SYSTEM: "system",
            }
            messages = [
                ChatMessage(role=role_map[m.role], content=m.content)
                for m in history_rows
            ]
            messages.append(ChatMessage(role="user", content=body.message))

            answer = await generate_answer(
                self._service,
                api_key,
                messages,
                body.model,
            )

            async with session.begin():
                assistant_msg = Message(
                    conversation_id=conv.id,
                    parent_id=user_msg.id,
                    role=MessageRole.ASSISTANT,
                    content=answer,
                )
                session.add(assistant_msg)

            resp.media = {"answer": answer, "conversation_id": str(conv.id)}


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
        api_value = body.api_key.strip()
        token_bytes = api_value.encode() if api_value else None

        async with self._session_factory() as session:
            stmt = (
                update(UserAccount)
                .where(
                    UserAccount.google_sub == typing.cast("str", req.context["user"])
                )
                .values(openrouter_token_enc=token_bytes)
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
