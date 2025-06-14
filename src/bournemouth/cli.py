from __future__ import annotations

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


COOKIE_PATH = Path(
    os.environ.get("BOURNEMOUTH_COOKIE", str(Path.home() / ".bournemouth_cookie"))
)

app = typer.Typer(help="Command line interface for Bournemouth chat")


async def _post(
    host: str,
    path: str,
    *,
    auth: tuple[str, str] | None = None,
    cookie: str | None = None,
    json: dict[str, typing.Any] | None = None,
) -> httpx.Response:
    """Send a POST request to ``host`` and return the response."""
    kwargs: dict[str, typing.Any] = {"base_url": host}
    if cookie:
        kwargs["cookies"] = {"session": cookie}
    async with httpx.AsyncClient(**kwargs) as client:
        if auth is None:
            resp = await client.post(path, json=json)
        else:
            resp = await client.post(path, auth=auth, json=json)
    resp.raise_for_status()
    return resp


async def _login_request(host: str, username: str, password: str) -> str:
    resp = await _post(host, "/login", auth=(username, password))
    if not (cookie := resp.cookies.get("session")):
        raise RuntimeError("missing session cookie")
    return cookie


async def _token_request(host: str, cookie: str, token: str) -> bool:
    resp = await _post(
        host,
        "/auth/openrouter-token",
        cookie=cookie,
        json={"api_key": token},
    )
    return resp.status_code == 204


async def _chat_request(
    host: str, cookie: str, message: str, history: list[dict[str, str]]
) -> str:
    resp = await _post(
        host,
        "/chat",
        cookie=cookie,
        json={"message": message, "history": history},
    )
    data = typing.cast("dict[str, typing.Any]", resp.json())
    if "answer" not in data:
        raise RuntimeError(f"Malformed chat response: missing 'answer' key in {data!r}")
    return typing.cast("str", data["answer"])


async def perform_login(
    host: str, username: str, password: str, cookie_file: Path = COOKIE_PATH
) -> str:
    cookie = await _login_request(host, username, password)
    cookie_file.write_text(cookie)
    if os.name == "posix":
        with suppress(OSError, PermissionError):
            cookie_file.chmod(0o600)
    return cookie


class FormApp(App):  # pyright: ignore[reportUntypedBaseClass, reportMissingTypeArgument]
    """Small form-based application."""

    def __init__(
        self,
        host: str,
        cookie: str | None,
        fields: list[tuple[str, str, bool]],
        submit_label: str,
        submit_cb: cabc.Callable[..., cabc.Awaitable[str | None]],
    ) -> None:
        super().__init__()
        self.host = host
        self.cookie = cookie
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
            msg = await self.submit_cb(self.host, self.cookie, **data)
        except Exception as exc:  # noqa: BLE001
            status.update(f"{self.submit_label} failed: {exc}")
            return
        status.update(msg or f"{self.submit_label} succeeded")
        await self.action_quit()


class ChatApp(App):  # pyright: ignore[reportUntypedBaseClass, reportMissingTypeArgument]
    def __init__(self, host: str, cookie: str) -> None:
        super().__init__()
        self.host = host
        self.cookie = cookie
        self.history: list[dict[str, str]] = []

    def compose(self) -> ComposeResult:
        yield Log(id="log")
        yield Input(placeholder="Message", id="input")

    async def on_input_submitted(self, event: Input.Submitted) -> None:  # pyright: ignore[reportUnknownArgumentType]
        text = typing.cast("str", event.value)  # pyright: ignore[reportUnnecessaryCast]
        log = self.query_one("#log", Log)  # pyright: ignore[reportUnknownArgumentType]
        log.write(f"You: {text}")
        answer = await _chat_request(self.host, self.cookie, text, self.history)
        log.write(f"Assistant: {answer}")
        self.history.append({"role": "user", "content": text})
        self.history.append({"role": "assistant", "content": answer})
        self.query_one("#input", Input).value = ""


async def _login_form(
    host: str, _cookie: str | None, *, user: str, password: str
) -> str | None:
    await perform_login(host, user, password, COOKIE_PATH)
    return None


@app.command()  # pyright: ignore[reportUntypedFunctionDecorator]
def login(
    host: str = typer.Option(
        "http://localhost:8000", "--host", help="Chat server host URL"
    ),
) -> None:
    """Login to the chat server."""
    FormApp(
        host,
        None,
        fields=[("Username", "user", False), ("Password", "password", True)],
        submit_label="Login",
        submit_cb=_login_form,
    ).run()


async def _token_form(host: str, cookie: str | None, *, token: str) -> str | None:
    if cookie is None:
        raise RuntimeError("missing session cookie")
    ok = await _token_request(host, cookie, token)
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
    FormApp(
        host,
        cookie,
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
    ChatApp(host, cookie).run()


__all__ = [
    "_chat_request",
    "_token_request",
    "app",
    "perform_login",
]
