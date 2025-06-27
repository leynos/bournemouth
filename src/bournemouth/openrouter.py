# pyright: reportUnknownArgumentType=false, reportCallIssue=false, reportGeneralTypeIssues=false, reportUntypedBaseClass=false
"""Async OpenRouter client built on httpx and msgspec."""

from __future__ import annotations

import contextlib
import typing
from http import HTTPStatus

import httpx
import msgspec
from msgspec import json as msgspec_json

if typing.TYPE_CHECKING:  # pragma: no cover - imports for type checking
    import collections.abc as cabc

__all__ = [
    "CHAT_COMPLETIONS_PATH",
    "DEFAULT_BASE_URL",
    "ChatCompletionRequest",
    "ChatCompletionResponse",
    "ChatMessage",
    "OpenRouterAPIError",
    "OpenRouterAsyncClient",
    "OpenRouterAuthenticationError",
    "OpenRouterClientError",
    "OpenRouterDataValidationError",
    "OpenRouterInsufficientCreditsError",
    "OpenRouterInvalidRequestError",
    "OpenRouterNetworkError",
    "OpenRouterPermissionError",
    "OpenRouterRateLimitError",
    "OpenRouterRequestDataValidationError",
    "OpenRouterResponseDataValidationError",
    "OpenRouterServerError",
    "OpenRouterTimeoutError",
    "Role",
    "StreamChunk",
    "TextContentPart",
]


DEFAULT_BASE_URL = "https://openrouter.ai/api/v1/"
CHAT_COMPLETIONS_PATH = "/chat/completions"

# Reusable annotation for message roles used by OpenRouter
Role = typing.Literal["system", "user", "assistant", "tool"]


class InvalidToolMessageError(ValueError):
    """Raised when a tool message is missing required tool_call_id."""

    def __init__(self) -> None:
        super().__init__("tool messages must include tool_call_id")


class InvalidContentPartsError(ValueError):
    """Raised when non-user messages contain content parts."""

    def __init__(self) -> None:
        super().__init__("only user messages may contain content parts")


class ClientNotInitializedError(RuntimeError):
    """Raised when client operations are attempted before initialization."""

    def __init__(self) -> None:
        super().__init__("client not initialized; use async with")


class StreamChunkDecodeError(Exception):
    """Raised when stream chunk decoding fails."""

    def __init__(self, payload: str) -> None:
        super().__init__(f"failed to decode stream chunk: {payload}")


class ImageUrl(msgspec.Struct, array_like=True):
    """URL and resolution hint for an image content part."""

    url: str
    detail: typing.Literal["auto", "low", "high"] = "auto"


class ImageContentPart(msgspec.Struct, tag="image_url"):
    """Represents an image in a chat message."""

    image_url: ImageUrl


class TextContentPart(msgspec.Struct, tag="text"):
    """Represents plain text in a chat message."""

    text: str


ContentPart = TextContentPart | ImageContentPart


class ChatMessage(msgspec.Struct):
    """A single chat message sent to or returned from OpenRouter."""

    role: Role
    content: str | list[ContentPart]
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: typing.Any | None = None

    def __post_init__(self) -> None:  # pragma: no cover - executed by msgspec
        """Validate message content and metadata."""
        if self.role == "tool" and not self.tool_call_id:
            raise InvalidToolMessageError
        if self.role != "user" and isinstance(self.content, list):
            raise InvalidContentPartsError


class FunctionDescription(msgspec.Struct):
    """Description of a callable tool function."""

    name: str
    parameters: dict[str, typing.Any]
    description: str | None = None


class Tool(msgspec.Struct):
    """Tool definition that can be called by the model."""

    function: FunctionDescription
    type: typing.Literal["function"] = "function"


class ToolChoiceFunction(msgspec.Struct):
    """Specify a single function to call."""

    name: str


class ToolChoiceObject(msgspec.Struct):
    """Structured ``tool_choice`` parameter."""

    type: typing.Literal["function"]
    function: ToolChoiceFunction


