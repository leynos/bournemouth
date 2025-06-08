from __future__ import annotations

import asyncio
import dataclasses
import os
import typing

if typing.TYPE_CHECKING:
    import httpx

from .openrouter import (
    DEFAULT_BASE_URL,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    OpenRouterAPIError,
    OpenRouterAsyncClient,
    OpenRouterNetworkError,
    OpenRouterServerError,
    OpenRouterTimeoutError,
)

DEFAULT_MODEL = "deepseek/deepseek-chat-v3-0324:free"


@dataclasses.dataclass(slots=True)
class OpenRouterService:
    """Wrapper around :class:`OpenRouterAsyncClient` configuration."""

    default_model: str = DEFAULT_MODEL
    base_url: str = DEFAULT_BASE_URL
    timeout_config: httpx.Timeout | None = None
    _clients: dict[str, OpenRouterAsyncClient] = dataclasses.field(
        default_factory=dict, init=False, repr=False
    )
    _locks: dict[str, asyncio.Lock] = dataclasses.field(
        default_factory=dict, init=False, repr=False
    )
    _inflight: int = dataclasses.field(default=0, init=False, repr=False)
    _inflight_lock: asyncio.Lock = dataclasses.field(
        default_factory=asyncio.Lock, init=False, repr=False
    )

    @staticmethod
    def _make_set_event() -> asyncio.Event:
        event = asyncio.Event()
        event.set()
        return event

    _no_inflight: asyncio.Event = dataclasses.field(
        default_factory=_make_set_event,
        init=False,
        repr=False,
    )
    _closing: bool = dataclasses.field(default=False, init=False, repr=False)

    @classmethod
    def from_env(cls) -> OpenRouterService:
        model = os.getenv("OPENROUTER_MODEL") or DEFAULT_MODEL
        base_url = os.getenv("OPENROUTER_BASE_URL") or DEFAULT_BASE_URL
        return cls(default_model=model, base_url=base_url)

    async def _get_client(self, api_key: str) -> OpenRouterAsyncClient:
        """Return a cached client, instantiating it once per API key."""
        lock = self._locks.get(api_key)
        if lock is None:
            lock = asyncio.Lock()
            lock = self._locks.setdefault(api_key, lock)
        async with lock:
            client = self._clients.get(api_key)
            if client is None:
                client = OpenRouterAsyncClient(
                    api_key=api_key,
                    base_url=self.base_url,
                    timeout_config=self.timeout_config,
                )
                await client.__aenter__()
                self._clients[api_key] = client
            return client

    async def aclose(self) -> None:
        if self._closing:
            await self._no_inflight.wait()
            return
        async with self._inflight_lock:
            self._closing = True
            if self._inflight == 0:
                self._no_inflight.set()
        await self._no_inflight.wait()
        for client in self._clients.values():
            await client.__aexit__(None, None, None)
        self._clients.clear()
        self._locks.clear()

    async def chat_completion(
        self,
        api_key: str,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
    ) -> ChatCompletionResponse:
        request = ChatCompletionRequest(
            model=model or self.default_model,
            messages=messages,
        )
        async with self._inflight_lock:
            if self._closing:
                raise RuntimeError("service is closing")
            self._inflight += 1
            self._no_inflight.clear()
        try:
            client = await self._get_client(api_key)
            return await client.create_chat_completion(request)
        finally:
            async with self._inflight_lock:
                self._inflight -= 1
                if self._inflight == 0:
                    self._no_inflight.set()


class OpenRouterServiceError(Exception):
    """Raised when the OpenRouter service fails."""


class OpenRouterServiceTimeoutError(OpenRouterServiceError):
    pass


class OpenRouterServiceBadGatewayError(OpenRouterServiceError):
    pass


async def chat_with_service(
    service: OpenRouterService,
    api_key: str,
    messages: list[ChatMessage],
    *,
    model: str | None = None,
) -> ChatCompletionResponse:
    try:
        return await service.chat_completion(api_key, messages, model=model)
    except OpenRouterTimeoutError as exc:
        raise OpenRouterServiceTimeoutError(str(exc)) from None
    except (OpenRouterNetworkError, OpenRouterServerError, OpenRouterAPIError) as exc:
        raise OpenRouterServiceBadGatewayError(str(exc)) from None
