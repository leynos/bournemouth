import base64
import typing

import msgspec
import pytest
from falcon import asgi, testing
from httpx import ASGITransport, AsyncClient
from pytest_httpx import HTTPXMock
from sqlalchemy.ext.asyncio import AsyncSession

from bournemouth.app import create_app
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
