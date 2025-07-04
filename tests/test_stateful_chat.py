"""Tests for the stateful chat API."""

import base64
import typing
import uuid
from http import HTTPStatus

import pytest
from falcon import asgi
from httpx import ASGITransport, AsyncClient
from pytest_httpx import HTTPXMock
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bournemouth import chat_service
from bournemouth.app import create_app
from bournemouth.models import Conversation, Message, MessageRole, UserAccount
from bournemouth.openrouter import ChatCompletionResponse, ChatMessage
from bournemouth.openrouter_service import OpenRouterService


@pytest.fixture
def app(db_session_factory: typing.Callable[[], AsyncSession]) -> asgi.App:
    """Create an application instance for testing."""
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
    """A new conversation is created and messages are stored."""
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
    assert conv_id.version == 7
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


@pytest.mark.timeout(5)
@pytest.mark.asyncio
async def test_stateful_chat_appends(
    app: asgi.App,
    db_session_factory: typing.Callable[[], AsyncSession],
    httpx_mock: HTTPXMock,
) -> None:
    """Subsequent messages append to the conversation."""
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
        cookie = client.cookies["session"]

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


@pytest.mark.asyncio
async def test_stateful_chat_missing_token(
    app: asgi.App, db_session_factory: typing.Callable[[], AsyncSession]
) -> None:
    """Return 401 if the user has not stored an API token."""
    async with db_session_factory() as session:
        await session.execute(
            update(UserAccount)
            .where(UserAccount.google_sub == "admin")
            .values(openrouter_token_enc=None)
        )
        await session.commit()

    async with AsyncClient(
        transport=ASGITransport(app=typing.cast("typing.Any", app)),
        base_url="https://test",
    ) as client:
        await _login(client)
        resp = await client.post("/chat/state", json={"message": "hi"})
    assert resp.status_code == HTTPStatus.UNAUTHORIZED


@pytest.mark.asyncio
async def test_stateful_chat_persists_user_message_on_timeout(
    app: asgi.App,
    db_session_factory: typing.Callable[[], AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """User messages are persisted even when the service times out."""
    async def fail(
        service: OpenRouterService,
        api_key: str,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
    ) -> ChatCompletionResponse:
        raise chat_service.OpenRouterServiceTimeoutError("boom")

    monkeypatch.setattr(chat_service, "chat_with_service", fail)

    async with AsyncClient(
        transport=ASGITransport(app=typing.cast("typing.Any", app)),
        base_url="https://test",
    ) as client:
        await _login(client)
        resp = await client.post("/chat/state", json={"message": "oops"})
    assert resp.status_code == HTTPStatus.GATEWAY_TIMEOUT

    async with db_session_factory() as session:
        conv = (await session.execute(select(Conversation))).scalar_one()
        result = await session.execute(
            select(Message.role)
            .where(Message.conversation_id == conv.id)
            .order_by(Message.created_at)
        )
        roles = list(result.scalars().all())
        assert roles == [MessageRole.USER]


@pytest.mark.asyncio
async def test_stateful_chat_handles_unexpected_error(
    app: asgi.App,
    db_session_factory: typing.Callable[[], AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unexpected service errors are handled gracefully."""
    async def fail(
        service: OpenRouterService,
        api_key: str,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
    ) -> ChatCompletionResponse:
        raise RuntimeError("boom")

    monkeypatch.setattr(chat_service, "chat_with_service", fail)

    async with AsyncClient(
        transport=ASGITransport(app=typing.cast("typing.Any", app)),
        base_url="https://test",
    ) as client:
        await _login(client)
        resp = await client.post("/chat/state", json={"message": "oops"})
    assert resp.status_code == HTTPStatus.INTERNAL_SERVER_ERROR

    async with db_session_factory() as session:
        conv = (await session.execute(select(Conversation))).scalar_one()
        result = await session.execute(
            select(Message.role)
            .where(Message.conversation_id == conv.id)
            .order_by(Message.created_at)
        )
        roles = list(result.scalars().all())
        assert roles == [MessageRole.USER]
