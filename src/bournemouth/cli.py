from __future__ import annotations

import typing
from pathlib import Path

import httpx
import typer
from textual.app import App, ComposeResult
from textual.widgets import Button, Input, Static, TextLog

COOKIE_PATH = Path.home() / ".bournemouth_cookie"

app = typer.Typer(help="Command line interface for Bournemouth chat")


async def _login_request(host: str, username: str, password: str) -> str:
    async with httpx.AsyncClient(base_url=host) as client:
        resp = await client.post("/login", auth=(username, password))
        resp.raise_for_status()
        cookie = resp.cookies.get("session")
        if not cookie:
            raise RuntimeError("missing session cookie")
        return cookie


async def _token_request(host: str, cookie: str, token: str) -> bool:
    async with httpx.AsyncClient(base_url=host, cookies={"session": cookie}) as client:
        resp = await client.post("/auth/openrouter-token", json={"api_key": token})
    return resp.status_code == 204


async def _chat_request(
    host: str, cookie: str, message: str, history: list[dict[str, str]]
) -> str:
    async with httpx.AsyncClient(base_url=host, cookies={"session": cookie}) as client:
        resp = await client.post("/chat", json={"message": message, "history": history})
        resp.raise_for_status()
    data = typing.cast("dict[str, typing.Any]", resp.json())
    return typing.cast("str", data.get("answer"))


async def perform_login(
    host: str, username: str, password: str, cookie_file: Path = COOKIE_PATH
) -> str:
    cookie = await _login_request(host, username, password)
    cookie_file.write_text(cookie)
    return cookie


class LoginApp(App):  # pyright: ignore[reportUntypedBaseClass]
    def __init__(self, host: str, cookie_file: Path) -> None:
        super().__init__()
        self.host = host
        self.cookie_file = cookie_file

    def compose(self) -> ComposeResult:
        yield Input(placeholder="Username", id="user")
        yield Input(placeholder="Password", password=True, id="pass")
        yield Button("Login", id="login")
        yield Static(id="status")

    async def on_button_pressed(self, event: Button.Pressed) -> None:  # pyright: ignore[reportUnknownArgumentType]
        if event.button.id != "login":
            return
        username = typing.cast("str", self.query_one("#user", Input).value)
        password = typing.cast("str", self.query_one("#pass", Input).value)
        status = self.query_one("#status", Static)
        try:
            await perform_login(self.host, username, password, self.cookie_file)
        except Exception as exc:  # noqa: BLE001
            status.update(f"Login failed: {exc}")
            return
        status.update("Login successful")
        await self.action_quit()


class TokenApp(App):  # pyright: ignore[reportUntypedBaseClass]
    def __init__(self, host: str, cookie: str) -> None:
        super().__init__()
        self.host = host
        self.cookie = cookie

    def compose(self) -> ComposeResult:
        yield Input(placeholder="OpenRouter token", id="token")
        yield Button("Save", id="save")
        yield Static(id="status")

    async def on_button_pressed(self, event: Button.Pressed) -> None:  # pyright: ignore[reportUnknownArgumentType]
        if event.button.id != "save":
            return
        token = typing.cast("str", self.query_one("#token", Input).value)
        status = self.query_one("#status", Static)
        ok = await _token_request(self.host, self.cookie, token)
        if ok:
            status.update("Token saved")
        else:
            status.update("Failed to save token")


class ChatApp(App):  # pyright: ignore[reportUntypedBaseClass]
    def __init__(self, host: str, cookie: str) -> None:
        super().__init__()
        self.host = host
        self.cookie = cookie
        self.history: list[dict[str, str]] = []

    def compose(self) -> ComposeResult:
        yield TextLog(id="log")
        yield Input(placeholder="Message", id="input")

    async def on_input_submitted(self, event: Input.Submitted) -> None:  # pyright: ignore[reportUnknownArgumentType]
        text = typing.cast("str", event.value)
        log = self.query_one("#log", TextLog)
        log.write(f"You: {text}")
        answer = await _chat_request(self.host, self.cookie, text, self.history)
        log.write(f"Assistant: {answer}")
        self.history.append({"role": "user", "content": text})
        self.history.append({"role": "assistant", "content": answer})
        self.query_one("#input", Input).value = ""


@app.command()  # pyright: ignore[reportUntypedFunctionDecorator]
def login(host: str = "http://localhost:8000") -> None:
    """Login to the chat server."""
    LoginApp(host, COOKIE_PATH).run()


@app.command()  # pyright: ignore[reportUntypedFunctionDecorator]
def token(host: str = "http://localhost:8000") -> None:
    """Store your OpenRouter token."""
    if not COOKIE_PATH.exists():
        typer.echo("Please login first.")
        raise typer.Exit(code=1)
    cookie = COOKIE_PATH.read_text().strip()
    TokenApp(host, cookie).run()


@app.command()  # pyright: ignore[reportUntypedFunctionDecorator]
def chat(host: str = "http://localhost:8000") -> None:
    """Chat with the assistant."""
    if not COOKIE_PATH.exists():
        typer.echo("Please login first.")
        raise typer.Exit(code=1)
    cookie = COOKIE_PATH.read_text().strip()
    ChatApp(host, cookie).run()


__all__ = [
    "_chat_request",
    "_token_request",
    "app",
    "perform_login",
]
