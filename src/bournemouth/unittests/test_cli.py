from __future__ import annotations

import json
import os
import typing

import pytest

# Skip all tests in this module if CLI dependencies are not available
pytest.importorskip("typer", reason="CLI dependency group not installed")
pytest.importorskip("textual", reason="CLI dependency group not installed")

from bournemouth import cli

if typing.TYPE_CHECKING:
    from pathlib import Path

    from pytest_httpx import HTTPXMock


@pytest.mark.asyncio  # pyright: ignore[reportUntypedFunctionDecorator]
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
    if os.name == "posix":
        assert (cookie_file.stat().st_mode & 0o777) == 0o600
    req = httpx_mock.get_requests()[0]
    assert req.headers["authorization"].startswith("Basic ")


@pytest.mark.asyncio  # pyright: ignore[reportUntypedFunctionDecorator]
async def test_token_posts_correctly(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url="http://localhost:8000/auth/openrouter-token",
        status_code=204,
    )
    session = cli.Session("http://localhost:8000", "abc123")
    ok = await cli.token_request(session, "tok")
    assert ok
    req = httpx_mock.get_requests()[0]
    assert req.headers["cookie"] == "session=abc123"
    assert typing.cast(
        "dict[str, typing.Any]",
        json.loads(req.content.decode()),
    ) == {"api_key": "tok"}


@pytest.mark.asyncio  # pyright: ignore[reportUntypedFunctionDecorator]
async def test_chat_sends_history(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url="http://localhost:8000/chat",
        json={"answer": "hi"},
    )
    history = [{"role": "assistant", "content": "hello"}]
    session = cli.Session("http://localhost:8000", "abc123")
    answer = await cli.chat_request(session, "hi", history)
    assert answer == "hi"
    req = httpx_mock.get_requests()[0]
    sent = typing.cast(
        "dict[str, typing.Any]",
        json.loads(req.content.decode()),
    )
    assert sent["message"] == "hi"
    assert sent["history"] == history
    assert req.headers["cookie"] == "session=abc123"
