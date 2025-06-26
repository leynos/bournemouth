"""Command line interface helpers for the chat server."""

from __future__ import annotations

import dataclasses as dc
import os
import typing
from contextlib import suppress
from pathlib import Path

import httpx
import typer
from textual.app import App, ComposeResult
from textual.widgets import Button, Input, Log, Static

if typing.TYPE_CHECKING:
    import collections.abc as cabc


@dc.dataclass(slots=True)
class Session:
    """Connection settings for API requests."""

    host: str
    cookie: str | None = None


COOKIE_PATH = Path(
    os.environ.get("BOURNEMOUTH_COOKIE", str(Path.home() / ".bournemouth_cookie"))
)

app = typer.Typer(help="Command line interface for Bournemouth chat")


async def _post(
    session: Session,
    path: str,
    *,
    auth: tuple[str, str] | None = None,
    json: dict[str, typing.Any] | None = None,
) -> httpx.Response:
    """Send a POST request and return the response."""
    kwargs: dict[str, typing.Any] = {"base_url": session.host}
    if session.cookie:
        kwargs["cookies"] = {"session": session.cookie}
    async with httpx.AsyncClient(**kwargs) as client:
        if auth is None:
            resp = await client.post(path, json=json)
        else:
            resp = await client.post(path, auth=auth, json=json)
    resp.raise_for_status()
    return resp


async def _login_request(session: Session, username: str, password: str) -> str:
    resp = await _post(session, "/login", auth=(username, password))
    if not (cookie := resp.cookies.get("session")):
        raise RuntimeError("missing session cookie")
    return cookie


async def token_request(session: Session, token: str) -> bool:
    """Send a token to the server and return whether it was stored."""
    resp = await _post(
        session,
        "/auth/openrouter-token",
        json={"api_key": token},
    )
    return resp.status_code == 204


async def chat_request(
    session: Session, message: str, history: list[dict[str, str]]
) -> str:
    """Send a chat request and return the assistant's reply."""
    resp = await _post(
        session,
        "/chat",
        json={"message": message, "history": history},
    )
    data = typing.cast("dict[str, typing.Any]", resp.json())
    if "answer" not in data:
        raise RuntimeError(f"Malformed chat response: missing 'answer' key in {data!r}")
    return typing.cast("str", data["answer"])


async def perform_login(
    host: str, username: str, password: str, cookie_file: Path = COOKIE_PATH
) -> str:
    """Log in to the server and persist the session cookie."""
    cookie = await _login_request(Session(host), username, password)
    cookie_file.write_text(cookie)
    if os.name == "posix":
        with suppress(OSError, PermissionError):
            cookie_file.chmod(0o600)
    return cookie


class FormApp(App):  # pyright: ignore[reportUntypedBaseClass, reportMissingTypeArgument]
    """Small form-based application."""

    def __init__(
        self,
        session: Session,
        fields: list[tuple[str, str, bool]],
        submit_label: str,
        submit_cb: cabc.Callable[..., cabc.Awaitable[str | None]],
    ) -> None:
        super().__init__()
        self.session = session
        self.fields = fields
        self.submit_label = submit_label
        self.submit_cb = submit_cb

    def compose(self) -> ComposeResult:
        for placeholder, fid, is_pw in self.fields:
            yield Input(placeholder=placeholder, password=is_pw, id=fid)
        yield Button(self.submit_label, id="action")
        yield Static(id="status")

    async def on_button_pressed(self, event: Button.Pressed) -> None:  # pyright: ignore[reportUnknownArgumentType]
        if event.button.id != "action":
            return
        data = {
            fid: self.query_one(f"#{fid}", Input).value for _, fid, _ in self.fields
        }
        status = self.query_one("#status", Static)
        try:
            msg = await self.submit_cb(self.session, **data)
        except Exception as exc:  # noqa: BLE001
            status.update(f"{self.submit_label} failed: {exc}")
            return
        status.update(msg or f"{self.submit_label} succeeded")
        await self.action_quit()


class ChatApp(App):  # pyright: ignore[reportUntypedBaseClass, reportMissingTypeArgument]
    def __init__(self, session: Session) -> None:
        super().__init__()
        self.session = session
        self.history: list[dict[str, str]] = []

    def compose(self) -> ComposeResult:
        yield Log(id="log")
        yield Input(placeholder="Message", id="input")

    async def on_input_submitted(self, event: Input.Submitted) -> None:  # pyright: ignore[reportUnknownArgumentType]
        text = event.value
        log = self.query_one("#log", Log)  # pyright: ignore[reportUnknownArgumentType]
        log.write(f"You: {text}")
        answer = await chat_request(self.session, text, self.history)
        log.write(f"Assistant: {answer}")
        self.history.append({"role": "user", "content": text})
        self.history.append({"role": "assistant", "content": answer})
        self.query_one("#input", Input).value = ""


async def _login_form(session: Session, *, user: str, password: str) -> str | None:
    await perform_login(session.host, user, password, COOKIE_PATH)
    return None


@app.command()  # pyright: ignore[reportUntypedFunctionDecorator]
def login(
    host: str = typer.Option(
        "http://localhost:8000", "--host", help="Chat server host URL"
    ),
) -> None:
    """Login to the chat server."""
    session = Session(host)
    FormApp(
        session,
        fields=[("Username", "user", False), ("Password", "password", True)],
        submit_label="Login",
        submit_cb=_login_form,
    ).run()


async def _token_form(session: Session, *, token: str) -> str | None:
    if session.cookie is None:
        raise RuntimeError("missing session cookie")
    ok = await token_request(session, token)
    if not ok:
        raise RuntimeError("token save failed")
    return "Token saved"


@app.command()  # pyright: ignore[reportUntypedFunctionDecorator]
def token(
    host: str = typer.Option(
        "http://localhost:8000", "--host", help="Chat server host URL"
    ),
) -> None:
    """Store your OpenRouter token."""
    if not COOKIE_PATH.exists():
        typer.echo("Please login first.")
        raise typer.Exit(code=1)
    cookie = COOKIE_PATH.read_text().strip()
    session = Session(host, cookie)
    FormApp(
        session,
        fields=[("OpenRouter token", "token", False)],
        submit_label="Save",
        submit_cb=_token_form,
    ).run()


@app.command()  # pyright: ignore[reportUntypedFunctionDecorator]
def chat(
    host: str = typer.Option(
        "http://localhost:8000", "--host", help="Chat server host URL"
    ),
) -> None:
    """Chat with the assistant."""
    if not COOKIE_PATH.exists():
        typer.echo("Please login first.")
        raise typer.Exit(code=1)
    cookie = COOKIE_PATH.read_text().strip()
    ChatApp(Session(host, cookie)).run()


__all__ = [
    "app",
    "chat_request",
    "perform_login",
    "token_request",
]
