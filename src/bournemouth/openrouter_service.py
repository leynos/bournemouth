from __future__ import annotations

import asyncio
import collections
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


def _make_set_event() -> asyncio.Event:
    """Return an already-set event for initial state."""
    event = asyncio.Event()
    event.set()
    return event


@dataclasses.dataclass(slots=True)
class OpenRouterService:
    """Wrapper around :class:`OpenRouterAsyncClient` configuration."""

    default_model: str = DEFAULT_MODEL
    base_url: str = DEFAULT_BASE_URL
    timeout_config: httpx.Timeout | None = None
    max_clients: int = 10
    _clients: dict[str, OpenRouterAsyncClient] = dataclasses.field(
        default_factory=dict, init=False, repr=False
    )
    _locks: dict[str, asyncio.Lock] = dataclasses.field(
        default_factory=dict, init=False, repr=False
    )
    _client_order: collections.deque[str] = dataclasses.field(
        default_factory=collections.deque, init=False, repr=False
    )
    _cache_lock: asyncio.Lock = dataclasses.field(
        default_factory=asyncio.Lock, init=False, repr=False
    )
    _inflight: int = dataclasses.field(default=0, init=False, repr=False)
    _inflight_lock: asyncio.Lock = dataclasses.field(
        default_factory=asyncio.Lock, init=False, repr=False
    )

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
        async with self._cache_lock:
            lock = self._locks.get(api_key)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[api_key] = lock
        async with lock, self._cache_lock:
            client = self._clients.get(api_key)
            if client is not None:
                if api_key in self._client_order:
                    self._client_order.remove(api_key)
                self._client_order.append(api_key)
                return client
            if len(self._clients) >= self.max_clients:
                evict = self._client_order.popleft()
                stale = self._clients.pop(evict)
                await stale.__aexit__(None, None, None)
                self._locks.pop(evict, None)
            client = OpenRouterAsyncClient(
                api_key=api_key,
                base_url=self.base_url,
                timeout_config=self.timeout_config,
            )
            await client.__aenter__()
            self._clients[api_key] = client
            self._client_order.append(api_key)
            return client

    async def aclose(self) -> None:
        async with self._inflight_lock:
            if self._closing:
                await self._no_inflight.wait()
                return
            self._closing = True
            if self._inflight == 0:
                self._no_inflight.set()
        await self._no_inflight.wait()
        for client in self._clients.values():
            await client.__aexit__(None, None, None)
        self._clients.clear()
        self._locks.clear()
        self._client_order.clear()
        self._closing = False
        self._no_inflight.set()

    async def remove_client(self, api_key: str) -> None:
        """Close and remove a cached client."""
        async with self._cache_lock:
            client = self._clients.pop(api_key, None)
            self._locks.pop(api_key, None)
            if api_key in self._client_order:
                self._client_order.remove(api_key)
        if client is not None:
            await client.__aexit__(None, None, None)

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
