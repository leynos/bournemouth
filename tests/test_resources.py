from __future__ import annotations

import typing
from http import HTTPStatus

import pytest
from httpx import ASGITransport, AsyncClient

if typing.TYPE_CHECKING:
    from falcon import asgi

from bournemouth.app import create_app


@pytest.fixture()
def app() -> asgi.App:
    return create_app()


@pytest.mark.asyncio
async def test_chat_not_implemented(app: asgi.App) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=typing.cast("typing.Any", app)),
        base_url="http://test",
    ) as client:
        resp = await client.post("/chat", json={"message": "hello"})
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
        resp = await client.post("/chat", json={})
    assert resp.status_code == HTTPStatus.BAD_REQUEST


@pytest.mark.asyncio
async def test_store_token_not_implemented(app: asgi.App) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=typing.cast("typing.Any", app)),
        base_url="http://test",
    ) as client:
        resp = await client.post("/auth/openrouter-token", json={"api_key": "xyz"})
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
        resp = await client.post("/auth/openrouter-token", json={})
    assert resp.status_code == HTTPStatus.BAD_REQUEST
