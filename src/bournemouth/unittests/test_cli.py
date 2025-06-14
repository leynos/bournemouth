from __future__ import annotations

import json
import typing

import pytest

from bournemouth import cli

if typing.TYPE_CHECKING:
    from pathlib import Path

    from pytest_httpx import HTTPXMock


@pytest.mark.asyncio
async def test_login_saves_cookie(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    cookie_file = tmp_path / "cookie"
    httpx_mock.add_response(
        method="POST",
        url="http://localhost:8000/login",
        json={"status": "logged_in"},
        headers={"set-cookie": "session=abc123"},
    )
    await cli.perform_login(
        "http://localhost:8000", "alice", "secret", cookie_file=cookie_file
    )
    assert cookie_file.read_text() == "abc123"
    req = httpx_mock.get_requests()[0]
    assert req.headers["authorization"].startswith("Basic ")


@pytest.mark.asyncio
async def test_token_posts_correctly(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url="http://localhost:8000/auth/openrouter-token",
        status_code=204,
    )
    ok = await cli._token_request("http://localhost:8000", "abc123", "tok")  # pyright: ignore[reportPrivateUsage]
    assert ok
    req = httpx_mock.get_requests()[0]
    assert req.headers["cookie"] == "session=abc123"
    assert json.loads(req.content.decode()) == {"api_key": "tok"}


@pytest.mark.asyncio
async def test_chat_sends_history(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url="http://localhost:8000/chat",
        json={"answer": "hi"},
    )
    history = [{"role": "assistant", "content": "hello"}]
    answer = await cli._chat_request("http://localhost:8000", "abc123", "hi", history)  # pyright: ignore[reportPrivateUsage]
    assert answer == "hi"
    req = httpx_mock.get_requests()[0]
    sent = json.loads(req.content.decode())
    assert sent["message"] == "hi"
    assert sent["history"] == history
    assert req.headers["cookie"] == "session=abc123"