ToolChoice = typing.Literal["none", "auto", "required"] | ToolChoiceObject


class ResponseFormat(msgspec.Struct):
    """Preferred format for the assistant's response."""

    type: typing.Literal["text", "json_object"]


class ProviderPreferences(msgspec.Struct, array_like=True, forbid_unknown_fields=False):
    """Placeholder for OpenRouter provider routing preferences."""

class ChatCompletionRequest(msgspec.Struct, forbid_unknown_fields=True):
    """Payload for ``/chat/completions`` requests."""

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


class FunctionCall(msgspec.Struct):
    """Function call returned by the assistant."""

    name: str
    arguments: str


class ToolCall(msgspec.Struct):
    """Invocation of a tool within a message."""

    id: str
    function: FunctionCall
    type: typing.Literal["function"] = "function"


class ResponseMessage(msgspec.Struct):
    """Full message object returned in non-streaming responses."""

    role: str
    content: str | None = None
    tool_calls: list[ToolCall] | None = None


class ResponseDelta(msgspec.Struct):
    """Partial message content used in streaming responses."""

    role: str | None = None
    content: str | None = None
    tool_calls: list[ToolCall] | None = None


class ChatCompletionChoice(msgspec.Struct):
    """Choice object from a non-streaming completion."""

    index: int
    message: ResponseMessage
    finish_reason: str | None = None
    native_finish_reason: str | None = None


class StreamChoice(msgspec.Struct):
    """Choice object from a streamed chunk."""

    index: int
    delta: ResponseDelta
    finish_reason: str | None = None
    native_finish_reason: str | None = None


class UsageStats(msgspec.Struct):
    """Token usage information returned by the API."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatCompletionResponse(msgspec.Struct, forbid_unknown_fields=False):
    """Response body for non-streaming chat completion requests."""

    id: str
    object: typing.Literal["chat.completion"]
    created: int
    model: str
    choices: list[ChatCompletionChoice]
    usage: UsageStats | None = None
    system_fingerprint: str | None = None


class StreamChunk(msgspec.Struct, forbid_unknown_fields=False):
    """A single chunk from a streaming completion."""

    id: str
    object: typing.Literal["chat.completion.chunk"]
    created: int
    model: str
    choices: list[StreamChoice]
    usage: UsageStats | None = None
    system_fingerprint: str | None = None


class OpenRouterAPIErrorDetails(msgspec.Struct, forbid_unknown_fields=False):
    """Details section in an error response."""

    message: str
    code: str | int | None = None
    param: str | None = None
    type: str | None = None
    metadata: dict[str, typing.Any] | None = None


class OpenRouterErrorResponse(msgspec.Struct, forbid_unknown_fields=False):
    """Wrapper for API error information."""

    error: OpenRouterAPIErrorDetails


class OpenRouterClientError(Exception):
    """Base exception for OpenRouter client errors."""


class OpenRouterNetworkError(OpenRouterClientError):
    """Raised when a network failure prevents contacting the API."""


class OpenRouterTimeoutError(OpenRouterNetworkError):
    """Raised when an HTTP request exceeds the timeout."""


class OpenRouterAPIError(OpenRouterClientError):
    """Base class for HTTP errors returned by OpenRouter."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        error_details: OpenRouterAPIErrorDetails | None = None,
    ) -> None:
        """Initialize the exception with error metadata.

        Parameters
        ----------
        message:
            Human-readable description of the error.
        status_code:
            HTTP status code returned by the API.
        error_details:
            Parsed ``error`` object from the response, if available.
        """
        super().__init__(message)
        self.status_code = status_code
        self.error_details = error_details

    @classmethod
    def from_status_code(
        cls,
        status_code: int,
        *,
        error_details: OpenRouterAPIErrorDetails | None = None,
    ) -> OpenRouterAPIError:
        """Create an exception instance with formatted message from status code."""
        return cls(
            f"API error {status_code}",
            status_code=status_code,
            error_details=error_details,
        )


class OpenRouterAuthenticationError(OpenRouterAPIError):
    """Raised when the API key is invalid or unauthorized."""


