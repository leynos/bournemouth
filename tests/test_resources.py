from __future__ import annotations

import typing
from http import HTTPStatus

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

if typing.TYPE_CHECKING:
    from falcon import asgi
    from pytest_httpx import HTTPXMock


import base64

from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from bournemouth.app import create_app
from bournemouth.models import Base, UserAccount


@pytest_asyncio.fixture()
async def db_session_factory() -> typing.AsyncIterator[
    typing.Callable[[], AsyncSession]
]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async_session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn, async_session_factory() as session:
        await conn.run_sync(Base.metadata.create_all)
        async with session.begin():
            session.add(
                UserAccount(
                    google_sub="admin",
                    email="admin@example.com",
                    openrouter_token_enc=b"k",
                )
            )

    def factory() -> AsyncSession:
        return async_session_factory()

    yield factory
    await engine.dispose()


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


pytest_plugins = ["pytest_httpx"]


@pytest.mark.asyncio
async def test_chat_returns_answer(app: asgi.App, httpx_mock: HTTPXMock) -> None:
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
    async with AsyncClient(
        transport=ASGITransport(app=typing.cast("typing.Any", app)),
        base_url="https://test",
    ) as client:
        await _login(client)
        resp = await client.post("/chat", json={})
    assert resp.status_code == HTTPStatus.BAD_REQUEST


@pytest.mark.asyncio
async def test_store_token(
    app: asgi.App, db_session_factory: typing.Callable[[], AsyncSession]
) -> None:
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
    async with AsyncClient(
        transport=ASGITransport(app=typing.cast("typing.Any", app)),
        base_url="https://test",
    ) as client:
        await _login(client)
        resp = await client.post("/auth/openrouter-token", json={})
    assert resp.status_code == HTTPStatus.BAD_REQUEST
