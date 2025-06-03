from __future__ import annotations

import base64

import pytest
from httpx import ASGITransport, AsyncClient
from typing import Any, cast

from bournemouth.app import create_app


@pytest.mark.asyncio
async def test_login_sets_cookie() -> None:
    app = create_app()
    credentials = base64.b64encode(b"admin:adminpass").decode()
    async with AsyncClient(
        transport=ASGITransport(app=cast(Any, app)),  # pyright: ignore[reportUnknownArgumentType]
        base_url="http://test",
    ) as ac:
        resp = await ac.post(
            "/login", headers={"Authorization": f"Basic {credentials}"}
        )
    assert resp.status_code == 200
    assert "session" in resp.cookies


@pytest.mark.asyncio
async def test_login_rejects_bad_credentials() -> None:
    app = create_app()
    credentials = base64.b64encode(b"admin:wrong").decode()
    async with AsyncClient(
        transport=ASGITransport(app=cast(Any, app)),  # pyright: ignore[reportUnknownArgumentType]
        base_url="http://test",
    ) as ac:
        resp = await ac.post(
            "/login", headers={"Authorization": f"Basic {credentials}"}
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_protected_endpoint_requires_cookie() -> None:
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=cast(Any, app)),  # pyright: ignore[reportUnknownArgumentType]
        base_url="http://test",
    ) as ac:
        resp = await ac.post("/chat", json={"message": "hi"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_chat_with_valid_session() -> None:
    app = create_app()
    credentials = base64.b64encode(b"admin:adminpass").decode()
    async with AsyncClient(
        transport=ASGITransport(app=cast(Any, app)),  # pyright: ignore[reportUnknownArgumentType]
        base_url="http://test",
    ) as ac:
        login_resp = await ac.post(
            "/login", headers={"Authorization": f"Basic {credentials}"}
        )
        session_cookie = login_resp.cookies.get("session")
        assert session_cookie is not None
        chat_resp = await ac.post(
            "/chat",
            json={"message": "hi"},
            cookies={"session": session_cookie},
        )
    assert chat_resp.status_code == 200


@pytest.mark.asyncio
async def test_health_does_not_require_auth() -> None:
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=cast(Any, app)),  # pyright: ignore[reportUnknownArgumentType]
        base_url="http://test",
    ) as ac:
        resp = await ac.get("/health")
    assert resp.status_code == 200
