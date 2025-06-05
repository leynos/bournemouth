# pyright: reportUnknownArgumentType=false, reportCallIssue=false, reportGeneralTypeIssues=false, reportUntypedBaseClass=false

"""Async OpenRouter client built on httpx and msgspec."""

from __future__ import annotations

import typing

if typing.TYPE_CHECKING:  # pragma: no cover - imports for type checking
    import collections.abc as cabc
    import types

import httpx
import msgspec

__all__ = [
    "ChatCompletionRequest",
    "ChatCompletionResponse",
    "ChatMessage",
    "OpenRouterAPIError",
    "OpenRouterAsyncClient",
    "OpenRouterAuthenticationError",
    "OpenRouterClientError",
    "OpenRouterInvalidRequestError",
    "OpenRouterNetworkError",
    "OpenRouterRateLimitError",
    "OpenRouterTimeoutError",
    "StreamChunk",
]


class ImageUrl(msgspec.Struct, array_like=True):
    url: str
    detail: typing.Literal["auto", "low", "high"] = "auto"


class ImageContentPart(msgspec.Struct):
    image_url: ImageUrl
    type: typing.Literal["image_url"] = "image_url"


class TextContentPart(msgspec.Struct):
    text: str
    type: typing.Literal["text"] = "text"


ContentPart = TextContentPart | ImageContentPart


class ChatMessage(msgspec.Struct):
    role: typing.Literal["system", "user", "assistant", "tool"]
    content: str | list[ContentPart]
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: typing.Any | None = None

    def __post_init__(self) -> None:  # pragma: no cover - executed by msgspec
        if self.role == "tool" and not self.tool_call_id:
            raise ValueError("tool messages must include tool_call_id")
        if self.role != "user" and isinstance(self.content, list):
            raise ValueError("only user messages may contain content parts")


class FunctionDescription(msgspec.Struct):
    name: str
    parameters: dict[str, typing.Any]
    description: str | None = None


class Tool(msgspec.Struct):
    function: FunctionDescription
    type: typing.Literal["function"] = "function"


class ToolChoiceFunction(msgspec.Struct):
    name: str


class ToolChoiceObject(msgspec.Struct):
    type: typing.Literal["function"]
    function: ToolChoiceFunction


ToolChoice = typing.Literal["none", "auto", "required"] | ToolChoiceObject


class ResponseFormat(msgspec.Struct):
    type: typing.Literal["text", "json_object"]


class ProviderPreferences(msgspec.Struct, array_like=True, forbid_unknown_fields=False):
    # Placeholder for provider routing fields
    pass


class ChatCompletionRequest(msgspec.Struct, forbid_unknown_fields=True):
    model: str
    messages: list[ChatMessage]
    stream: bool = False
    temperature: float | None = None
    max_tokens: int | None = None
    top_p: float | None = None
    top_k: int | None = None
    frequency_penalty: float | None = None
    presence_penalty: float | None = None
    repetition_penalty: float | None = None
    stop: str | list[str] | None = None
    seed: int | None = None
    tools: list[Tool] | None = None
    tool_choice: ToolChoice | None = None
    response_format: ResponseFormat | None = None
    user: str | None = None
    transforms: list[str] | None = None
    models: list[str] | None = None
    route: typing.Literal["fallback"] | None = None
    provider: ProviderPreferences | None = None
    usage: dict[str, typing.Any] | None = None


class FunctionCall(msgspec.Struct):
    name: str
    arguments: str


class ToolCall(msgspec.Struct):
    id: str
    function: FunctionCall
    type: typing.Literal["function"] = "function"


class ResponseMessage(msgspec.Struct):
    role: str
    content: str | None = None
    tool_calls: list[ToolCall] | None = None


class ResponseDelta(msgspec.Struct):
    role: str | None = None
    content: str | None = None
    tool_calls: list[ToolCall] | None = None


class ChatCompletionChoice(msgspec.Struct):
    index: int
    message: ResponseMessage
    finish_reason: str | None = None
    native_finish_reason: str | None = None


class StreamChoice(msgspec.Struct):
    index: int
    delta: ResponseDelta
    finish_reason: str | None = None
    native_finish_reason: str | None = None
    logprobs: typing.Any | None = None


class UsageStats(msgspec.Struct):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatCompletionResponse(msgspec.Struct, forbid_unknown_fields=False):
    id: str
    object: typing.Literal["chat.completion"]
    created: int
    model: str
    choices: list[ChatCompletionChoice]
    usage: UsageStats | None = None
    system_fingerprint: str | None = None


class StreamChunk(msgspec.Struct, forbid_unknown_fields=False):
    id: str
    object: typing.Literal["chat.completion.chunk"]
    created: int
    model: str
    choices: list[StreamChoice]
    usage: UsageStats | None = None
    system_fingerprint: str | None = None


class OpenRouterAPIErrorDetails(msgspec.Struct, forbid_unknown_fields=False):
    message: str
    code: str | int | None = None
    param: str | None = None
    type: str | None = None
    metadata: dict[str, typing.Any] | None = None


class OpenRouterErrorResponse(msgspec.Struct, forbid_unknown_fields=False):
    error: OpenRouterAPIErrorDetails


# Exception hierarchy
class OpenRouterClientError(Exception):
    pass


