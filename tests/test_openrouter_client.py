from __future__ import annotations

import typing
from http import HTTPStatus

import httpx
import msgspec
import pytest

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
from bournemouth.openrouter import TextContentPart


class MockTransport(httpx.AsyncBaseTransport):
    def __init__(
        self,
        handler: typing.Callable[[httpx.Request], typing.Awaitable[httpx.Response]],
    ):
        self._handler = handler

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        return await self._handler(request)


@pytest.mark.asyncio
async def test_create_chat_completion_success() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.headers["Authorization"] == "Bearer k"
        data = await request.aread()
        body = msgspec.json.decode(data)
        assert body["model"] == "openai/gpt-3.5-turbo"
        content = {
            "id": "1",
            "object": "chat.completion",
            "created": 1,
            "model": "openai/gpt-3.5-turbo",
            "choices": [
                {"index": 0, "message": {"role": "assistant", "content": "hi"}}
            ],
        }
        return httpx.Response(200, json=content)

    transport = MockTransport(handler)
    async with OpenRouterAsyncClient(
        api_key="k",
        default_headers={},
        timeout_config=None,
        transport=transport,
    ) as client:
        req = ChatCompletionRequest(
            model="openai/gpt-3.5-turbo",
            messages=[ChatMessage(role="user", content="hi")],
        )
        resp = await client.create_chat_completion(req)
        assert resp.choices[0].message.content == "hi"


@pytest.mark.asyncio
async def test_non_success_status_raises() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            HTTPStatus.UNAUTHORIZED,
            json={"error": {"message": "bad", "code": "invalid_key"}},
        )

    transport = MockTransport(handler)
    async with OpenRouterAsyncClient(api_key="k", transport=transport) as client:
        req = ChatCompletionRequest(
            model="openai/gpt-3.5-turbo",
            messages=[ChatMessage(role="user", content="hi")],
        )
        with pytest.raises(OpenRouterAuthenticationError):
            await client.create_chat_completion(req)


@pytest.mark.asyncio
async def test_invalid_request_status_raises() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            HTTPStatus.BAD_REQUEST,
            json={"error": {"message": "nope"}},
        )

    transport = MockTransport(handler)
    async with OpenRouterAsyncClient(api_key="k", transport=transport) as client:
        req = ChatCompletionRequest(
            model="openai/gpt-3.5-turbo",
            messages=[ChatMessage(role="user", content="hi")],
        )
        with pytest.raises(OpenRouterInvalidRequestError):
            await client.create_chat_completion(req)


@pytest.mark.asyncio
async def test_streaming_yields_chunks() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        content = (
            b'data: {"id": "1", "object": "chat.completion.chunk", "created": 1,'
            b' "model": "m", "choices": [{"index": 0, "delta": {"content": "hi"}}]}\n'
            b"data: \n"
        )
        return httpx.Response(
            200, content=content, headers={"Content-Type": "text/event-stream"}
        )

    transport = MockTransport(handler)
    async with OpenRouterAsyncClient(api_key="k", transport=transport) as client:
        req = ChatCompletionRequest(
            model="m",
            messages=[ChatMessage(role="user", content="hi")],
            stream=True,
        )
        chunks = [c async for c in client.stream_chat_completion(req)]
        assert chunks[0].choices[0].delta.content == "hi"


@pytest.mark.asyncio
async def test_streaming_error_status() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            HTTPStatus.TOO_MANY_REQUESTS,
            json={"error": {"message": "slow down"}},
        )

    transport = MockTransport(handler)
    async with OpenRouterAsyncClient(api_key="k", transport=transport) as client:
        req = ChatCompletionRequest(
            model="m",
            messages=[ChatMessage(role="user", content="hi")],
            stream=True,
        )
        with pytest.raises(OpenRouterRateLimitError):
            async for _ in client.stream_chat_completion(req):
                pass


@pytest.mark.asyncio
async def test_client_closes_on_exit() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        content = {
            "id": "1",
            "object": "chat.completion",
            "created": 1,
            "model": "m",
            "choices": [
                {"index": 0, "message": {"role": "assistant", "content": "hi"}}
            ],
        }
        return httpx.Response(200, json=content)

    transport = MockTransport(handler)
    client = OpenRouterAsyncClient(api_key="k", transport=transport)
    async with client as c:
        req = ChatCompletionRequest(
            model="m",
            messages=[ChatMessage(role="user", content="hi")],
        )
        await c.create_chat_completion(req)
    with pytest.raises(RuntimeError):
        await client.create_chat_completion(req)


@pytest.mark.asyncio
async def test_network_error_maps_to_client_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    transport = MockTransport(handler)
    async with OpenRouterAsyncClient(api_key="k", transport=transport) as client:
        req = ChatCompletionRequest(
            model="m",
            messages=[ChatMessage(role="user", content="hi")],
        )
        with pytest.raises(OpenRouterNetworkError):
            await client.create_chat_completion(req)


