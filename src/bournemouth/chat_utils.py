"""Utilities for websocket chat."""

from __future__ import annotations

import asyncio
import logging
import typing

import falcon
from msgspec import Struct
from msgspec import json as msgspec_json

from .chat_service import stream_answer
from .openrouter import ChatMessage, StreamChoice
from .openrouter_service import OpenRouterService

if typing.TYPE_CHECKING:  # pragma: no cover
    from falcon.asgi import WebSocket

__all__ = [
    "ChatWsRequest",
    "ChatWsResponse",
    "build_chat_history",
    "stream_chat_response",
]

_logger = logging.getLogger(__name__)


class ChatWsRequest(Struct):
    """Request payload for websocket chat."""

    transaction_id: str
    message: str
    model: str | None = None
    history: list[typing.Any] | None = None


class ChatWsResponse(Struct):
    """Response fragment sent over websocket."""

    transaction_id: str
    fragment: str
    finished: bool = False


def build_chat_history(message: str, history: list[ChatMessage] | None) -> list[ChatMessage]:
    """Return chat history with the user message appended."""
    hist = history or []
    new_history = [ChatMessage(role=m.role, content=m.content) for m in hist]
    new_history.append(ChatMessage(role="user", content=message))
    return new_history


async def stream_chat_response(
    service: OpenRouterService,
    ws: WebSocket,
    encoder: msgspec_json.Encoder,
    send_lock: asyncio.Lock,
    transaction_id: str,
    api_key: str,
    history: list[ChatMessage],
    model: str | None,
) -> None:
    """Stream chat completions back to the client."""
    try:
        async for chunk in stream_answer(service, api_key, history, model):
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
    except (falcon.HTTPGatewayTimeout, falcon.HTTPBadGateway) as exc:  # pragma: no cover - passthrough
        _logger.exception("closing websocket due to upstream error", exc_info=exc)
        await ws.close(code=1011)
