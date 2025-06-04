from __future__ import annotations

import base64
import datetime as dt
import typing
from http import HTTPStatus

import pytest
from freezegun import freeze_time
from httpx import ASGITransport, AsyncClient

from bournemouth.app import create_app


@pytest.mark.asyncio
async def test_login_sets_cookie() -> None:
    app = create_app()
    credentials = base64.b64encode(b"admin:adminpass").decode()
    async with AsyncClient(
        transport=ASGITransport(app=typing.cast("typing.Any", app)),  # pyright: ignore[reportUnknownArgumentType]
        base_url="https://test",
    ) as ac:
        resp = await ac.post(
            "/login", headers={"Authorization": f"Basic {credentials}"}
        )
    assert resp.status_code == HTTPStatus.OK
    assert "session" in resp.cookies


@pytest.mark.asyncio
async def test_login_rejects_bad_credentials() -> None:
    app = create_app()
    credentials = base64.b64encode(b"admin:wrong").decode()
    async with AsyncClient(
        transport=ASGITransport(app=typing.cast("typing.Any", app)),  # pyright: ignore[reportUnknownArgumentType]
        base_url="https://test",
    ) as ac:
        resp = await ac.post(
            "/login", headers={"Authorization": f"Basic {credentials}"}
        )
    assert resp.status_code == HTTPStatus.UNAUTHORIZED


@pytest.mark.asyncio
async def test_protected_endpoint_requires_cookie() -> None:
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=typing.cast("typing.Any", app)),  # pyright: ignore[reportUnknownArgumentType]
        base_url="https://test",
    ) as ac:
        resp = await ac.post("/chat", json={"message": "hi"})
    assert resp.status_code == HTTPStatus.UNAUTHORIZED


@pytest.mark.asyncio
async def test_empty_session_cookie_rejected() -> None:
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=typing.cast("typing.Any", app)),
        base_url="https://test",
        cookies={"session": ""},
    ) as ac:
        resp = await ac.post("/chat", json={"message": "hi"})
    assert resp.status_code == HTTPStatus.UNAUTHORIZED


@pytest.mark.asyncio
async def test_chat_with_valid_session() -> None:
    app = create_app()
    credentials = base64.b64encode(b"admin:adminpass").decode()
    async with AsyncClient(
        transport=ASGITransport(app=typing.cast("typing.Any", app)),  # pyright: ignore[reportUnknownArgumentType]
        base_url="https://test",
    ) as ac:
        login_resp = await ac.post(
            "/login", headers={"Authorization": f"Basic {credentials}"}
        )
        assert "session" in login_resp.cookies
        chat_resp = await ac.post("/chat", json={"message": "hi"})
    assert chat_resp.status_code == HTTPStatus.NOT_IMPLEMENTED


@pytest.mark.asyncio
async def test_health_does_not_require_auth() -> None:
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=typing.cast("typing.Any", app)),  # pyright: ignore[reportUnknownArgumentType]
        base_url="https://test",
    ) as ac:
        resp = await ac.get("/health")
    assert resp.status_code == HTTPStatus.OK


@pytest.mark.asyncio
async def test_expired_session_cookie_rejected() -> None:
    """Requests with expired session cookies should return 401."""
    app = create_app(session_timeout=1)
    credentials = base64.b64encode(b"admin:adminpass").decode()
    async with AsyncClient(
        transport=ASGITransport(app=typing.cast("typing.Any", app)),  # pyright: ignore[reportUnknownArgumentType]
        base_url="https://test",
    ) as ac:
        with freeze_time() as frozen:
            login_resp = await ac.post(
                "/login", headers={"Authorization": f"Basic {credentials}"}
            )
            assert login_resp.status_code == HTTPStatus.OK
            assert "session" in login_resp.cookies
            frozen.tick(delta=dt.timedelta(seconds=2))
            check_resp = await ac.post("/chat", json={"message": "hi"})
    assert check_resp.status_code == HTTPStatus.UNAUTHORIZED
