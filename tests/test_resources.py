from __future__ import annotations

import typing
from http import HTTPStatus

import pytest
from httpx import ASGITransport, AsyncClient

if typing.TYPE_CHECKING:
    from falcon import asgi
    from pytest_httpx import HTTPXMock


import base64

from bournemouth.app import create_app


@pytest.fixture()
def app(monkeypatch: pytest.MonkeyPatch) -> asgi.App:
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    return create_app()


async def _login(client: AsyncClient) -> None:
    credentials = base64.b64encode(b"admin:adminpass").decode()
    resp = await client.post(
        "/login", headers={"Authorization": f"Basic {credentials}"}
    )
    assert resp.status_code == HTTPStatus.OK
    assert "session" in resp.cookies


pytest_plugins = ["pytest_httpx"]


@pytest.mark.asyncio
async def test_chat_returns_answer(
    app: asgi.App, httpx_mock: HTTPXMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
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
async def test_store_token_not_implemented(app: asgi.App) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=typing.cast("typing.Any", app)),
        base_url="https://test",
    ) as client:
        await _login(client)
        resp = await client.post(
            "/auth/openrouter-token",
            json={"api_key": "xyz"},
        )
    assert resp.status_code == HTTPStatus.NOT_IMPLEMENTED
    assert (
        resp.json()["title"]
        == f"{HTTPStatus.NOT_IMPLEMENTED.value} {HTTPStatus.NOT_IMPLEMENTED.phrase}"
    )


@pytest.mark.asyncio
async def test_store_token_missing_key(app: asgi.App) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=typing.cast("typing.Any", app)),
        base_url="https://test",
    ) as client:
        await _login(client)
        resp = await client.post("/auth/openrouter-token", json={})
    assert resp.status_code == HTTPStatus.BAD_REQUEST
