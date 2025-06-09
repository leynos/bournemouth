import base64
import typing
import uuid
from http import HTTPStatus

import pytest
from falcon import asgi
from httpx import ASGITransport, AsyncClient
from pytest_httpx import HTTPXMock
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bournemouth.app import create_app
from bournemouth.models import Conversation, Message


@pytest.fixture()
def app(db_session_factory: typing.Callable[[], AsyncSession]) -> asgi.App:
    return create_app(db_session_factory=db_session_factory)


async def _login(client: AsyncClient) -> None:
    credentials = base64.b64encode(b"admin:adminpass").decode()
    resp = await client.post(
        "/login", headers={"Authorization": f"Basic {credentials}"}
    )
    assert resp.status_code == HTTPStatus.OK
    assert "session" in resp.cookies


@pytest.mark.asyncio
async def test_stateful_chat_creates_conversation(
    app: asgi.App,
    db_session_factory: typing.Callable[[], AsyncSession],
    httpx_mock: HTTPXMock,
) -> None:
    httpx_mock.add_response(
        method="POST",
        url="https://openrouter.ai/api/v1/chat/completions",
        json={
            "id": "1",
            "object": "chat.completion",
            "created": 1,
            "model": "m",
            "choices": [
                {"index": 0, "message": {"role": "assistant", "content": "hi"}}
            ],
        },
    )

    async with AsyncClient(
        transport=ASGITransport(app=typing.cast("typing.Any", app)),
        base_url="https://test",
    ) as client:
        await _login(client)
        resp = await client.post("/chat/state", json={"message": "hello"})
    assert resp.status_code == HTTPStatus.OK
    data = resp.json()
    conv_id = uuid.UUID(data["conversation_id"])
    assert data["answer"] == "hi"
    async with db_session_factory() as session:
        conv = await session.get(Conversation, conv_id)
        assert conv is not None
        stmt = (
            select(Message)
            .where(Message.conversation_id == conv_id)
            .order_by(Message.created_at)
        )
        result = await session.execute(stmt)
        roles = [m.role for m in result.scalars().all()]
        assert roles == ["user", "assistant"]


@pytest.mark.asyncio
async def test_stateful_chat_appends(
    app: asgi.App,
    db_session_factory: typing.Callable[[], AsyncSession],
    httpx_mock: HTTPXMock,
) -> None:
    httpx_mock.add_response(
        method="POST",
        url="https://openrouter.ai/api/v1/chat/completions",
        json={
            "id": "1",
            "object": "chat.completion",
            "created": 1,
            "model": "m",
            "choices": [
                {"index": 0, "message": {"role": "assistant", "content": "a1"}}
            ],
        },
    )
    async with AsyncClient(
        transport=ASGITransport(app=typing.cast("typing.Any", app)),
        base_url="https://test",
    ) as client:
        await _login(client)
        resp1 = await client.post("/chat/state", json={"message": "a"})
        conv_id = resp1.json()["conversation_id"]

    httpx_mock.add_response(
        method="POST",
        url="https://openrouter.ai/api/v1/chat/completions",
        json={
            "id": "2",
            "object": "chat.completion",
            "created": 1,
            "model": "m",
            "choices": [
                {"index": 0, "message": {"role": "assistant", "content": "b1"}}
            ],
        },
    )
    async with AsyncClient(
        transport=ASGITransport(app=typing.cast("typing.Any", app)),
        base_url="https://test",
    ) as client:
        cookie = client.cookies["session"]
        client.cookies.clear()
        client.cookies.set("session", cookie)
        resp2 = await client.post(
            "/chat/state",
            json={"message": "b", "conversation_id": conv_id},
        )
    assert resp2.status_code == HTTPStatus.OK
    assert resp2.json()["conversation_id"] == conv_id
    async with db_session_factory() as session:
        stmt = (
            select(Message)
            .where(Message.conversation_id == uuid.UUID(conv_id))
            .order_by(Message.created_at)
        )
        result = await session.execute(stmt)
        roles = [m.role for m in result.scalars().all()]
        assert roles == ["user", "assistant", "user", "assistant"]
