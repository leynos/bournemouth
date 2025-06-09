"""Falcon resource classes for the chat API."""

from __future__ import annotations

import asyncio
import contextlib
import secrets
import time
import typing
import uuid

import falcon
import falcon.asgi
import msgspec
from msgspec import json as msgspec_json
from sqlalchemy import select, update

if typing.TYPE_CHECKING:  # pragma: no cover
    from sqlalchemy.ext.asyncio import AsyncSession

from .models import Conversation, Message, MessageRole, UserAccount
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


class ChatStateRequest(msgspec.Struct):
    """Request body for the stateful chat endpoint."""

    message: str
    conversation_id: uuid.UUID | None = None
    model: str | None = None


def uuid7() -> uuid.UUID:
    """Return a time-ordered UUIDv7."""

    ts_ms = int(time.time_ns() // 1_000_000)
    rand_a = secrets.randbits(12)
    rand_b = secrets.randbits(62)
    hi = (ts_ms << 16) | (0x7000 | rand_a)
    lo = 0x8000000000000000 | rand_b
    return uuid.UUID(int=(hi << 64) | lo)


async def _load_user_and_api_key(
    session_factory: typing.Callable[[], AsyncSession],
    user_sub: str,
) -> tuple[uuid.UUID, str | None]:
    """Return the user's ID and decrypted OpenRouter API key."""

    async with session_factory() as session:
        stmt = select(UserAccount.id, UserAccount.openrouter_token_enc).where(
            UserAccount.google_sub == user_sub
        )
        result = await session.execute(stmt)
        row = result.one_or_none()
    if row is None:
        raise falcon.HTTPUnauthorized()
    user_id, token = typing.cast("tuple[uuid.UUID, bytes | str | None]", row)
    api_key = token.decode() if isinstance(token, bytes) else token
    if api_key is not None and not api_key.strip():
        api_key = None
    return user_id, api_key


async def _generate_answer(
    service: OpenRouterService,
    api_key: str,
    messages: list[ChatMessage],
    model: str | None,
) -> str:
    """Call the chat service and return the assistant's reply."""

    try:
        completion = await chat_with_service(service, api_key, messages, model=model)
    except OpenRouterServiceTimeoutError:
        raise falcon.HTTPGatewayTimeout() from None
    except OpenRouterServiceBadGatewayError as exc:
        raise falcon.HTTPBadGateway(description=str(exc)) from None

    if not completion.choices:
        raise falcon.HTTPBadGateway(description="no completion choices")
    return completion.choices[0].message.content or ""


async def _get_or_create_conversation(
    session: AsyncSession,
    conv_id: uuid.UUID | None,
    user_id: uuid.UUID,
) -> Conversation:
    """Return an existing conversation or create a new one."""

    conv: Conversation | None = None
    if conv_id is not None:
        conv = await session.get(Conversation, conv_id)
        if conv is None or conv.user_id != user_id:
            raise falcon.HTTPNotFound()
    if conv is None:
        conv = Conversation(id=uuid7(), user_id=user_id)
        session.add(conv)
        await session.flush()
    return conv


async def _list_conversation_messages(
    session: AsyncSession, conv_id: uuid.UUID
) -> list[Message]:
    """Return messages for ``conv_id`` ordered by creation time."""

    stmt = (
        select(Message)
        .where(Message.conversation_id == conv_id)
        .order_by(Message.created_at)
    )
    result = await session.execute(stmt)
    return typing.cast("list[Message]", result.scalars().all())


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
        try:
            _, api_key = await _load_user_and_api_key(self._session_factory, user)
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

        user = typing.cast("str", req.context["user"])
        _, api_key = await _load_user_and_api_key(self._session_factory, user)
        if api_key is None:
            raise falcon.HTTPUnauthorized(description="missing OpenRouter token")

        answer = await _generate_answer(
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
                request = decoder.decode(raw_bytes)
                task = asyncio.create_task(handle(request))
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
        user_id, api_key = await _load_user_and_api_key(self._session_factory, user_sub)
        if api_key is None:
            raise falcon.HTTPUnauthorized(description="missing OpenRouter token")

        async with self._session_factory() as session:
            if body.conversation_id is not None:
                conv = await session.get(Conversation, body.conversation_id)
                if conv is None or conv.user_id != user_id:
                    raise falcon.HTTPNotFound()
                history_rows = await _list_conversation_messages(session, conv.id)
            else:
                conv = None
                history_rows = []
            last_id = history_rows[-1].id if history_rows else None

        messages = [
            ChatMessage(role=typing.cast("Role", m.role.value), content=m.content)
            for m in history_rows
        ]
        messages.append(ChatMessage(role="user", content=body.message))

        answer = await _generate_answer(
            self._service,
            api_key,
            messages,
            body.model,
        )

        async with self._session_factory() as session, session.begin():
            conv = await _get_or_create_conversation(
                session, body.conversation_id, user_id
            )

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
