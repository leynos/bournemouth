"""Tests for the OpenRouter client implementation."""
from __future__ import annotations

import typing
from http import HTTPStatus

import httpx
import pytest
from msgspec import json as msgspec_json

if typing.TYPE_CHECKING:  # pragma: no cover - fixtures only
    import collections.abc as cabc

    from pytest_httpx import HTTPXMock

from bournemouth import (
    ChatCompletionRequest,
    ChatMessage,
    OpenRouterAsyncClient,
    OpenRouterAuthenticationError,
    OpenRouterInsufficientCreditsError,
    OpenRouterInvalidRequestError,
    OpenRouterNetworkError,
    OpenRouterPermissionError,
    OpenRouterRateLimitError,
    OpenRouterResponseDataValidationError,
    OpenRouterServerError,
    OpenRouterTimeoutError,
)
from bournemouth.openrouter import (
    CHAT_COMPLETIONS_PATH,
    DEFAULT_BASE_URL,
    InvalidContentPartsError,
    InvalidToolMessageError,
    TextContentPart,
)

pytest_plugins = ["pytest_httpx"]

CHAT_COMPLETIONS_URL = f"{DEFAULT_BASE_URL.rstrip('/')}{CHAT_COMPLETIONS_PATH}"


@pytest.fixture
def add_chat_response(httpx_mock: HTTPXMock) -> cabc.Callable[..., None]:
    """Return a helper to add a canned chat response."""
    def _add_response(**kwargs: typing.Any) -> None:  # noqa: ANN401
        httpx_mock.add_response(method="POST", url=CHAT_COMPLETIONS_URL, **kwargs)

    return _add_response


@pytest.fixture
def add_chat_callback(httpx_mock: HTTPXMock) -> cabc.Callable[..., None]:
    """Return a helper to register a callback for chat requests."""
    def _add_callback(
        handler: cabc.Callable[[httpx.Request], httpx.Response], **kwargs: typing.Any  # noqa: ANN401
    ) -> None:
        httpx_mock.add_callback(
            handler, method="POST", url=CHAT_COMPLETIONS_URL, **kwargs
        )

    return _add_callback


@pytest.mark.asyncio
async def test_create_chat_completion_success(
    httpx_mock: HTTPXMock, add_chat_callback: cabc.Callable[..., None]
) -> None:
    """Successful requests should return parsed completion data."""
    content = {
        "id": "1",
        "object": "chat.completion",
        "created": 1,
        "model": "openai/gpt-3.5-turbo",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": "hi"}}],
    }

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.headers["Authorization"] == "Bearer k"
        body = msgspec_json.decode(await request.aread())
        assert body["model"] == "openai/gpt-3.5-turbo"
        return httpx.Response(200, json=content)

    add_chat_callback(handler)

    async with OpenRouterAsyncClient(
        api_key="k",
        default_headers={},
        timeout_config=None,
    ) as client:
        req = ChatCompletionRequest(
            model="openai/gpt-3.5-turbo",
            messages=[ChatMessage(role="user", content="hi")],
        )
        resp = await client.create_chat_completion(req)
        assert resp.choices[0].message.content == "hi"


@pytest.mark.asyncio
async def test_non_success_status_raises(
    httpx_mock: HTTPXMock, add_chat_response: cabc.Callable[..., None]
) -> None:
    """HTTP errors from the API map to custom exceptions."""
    add_chat_response(
        status_code=HTTPStatus.UNAUTHORIZED,
        json={"error": {"message": "bad", "code": "invalid_key"}},
    )

    async with OpenRouterAsyncClient(api_key="k") as client:
        req = ChatCompletionRequest(
            model="openai/gpt-3.5-turbo",
            messages=[ChatMessage(role="user", content="hi")],
        )
        with pytest.raises(OpenRouterAuthenticationError):
            await client.create_chat_completion(req)


@pytest.mark.asyncio
async def test_invalid_request_status_raises(
    httpx_mock: HTTPXMock, add_chat_response: cabc.Callable[..., None]
) -> None:
    """Invalid request errors raise ``OpenRouterInvalidRequestError``."""
    add_chat_response(
        status_code=HTTPStatus.BAD_REQUEST,
        json={"error": {"message": "nope"}},
    )

    async with OpenRouterAsyncClient(api_key="k") as client:
        req = ChatCompletionRequest(
            model="openai/gpt-3.5-turbo",
            messages=[ChatMessage(role="user", content="hi")],
        )
        with pytest.raises(OpenRouterInvalidRequestError):
            await client.create_chat_completion(req)