@pytest.mark.asyncio
async def test_timeout_error_maps_to_timeout_exception() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("slow", request=request)

    transport = MockTransport(handler)
    async with OpenRouterAsyncClient(api_key="k", transport=transport) as client:
        req = ChatCompletionRequest(
            model="m",
            messages=[ChatMessage(role="user", content="hi")],
        )
        with pytest.raises(OpenRouterTimeoutError):
            await client.create_chat_completion(req)


@pytest.mark.asyncio
async def test_create_chat_completion_ignores_stream_true() -> None:
    content = {
        "id": "1",
        "object": "chat.completion",
        "created": 1,
        "model": "m",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}}],
    }

    async def handler(request: httpx.Request) -> httpx.Response:
        data = await request.aread()
        body = msgspec.json.decode(data)
        assert body["stream"] is False
        return httpx.Response(200, json=content)

    transport = MockTransport(handler)
    async with OpenRouterAsyncClient(api_key="k", transport=transport) as client:
        req = ChatCompletionRequest(
            model="m",
            messages=[ChatMessage(role="user", content="hi")],
            stream=True,
        )
        resp = await client.create_chat_completion(req)
        assert resp.choices[0].message.content == "ok"


@pytest.mark.asyncio
async def test_stream_chat_completion_sets_stream_true() -> None:
    content = (
        b'data: {"id": "1", "object": "chat.completion.chunk", "created": 1, '
        b'"model": "m", "choices": [{"index": 0, "delta": {"content": "hi"}}]}\n'
        b"data: \n"
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        data = await request.aread()
        body = msgspec.json.decode(data)
        assert body["stream"] is True
        return httpx.Response(
            200,
            content=content,
            headers={"Content-Type": "text/event-stream"},
        )

    transport = MockTransport(handler)
    async with OpenRouterAsyncClient(api_key="k", transport=transport) as client:
        req = ChatCompletionRequest(
            model="m",
            messages=[ChatMessage(role="user", content="hi")],
            stream=False,
        )
        chunks = [c async for c in client.stream_chat_completion(req)]
        assert chunks[0].choices[0].delta.content == "hi"


@pytest.mark.asyncio
async def test_insufficient_credits_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            HTTPStatus.PAYMENT_REQUIRED,
            json={"error": {"message": "pay up"}},
        )

    transport = MockTransport(handler)
    async with OpenRouterAsyncClient(api_key="k", transport=transport) as client:
        req = ChatCompletionRequest(
            model="m",
            messages=[ChatMessage(role="user", content="hi")],
        )
        with pytest.raises(OpenRouterInsufficientCreditsError):
            await client.create_chat_completion(req)


@pytest.mark.asyncio
async def test_permission_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            HTTPStatus.FORBIDDEN,
            json={"error": {"message": "no"}},
        )

    transport = MockTransport(handler)
    async with OpenRouterAsyncClient(api_key="k", transport=transport) as client:
        req = ChatCompletionRequest(
            model="m",
            messages=[ChatMessage(role="user", content="hi")],
        )
        with pytest.raises(OpenRouterPermissionError):
            await client.create_chat_completion(req)


@pytest.mark.asyncio
async def test_server_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            HTTPStatus.INTERNAL_SERVER_ERROR,
            json={"error": {"message": "boom"}},
        )

    transport = MockTransport(handler)
    async with OpenRouterAsyncClient(api_key="k", transport=transport) as client:
        req = ChatCompletionRequest(
            model="m",
            messages=[ChatMessage(role="user", content="hi")],
        )
        with pytest.raises(OpenRouterServerError):
            await client.create_chat_completion(req)


@pytest.mark.asyncio
async def test_invalid_json_raises_validation_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"{bad json}")

    transport = MockTransport(handler)
    async with OpenRouterAsyncClient(api_key="k", transport=transport) as client:
        req = ChatCompletionRequest(
            model="m",
            messages=[ChatMessage(role="user", content="hi")],
        )
        with pytest.raises(OpenRouterResponseDataValidationError):
            await client.create_chat_completion(req)


@pytest.mark.asyncio
async def test_stream_invalid_chunk_raises_validation_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        content = b"data: {bad json}\n"
        return httpx.Response(
            200,
            content=content,
            headers={"Content-Type": "text/event-stream"},
        )

    transport = MockTransport(handler)
    async with OpenRouterAsyncClient(api_key="k", transport=transport) as client:
        req = ChatCompletionRequest(
            model="m",
            messages=[ChatMessage(role="user", content="hi")],
            stream=True,
        )
        with pytest.raises(OpenRouterResponseDataValidationError):
            async for _ in client.stream_chat_completion(req):
                pass


def test_chat_message_validation_errors() -> None:
    with pytest.raises(ValueError):
        ChatMessage(role="tool", content="x")
    with pytest.raises(ValueError):
        ChatMessage(role="assistant", content=[TextContentPart(text="hi")])