class OpenRouterGenericAPIError(OpenRouterAPIError):
    """Raised for generic API errors with status code."""

    def __init__(
        self,
        status_code: int,
        *,
        error_details: OpenRouterAPIErrorDetails | None = None,
    ) -> None:
        super().__init__(
            f"API error {status_code}",
            status_code=status_code,
            error_details=error_details,
        )


class OpenRouterRateLimitError(OpenRouterAPIError):
    """Raised when the client exceeds its rate limit."""


class OpenRouterInvalidRequestError(OpenRouterAPIError):
    """Raised when the request payload is malformed."""


class OpenRouterPermissionError(OpenRouterAPIError):
    """Raised when the API key lacks permission for the operation."""


class OpenRouterInsufficientCreditsError(OpenRouterAPIError):
    """Raised when the account has insufficient credits."""


class OpenRouterServerError(OpenRouterAPIError):
    """Raised when OpenRouter encounters an internal error."""


class OpenRouterDataValidationError(OpenRouterClientError):
    """Raised when request or response data fails validation."""


class OpenRouterRequestDataValidationError(OpenRouterDataValidationError):
    """Raised when encoding a request fails validation."""


class OpenRouterResponseDataValidationError(OpenRouterDataValidationError):
    """Raised when decoding a response fails validation."""


class OpenRouterStreamChunkDecodeError(OpenRouterResponseDataValidationError):
    """Raised when stream chunk decoding fails."""

    def __init__(self, payload: str) -> None:
        super().__init__(f"failed to decode stream chunk: {payload}")


_STATUS_MAP = {
    HTTPStatus.UNAUTHORIZED: OpenRouterAuthenticationError,
    HTTPStatus.PAYMENT_REQUIRED: OpenRouterInsufficientCreditsError,
    HTTPStatus.FORBIDDEN: OpenRouterPermissionError,
    HTTPStatus.TOO_MANY_REQUESTS: OpenRouterRateLimitError,
    HTTPStatus.BAD_REQUEST: OpenRouterInvalidRequestError,
}


def _map_status_to_error(status: int) -> type[OpenRouterAPIError]:
    """Map an HTTP status to a client error type.

    Parameters
    ----------
    status : int
        HTTP status code returned by the API.

    Returns
    -------
    type[OpenRouterAPIError]
        Exception class that best represents the status code.
    """
    try:
        status_enum = HTTPStatus(status)
    except ValueError:
        return OpenRouterAPIError

    if status_enum in _STATUS_MAP:
        return _STATUS_MAP[status_enum]
    if status_enum >= HTTPStatus.INTERNAL_SERVER_ERROR:
        return OpenRouterServerError
    return OpenRouterAPIError


