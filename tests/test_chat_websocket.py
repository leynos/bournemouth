import asyncio
import base64
import typing

import pytest
from falcon import asgi, testing
from httpx import ASGITransport, AsyncClient
import msgspec
from msgspec import json as msgspec_json
from pytest_httpx import HTTPXMock
from sqlalchemy.ext.asyncio import AsyncSession

from bournemouth.app import create_app
from bournemouth.openrouter import ResponseDelta, StreamChoice, StreamChunk
from bournemouth.resources import ChatWsRequest, ChatWsResponse
from tests.ws_helpers import ws_collector

type SessionFactory = typing.Callable[[], AsyncSession]


@pytest.fixture()
def app(db_session_factory: SessionFactory) -> asgi.App:
    return create_app(db_session_factory=db_session_factory)


@pytest.fixture()
def conductor(app: asgi.App) -> testing.ASGIConductor:
    return testing.ASGIConductor(app)


async def _login(client: AsyncClient) -> str:
    credentials = base64.b64encode(b"admin:adminpass").decode()
    resp = await client.post(
        "/login", headers={"Authorization": f"Basic {credentials}"}
    )
    assert resp.status_code == 200
    return typing.cast("str", resp.cookies.get("session"))


def _patch_stream(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[asyncio.Event, asyncio.Event]:
    first_started = asyncio.Event()
    second_started = asyncio.Event()

    async def fake_stream(
        service: typing.Any,
        api_key: str,
        history: list[typing.Any],
        *,
        model: str | None = None,
    ) -> typing.AsyncIterator[StreamChunk]:
        idx = 1 if not first_started.is_set() else 2
        (first_started if idx == 1 else second_started).set()
        await asyncio.sleep(0.01)
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

    monkeypatch.setattr("bournemouth.chat_service.stream_answer", fake_stream)
    monkeypatch.setattr("bournemouth.resources.stream_answer", fake_stream)
    import bournemouth.resources as r
    monkeypatch.setitem(
        r.ChatResource._stream_chat.__globals__, "stream_answer", fake_stream
    )

    return first_started, second_started


@pytest.mark.timeout(5)
@pytest.mark.asyncio
async def test_websocket_streams_chat(
    app: asgi.App, conductor: testing.ASGIConductor, httpx_mock: HTTPXMock
) -> None:
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
    async with conductor.simulate_ws("/chat", headers=headers) as ws:
        req = ChatWsRequest(transaction_id="t1", message="hi")
        await ws.send_text(msgspec_json.encode(req).decode())
        first = msgspec_json.decode(await ws.receive_text(), type=ChatWsResponse)
        assert first.fragment == "hi"
        last = msgspec_json.decode(await ws.receive_text(), type=ChatWsResponse)
        assert last.finished is True


@pytest.mark.timeout(5)
@pytest.mark.asyncio
async def test_websocket_multiplexes_requests(
    app: asgi.App, conductor: testing.ASGIConductor, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_stream(monkeypatch)

    async with AsyncClient(
        transport=ASGITransport(app=typing.cast("typing.Any", app)),
        base_url="https://test",
    ) as client:
        cookie = await _login(client)

    headers = {"cookie": f"session={cookie}"}
    async with conductor.simulate_ws("/chat", headers=headers) as ws, ws_collector(ws) as coll:
        await ws.send_text(
            msgspec_json.encode(
                ChatWsRequest(transaction_id="t1", message="a")
            ).decode()
        )
        await ws.send_text(
            msgspec_json.encode(
                ChatWsRequest(transaction_id="t2", message="b")
            ).decode()
        )
        raw_msgs = await coll.collect_until(
            lambda m: m.get("finished") and m.get("transaction_id") == "t2",
            timeout=5,
        )
        responses = [msgspec.convert(m, ChatWsResponse) for m in raw_msgs]
        first, second, third, fourth = responses

    results = [first, second, third, fourth]
    ids = {r.transaction_id for r in results}
    assert ids == {"t1", "t2"}
    assert first.transaction_id == "t2"
    assert any(r.finished for r in results if r.transaction_id == "t1")
    assert any(r.finished for r in results if r.transaction_id == "t2")
