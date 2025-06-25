"""Utilities for websocket chat."""

from __future__ import annotations

import dataclasses as dc
import logging
import typing

import falcon
from msgspec import Struct
from msgspec import json as msgspec_json

from .chat_service import stream_answer
from .openrouter import ChatMessage, StreamChoice, StreamChunk

if typing.TYPE_CHECKING:  # pragma: no cover
    import asyncio

    from falcon.asgi import WebSocket

    from .openrouter_service import OpenRouterService

__all__ = [
    "ChatWsRequest",
    "ChatWsResponse",
    "StreamConfig",
    "build_chat_history",
    "stream_chat_response",
]

_logger = logging.getLogger(__name__)


class ChatWsRequest(Struct):
    """Request payload for websocket chat."""

    transaction_id: str
    message: str
    model: str | None = None
    history: list[ChatMessage] | None = None


class ChatWsResponse(Struct):
    """Response fragment sent over websocket."""

    transaction_id: str
    fragment: str
    finished: bool = False


@dc.dataclass(slots=True)
class StreamConfig:
    """Configuration for streaming chat responses."""

    service: OpenRouterService
    ws: WebSocket
    encoder: msgspec_json.Encoder
    send_lock: asyncio.Lock
    api_key: str
    model: str | None
    stream_func: typing.Callable[
        [OpenRouterService, str, list[ChatMessage], typing.Any],
        typing.AsyncIterator[StreamChunk],
    ] = stream_answer


def build_chat_history(
    message: str, history: list[ChatMessage] | None
) -> list[ChatMessage]:
    """Return chat history with the user message appended."""
    new_history = list(history or [])
    new_history.append(ChatMessage(role="user", content=message))
    return new_history


async def stream_chat_response(
    cfg: StreamConfig,
    transaction_id: str,
    history: list[ChatMessage],
) -> None:
    """Stream chat completions back to the client."""
    try:
        async for chunk in cfg.stream_func(
            cfg.service,
            cfg.api_key,
            history,
            cfg.model,
        ):
            choice: StreamChoice = chunk.choices[0]
            if choice.delta.content:
                async with cfg.send_lock:
                    raw = cfg.encoder.encode(
                        ChatWsResponse(
                            transaction_id=transaction_id,
                            fragment=choice.delta.content,
                        )
                    )
                    await cfg.ws.send_text(raw.decode())
            if choice.finish_reason is not None:
                async with cfg.send_lock:
                    raw = cfg.encoder.encode(
                        ChatWsResponse(
                            transaction_id=transaction_id,
                            fragment="",
                            finished=True,
                        )
                    )
                    await cfg.ws.send_text(raw.decode())
                break
    except (
        falcon.HTTPGatewayTimeout,
        falcon.HTTPBadGateway,
    ) as exc:  # pragma: no cover - passthrough
        _logger.exception(
            "closing websocket due to upstream error",
            exc_info=exc,
        )
        await cfg.ws.close(code=1011)
