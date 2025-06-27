"""Tests for the ``OpenRouterService`` class."""
import asyncio
import types

import httpx
import pytest

from bournemouth.openrouter import ChatCompletionRequest, ChatMessage
from bournemouth.openrouter_service import OpenRouterService


class DummyClient:
    """Simplified async client used for testing."""

    creations: int = 0

    def __init__(
        self, *, api_key: str, base_url: str, timeout_config: httpx.Timeout | None
    ) -> None:
        """Record creation of the dummy client."""
        DummyClient.creations += 1

    async def __aenter__(self) -> "DummyClient":
        """Enter the async context and return ``self``."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: types.TracebackType | None,
    ) -> None:
        """Exit the async context without error handling."""
        return

    async def create_chat_completion(self, request: ChatCompletionRequest) -> str:
        """Return a canned chat completion response."""
        await asyncio.sleep(0)
        return "ok"


@pytest.mark.asyncio
async def test_reuses_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """The service should reuse a single client instance."""
    DummyClient.creations = 0
    monkeypatch.setattr(
        "bournemouth.openrouter_service.OpenRouterAsyncClient", DummyClient
    )
    service = OpenRouterService()
    msg = [ChatMessage(role="user", content="hi")]
    await service.chat_completion("k", msg)
    await service.chat_completion("k", msg)
    assert DummyClient.creations == 1


@pytest.mark.asyncio
async def test_concurrent_reuse(monkeypatch: pytest.MonkeyPatch) -> None:
    """Concurrent requests share the same client."""
    DummyClient.creations = 0
    monkeypatch.setattr(
        "bournemouth.openrouter_service.OpenRouterAsyncClient", DummyClient
    )
    service = OpenRouterService()
    msg = [ChatMessage(role="user", content="hi")]

    await asyncio.gather(
        service.chat_completion("k", msg),
        service.chat_completion("k", msg),
    )
    assert DummyClient.creations == 1


@pytest.mark.asyncio
async def test_aclose_nonblocking(monkeypatch: pytest.MonkeyPatch) -> None:
    """Closing the service should not wait for ongoing requests."""
    started = asyncio.Event()
    finish = asyncio.Event()

    class SlowClient(DummyClient):
        async def create_chat_completion(self, request: ChatCompletionRequest) -> str:
            started.set()
            await finish.wait()
            return await super().create_chat_completion(request)

    monkeypatch.setattr(
        "bournemouth.openrouter_service.OpenRouterAsyncClient", SlowClient
    )
    service = OpenRouterService()
    msg = [ChatMessage(role="user", content="hi")]

    task = asyncio.create_task(service.chat_completion("k", msg))
    await started.wait()
    close_task = asyncio.create_task(service.aclose())
    await asyncio.sleep(0)
    assert close_task.done()
    finish.set()
    await task
    await close_task


@pytest.mark.asyncio
async def test_can_reuse_after_aclose(monkeypatch: pytest.MonkeyPatch) -> None:
    """A new client is created after the previous one closes."""
    DummyClient.creations = 0
    monkeypatch.setattr(
        "bournemouth.openrouter_service.OpenRouterAsyncClient", DummyClient
    )
    service = OpenRouterService()
    msg = [ChatMessage(role="user", content="hi")]
    await service.chat_completion("k", msg)
    await service.aclose()
    await service.chat_completion("k", msg)
    assert DummyClient.creations == 2


@pytest.mark.asyncio
async def test_remove_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """Removing a client triggers its closure."""
    class ClosingClient(DummyClient):
        closes: int = 0

        async def __aexit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            tb: types.TracebackType | None,
        ) -> None:
            ClosingClient.closes += 1
            await super().__aexit__(exc_type, exc, tb)

    DummyClient.creations = 0
    ClosingClient.closes = 0
    monkeypatch.setattr(
        "bournemouth.openrouter_service.OpenRouterAsyncClient", ClosingClient
    )
    service = OpenRouterService()
    msg = [ChatMessage(role="user", content="hi")]
    await service.chat_completion("k1", msg)
    await service.chat_completion("k2", msg)
    await service.remove_client("k1")
    assert ClosingClient.closes == 1
    await service.chat_completion("k1", msg)
    assert DummyClient.creations == 3
