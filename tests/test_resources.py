"""Integration tests for REST resources."""
from __future__ import annotations

import typing
from http import HTTPStatus

import pytest
from httpx import ASGITransport, AsyncClient

if typing.TYPE_CHECKING:
    from falcon import asgi
    from pytest_httpx import HTTPXMock
    from sqlalchemy.ext.asyncio import AsyncSession

    from bournemouth.openrouter import ChatCompletionResponse, ChatMessage
    from bournemouth.openrouter_service import OpenRouterService


import base64

from sqlalchemy import select, update

from bournemouth import chat_service
from bournemouth.app import create_app
from bournemouth.models import UserAccount


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
async def test_chat_returns_answer(app: asgi.App, httpx_mock: HTTPXMock) -> None:
    """The chat endpoint should return the assistant's answer."""
    httpx_mock.add_response(
        method="POST",
        url="https://openrouter.ai/api/v1/chat/completions",
        json={
            "id": "1",
            "object": "chat.completion",
            "created": 1,
            "model": "deepseek/deepseek-chat-v3-0324:free",
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
        resp = await client.post("/chat", json={"message": "hello"})
    assert resp.status_code == HTTPStatus.OK
    assert resp.json()["answer"] == "hi"


@pytest.mark.asyncio
async def test_chat_missing_message(app: asgi.App) -> None:
    """Requests without a message should fail validation."""
    async with AsyncClient(
        transport=ASGITransport(app=typing.cast("typing.Any", app)),
        base_url="https://test",
    ) as client:
        await _login(client)
        resp = await client.post("/chat", json={})
    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_store_token(
    app: asgi.App, db_session_factory: typing.Callable[[], AsyncSession]
) -> None:
    """Persist an API token for the authenticated user."""
    async with AsyncClient(
        transport=ASGITransport(app=typing.cast("typing.Any", app)),
        base_url="https://test",
    ) as client:
        await _login(client)
        resp = await client.post(
            "/auth/openrouter-token",
            json={"api_key": "xyz"},
        )
    assert resp.status_code == HTTPStatus.NO_CONTENT
    async with db_session_factory() as session:
        result = await session.execute(
            select(UserAccount.openrouter_token_enc).where(
                UserAccount.google_sub == "admin"
            )
        )
        stored = result.scalar_one()
        assert stored == b"xyz"


@pytest.mark.asyncio
async def test_store_token_missing_key(app: asgi.App) -> None:
    """Omitting the token should return a validation error."""
    async with AsyncClient(
        transport=ASGITransport(app=typing.cast("typing.Any", app)),
        base_url="https://test",
    ) as client:
        await _login(client)
        resp = await client.post("/auth/openrouter-token", json={})
    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_store_token_non_string(app: asgi.App) -> None:
    """Non-string tokens should be rejected."""
    async with AsyncClient(
        transport=ASGITransport(app=typing.cast("typing.Any", app)),
        base_url="https://test",
    ) as client:
        await _login(client)
        resp = await client.post("/auth/openrouter-token", json={"api_key": 1})
    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_store_token_empty_string(
    app: asgi.App, db_session_factory: typing.Callable[[], AsyncSession]
) -> None:
    """Empty strings should clear the stored token."""
    async with AsyncClient(
        transport=ASGITransport(app=typing.cast("typing.Any", app)),
        base_url="https://test",
    ) as client:
        await _login(client)
        resp = await client.post(
            "/auth/openrouter-token",
            json={"api_key": ""},
        )
    assert resp.status_code == HTTPStatus.NO_CONTENT
    async with db_session_factory() as session:
        result = await session.execute(
            select(UserAccount.openrouter_token_enc).where(
                UserAccount.google_sub == "admin"
            )
        )
        stored = result.scalar_one()
        assert stored is None


@pytest.mark.asyncio
async def test_chat_empty_choices(app: asgi.App, httpx_mock: HTTPXMock) -> None:
    """A lack of choices from the service results in a 502 response."""
    httpx_mock.add_response(
        method="POST",
        url="https://openrouter.ai/api/v1/chat/completions",
        json={
            "id": "1",
            "object": "chat.completion",
            "created": 1,
            "model": "deepseek/deepseek-chat-v3-0324:free",
            "choices": [],
        },
    )

    async with AsyncClient(
        transport=ASGITransport(app=typing.cast("typing.Any", app)),
        base_url="https://test",
    ) as client:
        await _login(client)
        resp = await client.post("/chat", json={"message": "hello"})
    assert resp.status_code == HTTPStatus.BAD_GATEWAY


@pytest.mark.asyncio
async def test_chat_missing_token(
    app: asgi.App, db_session_factory: typing.Callable[[], AsyncSession]
) -> None:
    """Missing OpenRouter token should yield a 401 response."""
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
        resp = await client.post("/chat", json={"message": "hi"})
    assert resp.status_code == HTTPStatus.UNAUTHORIZED


@pytest.mark.asyncio
async def test_chat_unexpected_error_returns_500(
    app: asgi.App, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unexpected service errors should map to HTTP 500."""
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
        resp = await client.post("/chat", json={"message": "oops"})
    assert resp.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
