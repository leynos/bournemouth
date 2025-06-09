import asyncio
import base64
import typing

import msgspec
import pytest
from falcon import asgi, testing
from httpx import ASGITransport, AsyncClient
from pytest_httpx import HTTPXMock
from sqlalchemy.ext.asyncio import AsyncSession

from bournemouth.app import create_app
from bournemouth.openrouter import ResponseDelta, StreamChoice, StreamChunk
from bournemouth.resources import ChatWsRequest, ChatWsResponse

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
        b'"delta": {}, "finish_reason": "stop"}}]}\n'
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
        await ws.send_text(msgspec.json.encode(req).decode())
        first = msgspec.json.decode(await ws.receive_text(), type=ChatWsResponse)
        assert first.fragment == "hi"
        last = msgspec.json.decode(await ws.receive_text(), type=ChatWsResponse)
        assert last.finished is True


@pytest.mark.asyncio
async def test_websocket_multiplexes_requests(
    app: asgi.App, conductor: testing.ASGIConductor, monkeypatch: pytest.MonkeyPatch
) -> None:
    first_started = asyncio.Event()
    second_started = asyncio.Event()

    async def fake_stream(
        service: typing.Any,
        api_key: str,
        history: list[typing.Any],
        *,
        model: str | None = None,
    ) -> typing.AsyncIterator[StreamChunk]:
        if not first_started.is_set():
            first_started.set()
            await second_started.wait()
            await asyncio.sleep(0.01)
            yield StreamChunk(
                id="1",
                object="chat.completion.chunk",
                created=1,
                model="m",
                choices=[StreamChoice(index=0, delta=ResponseDelta(content="a"))],
            )
            yield StreamChunk(
                id="1",
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
        else:
            second_started.set()
            await first_started.wait()
            yield StreamChunk(
                id="2",
                object="chat.completion.chunk",
                created=1,
                model="m",
                choices=[StreamChoice(index=0, delta=ResponseDelta(content="b"))],
            )
            yield StreamChunk(
                id="2",
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

    monkeypatch.setattr("bournemouth.resources.stream_chat_with_service", fake_stream)

    async with AsyncClient(
        transport=ASGITransport(app=typing.cast("typing.Any", app)),
        base_url="https://test",
    ) as client:
        cookie = await _login(client)

    headers = {"cookie": f"session={cookie}"}
    async with conductor.simulate_ws("/chat", headers=headers) as ws:
        await ws.send_text(
            msgspec.json.encode(
                ChatWsRequest(transaction_id="t1", message="a")
            ).decode()
        )
        await ws.send_text(
            msgspec.json.encode(
                ChatWsRequest(transaction_id="t2", message="b")
            ).decode()
        )
        first = msgspec.json.decode(
            await asyncio.wait_for(ws.receive_text(), 1), type=ChatWsResponse
        )
        second = msgspec.json.decode(
            await asyncio.wait_for(ws.receive_text(), 1), type=ChatWsResponse
        )
        third = msgspec.json.decode(
            await asyncio.wait_for(ws.receive_text(), 1), type=ChatWsResponse
        )
        fourth = msgspec.json.decode(
            await asyncio.wait_for(ws.receive_text(), 1), type=ChatWsResponse
        )

    results = [first, second, third, fourth]
    ids = {r.transaction_id for r in results}
    assert ids == {"t1", "t2"}
    assert first.transaction_id == "t2"
    assert any(r.finished for r in results if r.transaction_id == "t1")
    assert any(r.finished for r in results if r.transaction_id == "t2")
