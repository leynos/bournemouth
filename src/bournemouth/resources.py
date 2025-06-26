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
from falcon_pachinko import WebSocketResource, handles_message
from msgspec import json as msgspec_json
from sqlalchemy import update

if typing.TYPE_CHECKING:  # pragma: no cover
    from falcon.asgi import WebSocket
    from sqlalchemy.ext.asyncio import AsyncSession

    from .openrouter_service import OpenRouterService

from .chat_service import (
    generate_answer,
    get_or_create_conversation,
    list_conversation_messages,
    load_user_and_api_key,
    stream_answer,
)
from .chat_utils import (
    ChatWsRequest,
    ChatWsResponse,
    StreamConfig,
    build_chat_history,
    stream_chat_response,
)
from .models import Message, MessageRole, UserAccount
from .openrouter import ChatMessage, Role, StreamChunk
from .resource_helpers import get_api_key

_logger = logging.getLogger(__name__)

_MISSING_USER_ERROR = "on_connect must be called before handle_chat"


class HttpMessage(msgspec.Struct):  # pyright: ignore[reportUntypedBaseClass]
    """A chat message received via HTTP."""

    role: Role
    content: str


class ChatRequest(msgspec.Struct):  # pyright: ignore[reportUntypedBaseClass]
    """Request body for the chat endpoint."""

    message: str
    history: list[HttpMessage] | None = None
    model: str | None = None


class TokenRequest(msgspec.Struct):  # pyright: ignore[reportUntypedBaseClass]
    """Payload for saving an OpenRouter API token."""

    api_key: str


class ChatStateRequest(msgspec.Struct):  # pyright: ignore[reportUntypedBaseClass]
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
            [OpenRouterService, str, list[ChatMessage], str | None],
            typing.AsyncIterator[StreamChunk],
        ] = stream_answer,
    ) -> None:
        """Create a new ``ChatResource``.

        Parameters
        ----------
        service : OpenRouterService
            Client used to communicate with OpenRouter.
        session_factory : Callable[[], AsyncSession]
            Callable returning an :class:`AsyncSession`.
        stream_answer_func : Callable
            Callable to stream chat completions.
        """
        self._service = service
        self._session_factory = session_factory
        self._stream_answer = stream_answer_func

    async def on_post(
        self,
        req: falcon.Request,
        resp: falcon.Response,
        *,
        body: ChatRequest,
    ) -> None:
        """Handle a chat request and return a response."""
        # Convert HttpMessage to ChatMessage for compatibility
        chat_history: list[ChatMessage] | None = None
        if body.history:
            chat_history = [
                ChatMessage(role=msg.role, content=msg.content)
                for msg in body.history
            ]
        history = build_chat_history(body.message, chat_history)
        model = body.model

        user = typing.cast("str", req.context["user"])
        api_key = await get_api_key(self._session_factory, user)
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
        """Stream chat responses over WebSocket."""
        encoder = typing.cast("msgspec_json.Encoder", req.context.msgspec_encoder)
        decoder = msgspec_json.Decoder(ChatWsRequest)
        await ws.accept()
        send_lock = asyncio.Lock()
        tasks: set[asyncio.Task[None]] = set()

        def _finalize_task(task: asyncio.Task[None]) -> None:
            tasks.discard(task)
            with contextlib.suppress(Exception):
                task.result()

        async def handle(request: ChatWsRequest) -> None:
            history = build_chat_history(request.message, request.history)
            user = typing.cast("str", req.context["user"])
            api_key = await get_api_key(self._session_factory, user)
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
            cfg = StreamConfig(
                self._service,
                typing.cast("WebSocket", ws),  # pyright: ignore[reportUnknownArgumentType,reportUnnecessaryCast]
                typing.cast("msgspec_json.Encoder", encoder),  # pyright: ignore[reportUnknownArgumentType,reportUnnecessaryCast]
                send_lock,
                api_key,
                request.model,
                self._stream_answer,
            )
            await stream_chat_response(cfg, request.transaction_id, history)

        try:
            while True:
                raw = await ws.receive_text()
                raw_bytes: bytes = raw.encode()
                decoded_request = typing.cast("ChatWsRequest", decoder.decode(raw_bytes))  # pyright: ignore[reportUnnecessaryCast]
                task = asyncio.create_task(handle(decoded_request))
                tasks.add(task)
                task.add_done_callback(_finalize_task)
        except falcon.WebSocketDisconnected:
            pass
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)