class OpenRouterNetworkError(OpenRouterClientError):
    pass


class OpenRouterTimeoutError(OpenRouterNetworkError):
    pass


class OpenRouterAPIError(OpenRouterClientError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        error_details: OpenRouterAPIErrorDetails | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_details = error_details


class OpenRouterAuthenticationError(OpenRouterAPIError):
    pass


class OpenRouterRateLimitError(OpenRouterAPIError):
    pass


class OpenRouterInvalidRequestError(OpenRouterAPIError):
    pass


def _map_status_to_error(status: int) -> type[OpenRouterAPIError]:
    if status == 401:
        return OpenRouterAuthenticationError
    if status == 429:
        return OpenRouterRateLimitError
    if status == 400:
        return OpenRouterInvalidRequestError
    return OpenRouterAPIError


class OpenRouterAsyncClient:
    """Asynchronous client for OpenRouter's completions API."""

    _ENCODER = msgspec.json.Encoder()
    _RESP_DECODER = msgspec.json.Decoder(ChatCompletionResponse)
    _STREAM_DECODER = msgspec.json.Decoder(StreamChunk)
    _ERR_DECODER = msgspec.json.Decoder(OpenRouterErrorResponse)

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str | None = None,
        timeout_config: httpx.Timeout | None = None,
        default_headers: dict[str, str] | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url or "https://openrouter.ai/api/v1/"
        self.timeout = timeout_config
        self._user_headers = default_headers or {}
        self._client: httpx.AsyncClient | None = None
        self._transport = transport

    async def __aenter__(self) -> OpenRouterAsyncClient:
        """Initialize the underlying ``httpx`` client."""

        headers = {"Authorization": f"Bearer {self.api_key}"}
        """Close the ``httpx`` client and reset internal state."""

            self._client = None
    async def _decode_error(
        self, resp: httpx.Response
    ) -> OpenRouterAPIErrorDetails | None:
        """Return parsed error details if the body is decodable."""

        try:
            return self._ERR_DECODER.decode(await resp.aread()).error
        except msgspec.DecodeError:
            return None

    async def _raise_for_status(self, resp: httpx.Response) -> None:
        """Raise an API error if the response status indicates failure."""

        if resp.status_code < 400:
            return
        details = await self._decode_error(resp)
        exc_cls = _map_status_to_error(resp.status_code)
        raise exc_cls(
            f"API error {resp.status_code}",
            status_code=resp.status_code,
            error_details=details,
        )

    async def _decode_response(self, resp: httpx.Response) -> ChatCompletionResponse:
        """Return the deserialized response body."""

        data = await resp.aread()
        return self._RESP_DECODER.decode(data)

        """Validate ``resp`` and return the decoded body."""

        await self._raise_for_status(resp)
        return await self._decode_response(resp)
        """Send a non-streaming completion request."""
        """Yield ``StreamChunk`` objects for a streaming request."""
                err = None
            exc_cls = _map_status_to_error(resp.status_code)
            raise exc_cls(
                f"API error {resp.status_code}",
                status_code=resp.status_code,
                error_details=err,
            )
        return self._RESP_DECODER.decode(await resp.aread())

    async def create_chat_completion(
        self, request: ChatCompletionRequest
    ) -> ChatCompletionResponse:
        if request.stream:
            raise ValueError("stream flag must be False for create_chat_completion")
        if not self._client:
            raise RuntimeError("client not initialized; use async with")
        payload = self._ENCODER.encode(request)
        try:
            resp = await self._client.post("/chat/completions", content=payload)
        except httpx.TimeoutException as e:
            raise OpenRouterTimeoutError(str(e)) from e
        except httpx.RequestError as e:
            raise OpenRouterNetworkError(str(e)) from e
        return await self._handle_response(resp)

    async def stream_chat_completion(
        self, request: ChatCompletionRequest
    ) -> cabc.AsyncIterator[StreamChunk]:
        if not request.stream:
            raise ValueError("stream flag must be True for stream_chat_completion")
        if not self._client:
            raise RuntimeError("client not initialized; use async with")
        payload = self._ENCODER.encode(request)
        try:
            async with self._client.stream(
                "POST", "/chat/completions", content=payload
            ) as resp:
                if resp.status_code >= 400:
                    data = await resp.aread()
                    try:
                        err = self._ERR_DECODER.decode(data).error
                    except msgspec.DecodeError:
                        err = None
                    exc_cls = _map_status_to_error(resp.status_code)
                    raise exc_cls(
                        f"API error {resp.status_code}",
                        status_code=resp.status_code,
                        error_details=err,
                    )
                async for line in resp.aiter_lines():
                    if not line or line.startswith(":"):
                        continue
                    if line.startswith("data: "):
                        payload_str = line[6:]
                        if payload_str == "":
                            break
                        try:
                            yield self._STREAM_DECODER.decode(payload_str)
                        except msgspec.DecodeError as e:
                            raise OpenRouterAPIError(
                                f"failed to decode stream chunk: {payload_str}"
                            ) from e
        except httpx.TimeoutException as e:
            raise OpenRouterTimeoutError(str(e)) from e
        except httpx.RequestError as e:
            raise OpenRouterNetworkError(str(e)) from e
