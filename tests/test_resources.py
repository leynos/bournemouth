from __future__ import annotations

import typing
from http import HTTPStatus

import pytest
from httpx import ASGITransport, AsyncClient

if typing.TYPE_CHECKING:
    from falcon import asgi

import base64

from bournemouth.app import create_app


@pytest.fixture()
def app() -> asgi.App:
    return create_app()


async def _login(client: AsyncClient) -> str:
    credentials = base64.b64encode(b"admin:adminpass").decode()
    resp = await client.post(
        "/login", headers={"Authorization": f"Basic {credentials}"}
    )
    return resp.cookies["session"]


@pytest.mark.asyncio
async def test_chat_not_implemented(app: asgi.App) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=typing.cast("typing.Any", app)),
        base_url="http://test",
    ) as client:
        cookie = await _login(client)
        resp = await client.post(
            "/chat", json={"message": "hello"}, cookies={"session": cookie}
        )
    assert resp.status_code == HTTPStatus.NOT_IMPLEMENTED
    assert (
        resp.json()["title"]
        == f"{HTTPStatus.NOT_IMPLEMENTED.value} {HTTPStatus.NOT_IMPLEMENTED.phrase}"
    )


@pytest.mark.asyncio
async def test_chat_missing_message(app: asgi.App) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=typing.cast("typing.Any", app)),
        base_url="http://test",
    ) as client:
        cookie = await _login(client)
        resp = await client.post("/chat", json={}, cookies={"session": cookie})
    assert resp.status_code == HTTPStatus.BAD_REQUEST


@pytest.mark.asyncio
async def test_store_token_not_implemented(app: asgi.App) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=typing.cast("typing.Any", app)),
        base_url="http://test",
    ) as client:
        cookie = await _login(client)
        resp = await client.post(
            "/auth/openrouter-token",
            json={"api_key": "xyz"},
            cookies={"session": cookie},
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
        base_url="http://test",
    ) as client:
        cookie = await _login(client)
        resp = await client.post(
            "/auth/openrouter-token", json={}, cookies={"session": cookie}
        )
    assert resp.status_code == HTTPStatus.BAD_REQUEST
