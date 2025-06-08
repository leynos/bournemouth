from __future__ import annotations

import asyncio
import os
import typing
from collections import OrderedDict
from contextlib import AsyncExitStack

if typing.TYPE_CHECKING:  # pragma: no cover - only for type checking
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


class OpenRouterService:
    """Cache and manage :class:`OpenRouterAsyncClient` instances."""

    def __init__(
        self,
        *,
        default_model: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_BASE_URL,
        timeout_config: httpx.Timeout | None = None,
        max_clients: int = 10,
    ) -> None:
        self.default_model = default_model
        self.base_url = base_url
        self.timeout_config = timeout_config
        self.max_clients = max_clients

        self._lock = asyncio.Lock()
        self._stack = AsyncExitStack()
        self._entered = False
        self._clients: OrderedDict[str, OpenRouterAsyncClient] = OrderedDict()

    @classmethod
    def from_env(cls) -> OpenRouterService:
        model = os.getenv("OPENROUTER_MODEL") or DEFAULT_MODEL
        base_url = os.getenv("OPENROUTER_BASE_URL") or DEFAULT_BASE_URL
        return cls(default_model=model, base_url=base_url)

    async def _ensure_stack(self) -> None:
        async with self._lock:
            if not self._entered:
                await self._stack.__aenter__()
                self._entered = True

    async def __aenter__(self) -> OpenRouterService:
        await self._ensure_stack()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: typing.Any,
    ) -> None:
        await self._stack.aclose()
        self._clients.clear()
        self._stack = AsyncExitStack()
        self._entered = False

    async def aclose(self) -> None:
        await self.__aexit__(None, None, None)
        # reopen for reuse
        await self._ensure_stack()

    async def _get_client(self, api_key: str) -> OpenRouterAsyncClient:
        await self._ensure_stack()
        async with self._lock:
            if api_key in self._clients:
                client = self._clients[api_key]
                self._clients.move_to_end(api_key)
                return client
            if len(self._clients) >= self.max_clients:
                _, stale = self._clients.popitem(last=False)
                await stale.__aexit__(None, None, None)
            client = OpenRouterAsyncClient(
                api_key=api_key,
                base_url=self.base_url,
                timeout_config=self.timeout_config,
            )
            client = await self._stack.enter_async_context(client)
            self._clients[api_key] = client
            return client

    async def remove_client(self, api_key: str) -> None:
        async with self._lock:
            client = self._clients.pop(api_key, None)
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
        client = await self._get_client(api_key)
        return await client.create_chat_completion(request)


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
