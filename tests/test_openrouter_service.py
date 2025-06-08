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