@pytest.mark.asyncio
async def test_streaming_yields_chunks(
    httpx_mock: HTTPXMock, add_chat_response: cabc.Callable[..., None]
) -> None:
    """Streaming responses should yield parsed chunks."""
    content = (
        b'data: {"id": "1", "object": "chat.completion.chunk", "created": 1,'
        b' "model": "m", "choices": [{"index": 0, "delta": {"content": "hi"}}]}\n'
        b"data: \n"
    )

    add_chat_response(
        headers={"Content-Type": "text/event-stream"},
        content=content,
    )

    async with OpenRouterAsyncClient(api_key="k") as client:
        req = ChatCompletionRequest(
            model="m",
            messages=[ChatMessage(role="user", content="hi")],
            stream=True,
        )
        chunks = [c async for c in client.stream_chat_completion(req)]
        assert chunks[0].choices[0].delta.content == "hi"


@pytest.mark.asyncio
async def test_streaming_error_status(
    httpx_mock: HTTPXMock, add_chat_response: cabc.Callable[..., None]
) -> None:
    """Streaming with an error status raises ``OpenRouterRateLimitError``."""
    add_chat_response(
        status_code=HTTPStatus.TOO_MANY_REQUESTS,
        json={"error": {"message": "slow down"}},
    )

    async with OpenRouterAsyncClient(api_key="k") as client:
        req = ChatCompletionRequest(
            model="m",
            messages=[ChatMessage(role="user", content="hi")],
            stream=True,
        )
        with pytest.raises(OpenRouterRateLimitError):
            async for _ in client.stream_chat_completion(req):
                pass


@pytest.mark.asyncio
async def test_client_closes_on_exit(
    httpx_mock: HTTPXMock, add_chat_response: cabc.Callable[..., None]
) -> None:
    """Client sessions should close and reject new requests."""
    add_chat_response(
        json={
            "id": "1",
            "object": "chat.completion",
            "created": 1,
            "model": "m",
            "choices": [
                {"index": 0, "message": {"role": "assistant", "content": "hi"}}
            ],
        },
    )

    client = OpenRouterAsyncClient(api_key="k")
    async with client as c:
        req = ChatCompletionRequest(
            model="m",
            messages=[ChatMessage(role="user", content="hi")],
        )
        await c.create_chat_completion(req)
    with pytest.raises(RuntimeError):
        await client.create_chat_completion(req)


@pytest.mark.asyncio
async def test_network_error_maps_to_client_error(httpx_mock: HTTPXMock) -> None:
    """Network errors raise ``OpenRouterNetworkError``."""
    httpx_mock.add_exception(
        method="POST",
        url=CHAT_COMPLETIONS_URL,
        exception=httpx.ConnectError(
            "boom", request=httpx.Request("POST", "https://openrouter.ai")
        ),
    )

    async with OpenRouterAsyncClient(api_key="k") as client:
        req = ChatCompletionRequest(
            model="m",
            messages=[ChatMessage(role="user", content="hi")],
        )
        with pytest.raises(OpenRouterNetworkError):
            await client.create_chat_completion(req)


@pytest.mark.asyncio
async def test_timeout_error_maps_to_timeout_exception(httpx_mock: HTTPXMock) -> None:
    """Timeout errors raise ``OpenRouterTimeoutError``."""
    httpx_mock.add_exception(
        method="POST",
        url=CHAT_COMPLETIONS_URL,
        exception=httpx.TimeoutException(
            "slow", request=httpx.Request("POST", "https://openrouter.ai")
        ),
    )

    async with OpenRouterAsyncClient(api_key="k") as client:
        req = ChatCompletionRequest(
            model="m",
            messages=[ChatMessage(role="user", content="hi")],
        )
        with pytest.raises(OpenRouterTimeoutError):
            await client.create_chat_completion(req)


@pytest.mark.asyncio
async def test_create_chat_completion_ignores_stream_true(
    httpx_mock: HTTPXMock, add_chat_callback: cabc.Callable[..., None]
) -> None:
    """Non-stream requests should override ``stream`` in payload."""
    content = {
        "id": "1",
        "object": "chat.completion",
        "created": 1,
        "model": "m",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}}],
    }

    async def handler(request: httpx.Request) -> httpx.Response:
        body = msgspec_json.decode(await request.aread())
        assert body["stream"] is False
        return httpx.Response(200, json=content)

    add_chat_callback(handler)

    async with OpenRouterAsyncClient(api_key="k") as client:
        req = ChatCompletionRequest(
            model="m",
            messages=[ChatMessage(role="user", content="hi")],
            stream=True,
        )
        resp = await client.create_chat_completion(req)
        assert resp.choices[0].message.content == "ok"