class OpenRouterAsyncClient:
    """Asynchronous client for OpenRouter's completions API."""

    _ENCODER = msgspec_json.Encoder()
    _RESP_DECODER = msgspec_json.Decoder(ChatCompletionResponse)
    _STREAM_DECODER = msgspec_json.Decoder(StreamChunk)
    _ERR_DECODER = msgspec_json.Decoder(OpenRouterErrorResponse)

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str | None = None,
        timeout_config: httpx.Timeout | None = None,
        default_headers: dict[str, str] | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Create a new API client.

        Parameters
        ----------
        api_key:
            OpenRouter API key used for authentication.
        base_url:
            Base URL for the API. Defaults to ``DEFAULT_BASE_URL``.
        timeout_config:
            Optional ``httpx.Timeout`` settings.
        default_headers:
            Extra headers to include with every request.
        transport:
            Custom HTTP transport for testing.
        """
        self.api_key = api_key
        self.base_url = base_url or DEFAULT_BASE_URL
        self.timeout = timeout_config
        self._user_headers = default_headers or {}
        self._client: httpx.AsyncClient | None = None
        self._transport = transport

    async def __aenter__(self) -> typing.Self:
        """Open the underlying ``httpx`` client and return ``self``."""
        headers = {"Authorization": f"Bearer {self.api_key}"} | self._user_headers
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
            timeout=self.timeout,
            transport=self._transport,
        )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: typing.Any,
    ) -> None:
        """Close the underlying ``httpx`` client."""
        if not self._client:
            return
        await self._client.aclose()
        self._client = None

    async def _decode_error_details(
        self, data: bytes
    ) -> OpenRouterAPIErrorDetails | None:
        try:
            return self._ERR_DECODER.decode(data).error
        except msgspec.DecodeError:
            return None

    async def _raise_for_status(self, resp: httpx.Response) -> None:
        if resp.status_code < 400:
            return
        raw = await resp.aread()
        details = await self._decode_error_details(raw)
        exc_cls = _map_status_to_error(resp.status_code)
        if exc_cls == OpenRouterAPIError:
            # Use our custom exception for generic API errors
            raise OpenRouterGenericAPIError(
                resp.status_code,
                error_details=details,
            )
        # Use the specific exception class with class method
        raise exc_cls.from_status_code(
            resp.status_code,
            error_details=details,
        )

    async def _decode_response(self, resp: httpx.Response) -> ChatCompletionResponse:
        await self._raise_for_status(resp)
        data = await resp.aread()
        try:
            return self._RESP_DECODER.decode(data)
        except (msgspec.ValidationError, msgspec.DecodeError) as e:
            raise OpenRouterResponseDataValidationError(str(e)) from e

    async def _post(self, path: str, *, content: bytes) -> httpx.Response:
        if not self._client:
            raise ClientNotInitializedError
        try:
            return await self._client.post(path, content=content)
        except httpx.TimeoutException as e:
            raise OpenRouterTimeoutError(str(e)) from e
        except httpx.RequestError as e:
            raise OpenRouterNetworkError(str(e)) from e

    @contextlib.asynccontextmanager
    async def _stream_post(
        self, path: str, *, content: bytes
    ) -> cabc.AsyncIterator[httpx.Response]:
        if not self._client:
            raise ClientNotInitializedError
        try:
            async with self._client.stream("POST", path, content=content) as resp:
                yield resp
        except httpx.TimeoutException as e:
            raise OpenRouterTimeoutError(str(e)) from e
        except httpx.RequestError as e:
            raise OpenRouterNetworkError(str(e)) from e

    async def create_chat_completion(
        self, request: ChatCompletionRequest
    ) -> ChatCompletionResponse:
        """Send a completion request and return the parsed response.

        Parameters
        ----------
        request : ChatCompletionRequest
            Data structure describing the completion request.

        Returns
        -------
        ChatCompletionResponse
            Parsed response object.
        """
        if request.stream:
            data = msgspec.to_builtins(request)
            data["stream"] = False
            request = ChatCompletionRequest(**data)
        try:
            payload = self._ENCODER.encode(request)
        except (msgspec.ValidationError, msgspec.EncodeError) as e:
            raise OpenRouterRequestDataValidationError(str(e)) from e
        resp = await self._post(CHAT_COMPLETIONS_PATH, content=payload)
        return await self._decode_response(resp)

    async def stream_chat_completion(
        self, request: ChatCompletionRequest
    ) -> cabc.AsyncIterator[StreamChunk]:
        """Send a streaming request and yield chunks as they arrive.

        Parameters
        ----------
        request : ChatCompletionRequest
            Data structure describing the completion request.

        Yields
        ------
        StreamChunk
            Parsed stream chunks from OpenRouter.
        """
        if not request.stream:
            data = msgspec.to_builtins(request)
            data["stream"] = True
            request = ChatCompletionRequest(**data)
        try:
            payload = self._ENCODER.encode(request)
        except (msgspec.ValidationError, msgspec.EncodeError) as e:
            raise OpenRouterRequestDataValidationError(str(e)) from e
        async with self._stream_post(CHAT_COMPLETIONS_PATH, content=payload) as resp:
            await self._raise_for_status(resp)
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
                        raise OpenRouterStreamChunkDecodeError(payload_str) from e

            # end for
        # end async with