class ChatWsPachinkoResource(WebSocketResource):  # pyright: ignore[reportUntypedBaseClass]
    """Stateless chat using ``falcon-pachinko``.

    Dependencies are supplied at construction time to avoid shared state.
    """

    def __init__(
        self,
        service: OpenRouterService,
        session_factory: typing.Callable[[], AsyncSession],
    ) -> None:
        """Create a new ``ChatWsPachinkoResource``.

        Parameters
        ----------
        service:
            Client for interacting with the OpenRouter API.
        session_factory:
            Callable returning an :class:`AsyncSession`.
        """
        self._service = service
        self._session_factory = session_factory
        self._encoder = msgspec_json.Encoder()
        self._send_lock: asyncio.Lock | None = None
        self._user: str | None = None

    async def on_connect(
        self, req: falcon.asgi.Request, ws: falcon.asgi.WebSocket, **_: typing.Any
    ) -> bool:
        """Accept the connection and store the user.

        Parameters
        ----------
        req : falcon.asgi.Request
            The handshake request.
        ws : falcon.asgi.WebSocket
            The WebSocket being connected.
        **_ : typing.Any
            Additional arguments ignored.

        Returns
        -------
        bool
            ``True`` to keep the connection open.
        """
        self._send_lock = asyncio.Lock()
        self._user = typing.cast("str", req.context["user"])
        await ws.accept()
        return True


    @handles_message("chat")  # pyright: ignore[reportUntypedFunctionDecorator]
    async def handle_chat(
        self, ws: falcon.asgi.WebSocket, payload: ChatWsRequest
    ) -> None:
        """Handle incoming chat messages over WebSocket."""
        if self._send_lock is None:
            raise RuntimeError(_MISSING_USER_ERROR)
        history = build_chat_history(payload.message, payload.history)
        if self._user is None:
            raise RuntimeError(_MISSING_USER_ERROR)
        api_key = await get_api_key(self._session_factory, self._user)
        if api_key is None:
            async with self._send_lock:
                raw = self._encoder.encode(
                    ChatWsResponse(
                        transaction_id=payload.transaction_id,
                        fragment="missing OpenRouter token",
                        finished=True,
                    )
                )
                await ws.send_text(raw.decode())
            return
        cfg = StreamConfig(
            self._service,
            typing.cast("WebSocket", ws),  # pyright: ignore[reportUnknownArgumentType,reportUnnecessaryCast]
            typing.cast("msgspec_json.Encoder", self._encoder),  # pyright: ignore[reportUnknownArgumentType,reportUnnecessaryCast]
            self._send_lock,
            api_key,
            payload.model,
        )
        await stream_chat_response(cfg, payload.transaction_id, history)


class ChatStateResource:
    """Handle stateful chat requests."""

    POST_SCHEMA = ChatStateRequest

    def __init__(
        self,
        service: OpenRouterService,
        session_factory: typing.Callable[[], AsyncSession],
    ) -> None:
        """Create a new ``ChatStateResource``.

        Parameters
        ----------
        service : OpenRouterService
            Client used to communicate with OpenRouter.
        session_factory : Callable[[], AsyncSession]
            Callable returning an :class:`AsyncSession`.
        """
        self._service = service
        self._session_factory = session_factory

    async def on_post(
        self,
        req: falcon.Request,
        resp: falcon.Response,
        *,
        body: ChatStateRequest,
    ) -> None:
        """Process a stateful chat request."""
        user_sub = typing.cast("str", req.context["user"])
        user_id, api_key = await load_user_and_api_key(self._session_factory, user_sub)
        if api_key is None:
            raise falcon.HTTPUnauthorized(description="missing OpenRouter token")

        async with self._session_factory() as session:
            session_typed: AsyncSession = session
            async with session_typed.begin():
                conv = await get_or_create_conversation(
                    session_typed,  # pyright: ignore[reportUnknownArgumentType]
                    body.conversation_id,
                    user_id,
                )
                history_rows = await list_conversation_messages(
                    session_typed,  # pyright: ignore[reportUnknownArgumentType]
                    typing.cast("uuid.UUID", conv.id),  # pyright: ignore[reportUnnecessaryCast]
                )
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

            resp.media = {
                "answer": answer,
                "conversation_id": str(typing.cast("uuid.UUID", conv.id)),  # pyright: ignore[reportUnnecessaryCast]
            }


class OpenRouterTokenResource:
    """Store user's OpenRouter API token."""

    POST_SCHEMA = TokenRequest

    def __init__(self, session_factory: typing.Callable[[], AsyncSession]) -> None:
        """Create a new ``OpenRouterTokenResource``.

        Parameters
        ----------
        session_factory : Callable[[], AsyncSession]
            Callable returning an :class:`AsyncSession`.
        """
        self._session_factory = session_factory

    async def on_post(
        self,
        req: falcon.Request,
        resp: falcon.Response,
        *,
        body: TokenRequest,
    ) -> None:
        """Save the provided API token for the current user."""
        api_value = body.api_key.strip()
        token_bytes = api_value.encode() if api_value else None

        async with self._session_factory() as session:
            session_typed: AsyncSession = session
            stmt = (
                update(UserAccount)
                .where(
                    UserAccount.google_sub == typing.cast("str", req.context["user"])
                )
                .values(openrouter_token_enc=token_bytes)
            )
            result = await session_typed.execute(stmt)
            if result.rowcount == 0:
                resp.status = falcon.HTTP_404
                return
            await session_typed.commit()
        resp.status = falcon.HTTP_NO_CONTENT


class HealthResource:
    """Basic health check."""

    async def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        """Return a simple health status payload."""
        del req  # Unused parameter
        resp.media = {"status": "ok"}
