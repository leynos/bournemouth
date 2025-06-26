"""Integration tests for authentication and session handling."""
from __future__ import annotations

import base64
import datetime as dt
import typing
from http import HTTPStatus

import pytest
from freezegun import freeze_time
from httpx import ASGITransport, AsyncClient

if typing.TYPE_CHECKING:
    from pytest_httpx import HTTPXMock


if typing.TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from bournemouth.app import create_app

type SessionFactory = typing.Callable[[], AsyncSession]


@pytest.mark.asyncio
async def test_login_sets_cookie(
    db_session_factory: SessionFactory,
) -> None:
    """Valid credentials should set a session cookie."""
    app = create_app(db_session_factory=db_session_factory)
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
async def test_login_rejects_bad_credentials(
    db_session_factory: SessionFactory,
) -> None:
    """Incorrect credentials result in 401."""
    app = create_app(db_session_factory=db_session_factory)
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
async def test_protected_endpoint_requires_cookie(
    db_session_factory: SessionFactory,
) -> None:
    """Protected endpoints require authentication."""
    app = create_app(db_session_factory=db_session_factory)
    async with AsyncClient(
        transport=ASGITransport(app=typing.cast("typing.Any", app)),  # pyright: ignore[reportUnknownArgumentType]
        base_url="https://test",
    ) as ac:
        resp = await ac.post("/chat", json={"message": "hi"})
    assert resp.status_code == HTTPStatus.UNAUTHORIZED


@pytest.mark.asyncio
async def test_empty_session_cookie_rejected(
    db_session_factory: SessionFactory,
) -> None:
    """Empty session cookies are treated as invalid."""
    app = create_app(db_session_factory=db_session_factory)
    async with AsyncClient(
        transport=ASGITransport(app=typing.cast("typing.Any", app)),
        base_url="https://test",
        cookies={"session": ""},
    ) as ac:
        resp = await ac.post("/chat", json={"message": "hi"})
    assert resp.status_code == HTTPStatus.UNAUTHORIZED


@pytest.mark.asyncio
async def test_chat_with_valid_session(
    httpx_mock: HTTPXMock,
    db_session_factory: SessionFactory,
) -> None:
    """Chat endpoint works when a valid session is provided."""
    app = create_app(db_session_factory=db_session_factory)
    credentials = base64.b64encode(b"admin:adminpass").decode()
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
        transport=ASGITransport(app=typing.cast("typing.Any", app)),  # pyright: ignore[reportUnknownArgumentType]
        base_url="https://test",
    ) as ac:
        login_resp = await ac.post(
            "/login", headers={"Authorization": f"Basic {credentials}"}
        )
        assert "session" in login_resp.cookies
        chat_resp = await ac.post("/chat", json={"message": "hi"})
    assert chat_resp.status_code == HTTPStatus.OK


@pytest.mark.asyncio
async def test_health_does_not_require_auth(
    db_session_factory: SessionFactory,
) -> None:
    """Health checks should be accessible without authentication."""
    app = create_app(db_session_factory=db_session_factory)
    async with AsyncClient(
        transport=ASGITransport(app=typing.cast("typing.Any", app)),  # pyright: ignore[reportUnknownArgumentType]
        base_url="https://test",
    ) as ac:
        resp = await ac.get("/health")
    assert resp.status_code == HTTPStatus.OK


@pytest.mark.asyncio
async def test_expired_session_cookie_rejected(
    db_session_factory: SessionFactory,
) -> None:
    """Requests with expired session cookies should return 401."""
    app = create_app(session_timeout=1, db_session_factory=db_session_factory)
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
