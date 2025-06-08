import asyncio
import typing

import pytest

from bournemouth.openrouter import ChatMessage
from bournemouth.openrouter_service import OpenRouterService


class DummyClient:
    def __init__(
        self, *, api_key: str, base_url: str, timeout_config: typing.Any
    ) -> None:
        DummyClient.creations += 1

    async def __aenter__(self) -> "DummyClient":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: typing.Any,
    ) -> None:
        return

    async def create_chat_completion(self, request: typing.Any) -> str:
        await asyncio.sleep(0)
        return "ok"


DummyClient.creations = 0


@pytest.mark.asyncio
async def test_reuses_client(monkeypatch: pytest.MonkeyPatch) -> None:
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
async def test_aclose_waits(monkeypatch: pytest.MonkeyPatch) -> None:
    started = asyncio.Event()
    finish = asyncio.Event()

    class SlowClient(DummyClient):
        async def create_chat_completion(self, request: typing.Any) -> str:
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
    assert not close_task.done()
    finish.set()
    await task
    await close_task


@pytest.mark.asyncio
async def test_can_reuse_after_aclose(monkeypatch: pytest.MonkeyPatch) -> None:
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
    class ClosingClient(DummyClient):
        async def __aexit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            tb: typing.Any,
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
