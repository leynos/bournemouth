"""Tests for the WebSocket chat endpoint."""

import asyncio
import base64
import typing

import msgspec
import pytest
from falcon import asgi, testing
from httpx import ASGITransport, AsyncClient
from msgspec import json as msgspec_json
from pytest_httpx import HTTPXMock
from sqlalchemy.ext.asyncio import AsyncSession

from bournemouth.app import create_app
from bournemouth.openrouter import ChatMessage, ResponseDelta, StreamChoice, StreamChunk
from bournemouth.openrouter_service import OpenRouterService
from bournemouth.resources import ChatWsRequest, ChatWsResponse
from tests.ws_helpers import ws_collector

type SessionFactory = typing.Callable[[], AsyncSession]


@pytest.fixture
def app(db_session_factory: SessionFactory) -> asgi.App:
    """Create an application instance for testing."""
    return create_app(db_session_factory=db_session_factory)


@pytest.fixture
def conductor(app: asgi.App) -> testing.ASGIConductor:
    """Return an ASGI conductor for WebSocket testing."""
    return testing.ASGIConductor(app)


async def _login(client: AsyncClient) -> str:
    credentials = base64.b64encode(b"admin:adminpass").decode()
    resp = await client.post(
        "/login", headers={"Authorization": f"Basic {credentials}"}
    )
    assert resp.status_code == 200
    return typing.cast("str", resp.cookies.get("session"))


class _StreamPatcher:
    def __init__(self) -> None:
        self.call_count = 0
        self.call_lock = asyncio.Lock()

    async def fake_stream(
        self,
        service: OpenRouterService,
        api_key: str,
        history: list[ChatMessage],
        model: str | None,
    ) -> typing.AsyncIterator[StreamChunk]:
        # Safely determine which call this is
        async with self.call_lock:
            self.call_count += 1
            idx = self.call_count

        # Simple delay to ensure proper ordering without deadlock
        if idx == 1:
            await asyncio.sleep(0.1)  # First request takes longer
        else:
            await asyncio.sleep(0.05)  # Second request is faster

        yield StreamChunk(
            id=str(idx),
            object="chat.completion.chunk",
            created=1,
            model="m",
            choices=[
                StreamChoice(
                    index=0,
                    delta=ResponseDelta(content="a" if idx == 1 else "b"),
                )
            ],
        )
        yield StreamChunk(
            id=str(idx),
            object="chat.completion.chunk",
            created=1,
            model="m",
            choices=[
                StreamChoice(
                    index=0,
                    delta=ResponseDelta(),
                    finish_reason="stop",
                )
            ],
        )


def _patch_stream() -> typing.Callable[..., typing.AsyncIterator[StreamChunk]]:
    patcher = _StreamPatcher()
    return patcher.fake_stream


@pytest.mark.timeout(5)
@pytest.mark.asyncio
async def test_websocket_streams_chat(
    app: asgi.App, conductor: testing.ASGIConductor, httpx_mock: HTTPXMock
) -> None:
    """Messages should be streamed to the client over WebSocket."""
    content = (
        b'data: {"id": "1", "object": "chat.completion.chunk", '
        b'"created": 1, "model": "m", "choices": [{"index": 0, '
        b'"delta": {"content": "hi"}}]}\n'
        b'data: {"id": "1", "object": "chat.completion.chunk", '
        b'"created": 1, "model": "m", "choices": [{"index": 0, '
        b'"delta": {}, "finish_reason": "stop"}]}\n'
        b"data: \n"
    )
    httpx_mock.add_response(
        method="POST",
        url="https://openrouter.ai/api/v1/chat/completions",
        headers={"Content-Type": "text/event-stream"},
        content=content,
    )

    async with AsyncClient(
        transport=ASGITransport(app=typing.cast("typing.Any", app)),
        base_url="https://test",
    ) as client:
        cookie = await _login(client)

    headers = {"cookie": f"session={cookie}"}
    async with conductor.simulate_ws("/ws/chat", headers=headers) as ws:
        req = ChatWsRequest(transaction_id="t1", message="hi")
        await ws.send_text(msgspec_json.encode(req).decode())
        first = msgspec_json.decode(await ws.receive_text(), type=ChatWsResponse)
        assert first.fragment == "hi"
        last = msgspec_json.decode(await ws.receive_text(), type=ChatWsResponse)
        assert last.finished is True


@pytest.mark.timeout(10)
@pytest.mark.asyncio
async def test_websocket_multiplexes_requests(
    db_session_factory: SessionFactory,
) -> None:
    """Multiple concurrent requests should receive independent streams."""
    fake_stream = _patch_stream()
    app = create_app(
        db_session_factory=db_session_factory,
        chat_stream_answer=fake_stream,
    )
    conductor = testing.ASGIConductor(app)

    async with AsyncClient(
        transport=ASGITransport(app=typing.cast("typing.Any", app)),
        base_url="https://test",
    ) as client:
        cookie = await _login(client)

    headers = {"cookie": f"session={cookie}"}
    async with (
        conductor.simulate_ws("/ws/chat", headers=headers) as ws,
        ws_collector(ws) as coll,
    ):
        # Send first request
        await ws.send_text(
            msgspec_json.encode(
                ChatWsRequest(transaction_id="t1", message="a")
            ).decode()
        )
        # Send second request
        await ws.send_text(
            msgspec_json.encode(
                ChatWsRequest(transaction_id="t2", message="b")
            ).decode()
        )

        # Collect all messages from both transactions
        # Expect 4 messages total (2 per transaction)
        all_msgs = await coll.collect(n=4, timeout=5)

        # Convert to response objects
        responses = [msgspec.convert(m, ChatWsResponse) for m in all_msgs]

        # Check we got responses for both transactions
        transaction_ids = {r.transaction_id for r in responses}
        assert "t1" in transaction_ids, f"Missing t1 in {transaction_ids}"
        assert "t2" in transaction_ids, f"Missing t2 in {transaction_ids}"

        # Check we got finished messages for both transactions
        finished_responses = [r for r in responses if r.finished]
        finished_transaction_ids = {r.transaction_id for r in finished_responses}
        assert "t1" in finished_transaction_ids, (
            f"Missing finished t1 in {finished_transaction_ids}"
        )
        assert "t2" in finished_transaction_ids, (
            f"Missing finished t2 in {finished_transaction_ids}"
        )

        # Verify we got the expected content
        content_by_transaction = {}
        for r in responses:
            if r.transaction_id not in content_by_transaction:
                content_by_transaction[r.transaction_id] = []
            if r.fragment:
                content_by_transaction[r.transaction_id].append(r.fragment)

        assert "a" in content_by_transaction.get("t1", []), (
            f"Missing 'a' content for t1: {content_by_transaction}"
        )
        assert "b" in content_by_transaction.get("t2", []), (
            f"Missing 'b' content for t2: {content_by_transaction}"
        )
