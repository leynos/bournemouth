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
    OpenRouterInvalidRequestError,
    OpenRouterNetworkError,
    OpenRouterRateLimitError,
    OpenRouterTimeoutError,
)


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