@pytest.mark.asyncio
async def test_stream_chat_completion_sets_stream_true(
    httpx_mock: HTTPXMock, add_chat_callback: cabc.Callable[..., None]
) -> None:
    """Streaming API requests should send ``stream=True``."""
    content = (
        b'data: {"id": "1", "object": "chat.completion.chunk", "created": 1, '
        b'"model": "m", "choices": [{"index": 0, "delta": {"content": "hi"}}]}\n'
        b"data: \n"
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        body = msgspec_json.decode(await request.aread())
        assert body["stream"] is True
        return httpx.Response(
            200,
            content=content,
            headers={"Content-Type": "text/event-stream"},
        )

    add_chat_callback(handler)

    async with OpenRouterAsyncClient(api_key="k") as client:
        req = ChatCompletionRequest(
            model="m",
            messages=[ChatMessage(role="user", content="hi")],
            stream=False,
        )
        chunks = [c async for c in client.stream_chat_completion(req)]
        assert chunks[0].choices[0].delta.content == "hi"


@pytest.mark.asyncio
async def test_insufficient_credits_error(
    httpx_mock: HTTPXMock, add_chat_response: cabc.Callable[..., None]
) -> None:
    """Payment required responses raise ``OpenRouterInsufficientCreditsError``."""
    add_chat_response(
        status_code=HTTPStatus.PAYMENT_REQUIRED,
        json={"error": {"message": "pay up"}},
    )

    async with OpenRouterAsyncClient(api_key="k") as client:
        req = ChatCompletionRequest(
            model="m",
            messages=[ChatMessage(role="user", content="hi")],
        )
        with pytest.raises(OpenRouterInsufficientCreditsError):
            await client.create_chat_completion(req)


@pytest.mark.asyncio
async def test_permission_error(
    httpx_mock: HTTPXMock, add_chat_response: cabc.Callable[..., None]
) -> None:
    """Forbidden responses raise ``OpenRouterPermissionError``."""
    add_chat_response(
        status_code=HTTPStatus.FORBIDDEN,
        json={"error": {"message": "no"}},
    )

    async with OpenRouterAsyncClient(api_key="k") as client:
        req = ChatCompletionRequest(
            model="m",
            messages=[ChatMessage(role="user", content="hi")],
        )
        with pytest.raises(OpenRouterPermissionError):
            await client.create_chat_completion(req)


@pytest.mark.asyncio
async def test_server_error(
    httpx_mock: HTTPXMock, add_chat_response: cabc.Callable[..., None]
) -> None:
    """Server errors raise ``OpenRouterServerError``."""
    add_chat_response(
        status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        json={"error": {"message": "boom"}},
    )

    async with OpenRouterAsyncClient(api_key="k") as client:
        req = ChatCompletionRequest(
            model="m",
            messages=[ChatMessage(role="user", content="hi")],
        )
        with pytest.raises(OpenRouterServerError):
            await client.create_chat_completion(req)


@pytest.mark.asyncio
async def test_invalid_json_raises_validation_error(
    httpx_mock: HTTPXMock, add_chat_response: cabc.Callable[..., None]
) -> None:
    """Invalid JSON responses raise validation errors."""
    add_chat_response(content=b"{bad json}")

    async with OpenRouterAsyncClient(api_key="k") as client:
        req = ChatCompletionRequest(
            model="m",
            messages=[ChatMessage(role="user", content="hi")],
        )
        with pytest.raises(OpenRouterResponseDataValidationError):
            await client.create_chat_completion(req)


@pytest.mark.asyncio
async def test_stream_invalid_chunk_raises_validation_error(
    httpx_mock: HTTPXMock, add_chat_response: cabc.Callable[..., None]
) -> None:
    """Invalid streamed chunks raise validation errors."""
    content = b"data: {bad json}\n"

    add_chat_response(
        headers={"Content-Type": "text/event-stream"},
        content=content,
    )

    async with OpenRouterAsyncClient(api_key="k") as client:
        req = ChatCompletionRequest(
            model="m",
            messages=[ChatMessage(role="user", content="hi")],
            stream=True,
        )
        with pytest.raises(OpenRouterResponseDataValidationError):
            async for _ in client.stream_chat_completion(req):
                pass


def test_chat_message_validation_errors() -> None:
    """ChatMessage should validate role and content types."""
    with pytest.raises(InvalidToolMessageError):
        ChatMessage(role="tool", content="x")
    with pytest.raises(InvalidContentPartsError):
        ChatMessage(role="assistant", content=[TextContentPart(text="hi")])
