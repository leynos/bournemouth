# Asynchronous OpenRouter Completions Client with msgspec and httpx

## 1. Introduction

This report outlines the design for a comprehensive, asynchronous Python client
tailored for the OpenRouter.ai Completions API. The primary objective is to
furnish developers with a robust, performant, and user-friendly library that
simplifies interaction with the diverse range of Large Language Models (LLMs)
accessible through OpenRouter. OpenRouter.ai offers a significant advantage by
providing a unified API endpoint and aggregated billing for numerous LLM
providers, alongside features like uptime pooling and usage analytics.1

The proposed client will leverage `httpx` for its efficient asynchronous HTTP
request capabilities and `msgspec` for high-performance data modeling,
validation, and serialization/deserialization. Key goals for this client include
ensuring robustness in the face of network issues and API errors, maximizing
performance through asynchronous operations and efficient data handling,
promoting ease of use via a clean API, and guaranteeing type safety through
rigorous data validation. This design will cover essential functionalities such
as making asynchronous API calls, handling streaming responses for real-time
interactions, implementing comprehensive error management, and ensuring data
integrity through `msgspec`-based validation.

## 2. Client Architecture and Initialization

The core of the library will be the `OpenRouterAsyncClient` class, serving as
the primary interface for all client operations.

### 2.1. `OpenRouterAsyncClient` Class Definition

The `OpenRouterAsyncClient` class will encapsulate all the logic for interacting
with the OpenRouter API. Its core attributes will include:

- `api_key`: The user's OpenRouter API key, essential for authentication.
- `base_url`: The base URL for the OpenRouter API, defaulting to
  `https://openrouter.ai/api/v1/`.
- `timeout_config`: An `httpx.Timeout` object to configure various timeout
  settings for requests.
- `default_headers`: A dictionary for any default HTTP headers the user wishes
  to apply to all requests.
- `_client`: An internal instance of `httpx.AsyncClient`, which will handle the
  actual HTTP communication. This instance will be managed by the
  `OpenRouterAsyncClient`.

### 2.2. Initialization (`__init__`)

The constructor for `OpenRouterAsyncClient` will accept the following
parameters:

- `api_key: str`: This is a mandatory parameter for authentication.
- `base_url: Optional[str]`: Defaults to `https://openrouter.ai/api/v1/`.1
  Allows users to override if necessary, for instance, for testing against a
  mock server or if OpenRouter changes its API prefix.
- `timeout_config: Optional`: An optional `httpx.Timeout` instance. If not
  provided, `httpx`'s default timeouts will apply (5 seconds for all operations
  3).
- `default_headers: Optional]`: Optional custom headers to be included with
  every request. These will be merged with standard headers like `Authorization`
  and `Content-Type`.

Upon initialization, these parameters will be stored as instance attributes. The
internal `httpx.AsyncClient` (`_client`) will be initialized to `None` at this
stage, as its instantiation is best handled within the asynchronous context
management.

### 2.3. Asynchronous Context Management (`__aenter__`, `__aexit__`)

To ensure proper management of network resources, particularly connection pools,
the `OpenRouterAsyncClient` will implement the asynchronous context manager
protocol.

- async def \__aenter_\_(self):

  This method will be called when entering an async with block. It will
  instantiate the internal self.\_client = httpx.AsyncClient(...), configuring
  it with the base_url, timeout_config, and any other relevant httpx-specific
  settings derived from the OpenRouterAsyncClient's configuration. Crucially, it
  will apply default headers, including the mandatory Authorization header
  derived from the api_key. This method will return self, allowing the client
  instance to be used within the async with block.

  ```python
  # Example snippet for __aenter__
  # async def __aenter__(self):
  #     self._client = httpx.AsyncClient(
  #         base_url=self.base_url,
  #         timeout=self.timeout_config,
  #         headers=self._prepare_default_headers() # Method to merge user defaults and auth
  #     )
  #     return self

  ```

- async def \__aexit_\_(self, exc_type, exc_val, exc_tb):

  This method will be called when exiting the async with block, regardless of
  whether an exception occurred. Its primary responsibility is to ensure that
  the internal httpx.AsyncClient is properly closed by calling await
  self.\_client.aclose(). This releases any acquired network resources, such as
  connections in the pool.

The decision to make `OpenRouterAsyncClient` an asynchronous context manager
itself is driven by the need for simplified usage and robust resource
management. `httpx.AsyncClient` is designed to be used as a context manager to
leverage its connection pooling and ensure that connections are properly cleaned
up.4 If users were required to manage both the `OpenRouterAsyncClient` and its
internal `httpx.AsyncClient` separately, it would introduce unnecessary
complexity. By encapsulating the `httpx.AsyncClient`'s lifecycle within the
`OpenRouterAsyncClient`, the end-developer interacts with a single, cohesive
client object (e.g., `async with OpenRouterAsyncClient(...) as or_client:`),
promoting cleaner and less error-prone code. This design transparently handles
the underlying HTTP transport layer's resource management.

### 2.4. Connection Pooling

Connection pooling is a critical feature for performance, especially when making
multiple requests to the same host. `httpx.AsyncClient` automatically handles
connection pooling when the client instance is reused for multiple requests.4 By
managing the `httpx.AsyncClient` instance within the `OpenRouterAsyncClient`'s
lifecycle (ideally through context management), these benefits are passed on to
the user of the `OpenRouterAsyncClient`.

## 3. Data Modeling with `msgspec`

The choice of `msgspec` for data modeling, validation, and
serialization/deserialization is predicated on its notable advantages in
performance and type safety.

### 3.1. Rationale for using `msgspec`

`msgspec` is a Python library designed for high-performance message processing.
Its `Struct` types are implemented in C, offering significantly faster creation,
comparison, encoding, and decoding compared to alternatives like standard
dataclasses, `attrs`, or Pydantic.5 This speed is crucial for an API client that
may handle large volumes of data or require low latency.

Furthermore, `msgspec.Struct` allows for the definition of clear and concise
data contracts through Python type annotations.5 This enables strict typing and
efficient validation of data before sending requests and after receiving
responses, helping to catch errors early in the development cycle or at
runtime.6 The validation ensures that the data exchanged with the OpenRouter API
conforms to the expected schemas.

### 3.2. Request `Struct`s

These `msgspec.Struct` classes will define the structure of request payloads
sent to the OpenRouter API. Their definitions are derived from the OpenRouter
API documentation, particularly the detailed TypeScript type definitions.8

- `ImageUrl(msgspec.Struct)`:
  - `url: str` (Represents a URL or a base64 encoded image string 8)
  - `detail: Optional[Literal["auto", "low", "high"]] = "auto"` 8
- `ImageContentPart(msgspec.Struct)`:
  - `type: Literal["image_url"] = "image_url"` 8
  - `image_url: ImageUrl`
- `TextContentPart(msgspec.Struct)`:
  - `type: Literal["text"] = "text"` 8
  - `text: str`
- `ContentPart = Union` 8
  - `msgspec` supports `Union` types, which will be used here to represent
    content that can be either text or an image.
- `ChatMessage(msgspec.Struct)`:
  - `role: Literal["system", "user", "assistant", "tool"]` 8
  - `content: Union[str, List[ContentPart]]` (String for most roles,
    `List[ContentPart]` for user role with multimodal input 8)
  - `name: Optional[str] = None` 8
  - `tool_call_id: Optional[str] = None` (Required if `role` is "tool" 8)
  - `tool_calls: Optional] = None` (Present if `role` is "assistant" and tool
    calls were made; `ToolCall` defined under Response Structs 8)
- `FunctionDescription(msgspec.Struct)`:
  - `name: str` 8
  - `description: Optional[str] = None` 8
  - `parameters: Dict[str, Any]` (A JSON Schema object defining the function's
    parameters 8)
- `Tool(msgspec.Struct)`:
  - `type: Literal["function"] = "function"` 8
  - `function: FunctionDescription`
- `ToolChoiceFunction(msgspec.Struct)`:
  - `name: str` 8
- `ToolChoiceObject(msgspec.Struct)`:
  - `type: Literal["function"]` 8
  - `function: ToolChoiceFunction`
- `ToolChoice = Union[Literal["none", "auto", "required"], ToolChoiceObject]`
  - The OpenRouter API specifies `tool_choice` can be a string literal or an
    object specifying a function.8 `msgspec` can model this `Union`.
- `ResponseFormat(msgspec.Struct)`:
  - `type: Literal["text", "json_object"]` 8
- `ProviderPreferences(msgspec.Struct, array_like=True, forbid_unknown_fields=False)`:
  - This is a placeholder for provider routing preferences.2 A more detailed
    structure can be defined if the API specifics for `provider` are complex.
    For now, `Dict[str, Any]` might be used directly in `ChatCompletionRequest`
    or a simple struct.
- `ChatCompletionRequest(msgspec.Struct, forbid_unknown_fields=True)`:
  - `model: str` 2
  - `messages: List[ChatMessage]` 2
  - `stream: bool = False` 2
  - `temperature: Optional[float] = None` (Range: 2) 2
  - `max_tokens: Optional[int] = None` (Range: \[1, context_length)) 2
  - `top_p: Optional[float] = None` (Range: (0, 1\]) 2
  - `top_k: Optional[int] = None` (Range: \[1, Infinity)) 2
  - `frequency_penalty: Optional[float] = None` (Range: [-2, 2]) 2
  - `presence_penalty: Optional[float] = None` (Range: [-2, 2]) 2
  - `repetition_penalty: Optional[float] = None` (Range: (0, 2\]) 8
  - `stop: Optional[Union[str, List[str]]] = None` 8
  - `seed: Optional[int] = None` 2
  - `tools: Optional] = None` 8
  - `tool_choice: Optional = None` 8
  - `response_format: Optional = None` 8
  - `user: Optional[str] = None` (Identifier for end-users to help detect abuse)
    2
  - OpenRouter-specific parameters:
    - `transforms: Optional[List[str]] = None` (List of prompt transforms) 2
    - `models: Optional[List[str]] = None` (Alternate list of models for routing
      overrides) 2
    - `route: Optional[Literal["fallback"]] = None` 8
    - `provider: Optional[ProviderPreferences] = None` (Provider routing
      preferences) 2
    - `usage: Optional] = None` (e.g., `{"include": True}` to include usage in
      response) 1

### 3.3. Response `Struct`s

These structs will model the data received from the OpenRouter API.

- `FunctionCall(msgspec.Struct)`: (Part of `ToolCall`)
  - `name: str` 8
  - `arguments: str` (A JSON string representing the arguments to the function
    8\)
- `ToolCall(msgspec.Struct)`: (Used in `ResponseMessage` and `ResponseDelta`)
  - `id: str` 8
  - `type: Literal["function"] = "function"` 8
  - `function: FunctionCall`
- `ResponseMessage(msgspec.Struct)`: (For the `message` field in non-streaming
  responses)
  - `role: str` (Typically "assistant" 8)
  - `content: Optional[str] = None` 8
  - `tool_calls: Optional] = None` 8
- `ResponseDelta(msgspec.Struct)`: (For the `delta` field in streaming response
  chunks)
  - `role: Optional[str] = None` 8
  - `content: Optional[str] = None` 8
  - `tool_calls: Optional] = None` (The structure of streamed tool calls needs
    careful handling as they might be delivered in chunks 8)
- `ChatCompletionChoice(msgspec.Struct)`: (For choices in non-streaming
  responses)
  - `index: int` (Typically 0, though the API schema indicates `choices` is an
    array 8)
  - `message: ResponseMessage` 8
  - `finish_reason: Optional[str] = None` (e.g., "stop", "length", "tool_calls",
    "content_filter", "error" 8)
  - `native_finish_reason: Optional[str] = None` (Raw finish reason from the
    provider 8)
- `StreamChoice(msgspec.Struct)`: (For choices in streaming response chunks)
  - `index: int`
  - `delta: ResponseDelta` 8
  - `finish_reason: Optional[str] = None` 8
  - `native_finish_reason: Optional[str] = None` 8
  - `logprobs: Optional[Any] = None` (Structure depends on whether logprobs are
    included in stream chunks; not detailed in provided snippets for streaming)
- `UsageStats(msgspec.Struct)`:
  - `prompt_tokens: int` 8
  - `completion_tokens: int` 8
  - `total_tokens: int` 8
- `ChatCompletionResponse(msgspec.Struct, forbid_unknown_fields=False)`: (For
  non-streaming responses)
  - `id: str` 8
  - `object: Literal["chat.completion"]` 8
  - `created: int` (Unix timestamp 8)
  - `model: str` 8
  - `choices: List[ChatCompletionChoice]` 8
  - `usage: Optional = None` 8
  - `system_fingerprint: Optional[str] = None` 8
- `StreamChunk(msgspec.Struct, forbid_unknown_fields=False)`: (Represents a
  single `data:` payload in a stream)
  - `id: str` 8
  - `object: Literal["chat.completion.chunk"]` 8
  - `created: int` 8
  - `model: str` 8
  - `choices: List` 8
  - `usage: Optional = None` 8
  - `system_fingerprint: Optional[str] = None` 8

A key consideration for `StreamChunk` is handling the final message containing
usage statistics. The OpenRouter API documentation states: "When streaming, you
will get one usage object at the end accompanied by an empty choices array".8
This implies that the `StreamChunk` struct must be designed to accommodate two
forms of data payloads: regular chunks containing `delta` updates within the
`choices` array, and a final chunk where `choices` is empty and `usage` is
populated. The `msgspec.Struct` definition with `choices: List` (which can be an
empty list) and `usage: Optional` naturally supports this. The client's stream
processing logic will then need to identify this final chunk, perhaps by
checking for the presence of `usage` data when `choices` is empty.

### 3.4. Error `Struct`s

These structs will model error responses from the OpenRouter API.

- `OpenRouterAPIErrorDetails(msgspec.Struct, forbid_unknown_fields=False)`:
  - `code: Optional[Union[str, int]] = None` (API-specific error code, which can
    be a string like "insufficient_funds" or a numeric HTTP status 8)
  - `message: str` 8
  - `param: Optional[str] = None`
  - `type: Optional[str] = None` (e.g., "invalid_request_error")
  - `metadata: Optional] = None` (For additional details like provider errors or
    moderation flags 8)
- `OpenRouterErrorResponse(msgspec.Struct, forbid_unknown_fields=False)`:
  - `error: OpenRouterAPIErrorDetails` 8

These structs will be used to parse the JSON body of HTTP error responses (e.g.,
4xx, 5xx status codes) returned by OpenRouter.8

### 3.5. Validation, Optional Fields, and Default Values

`msgspec.Struct` inherently supports these features:

- Type annotations provide automatic validation during decoding. 6
- `Optional` (or `Union`) is used for fields that may not always be present in
  the JSON payload. 5
- Default values for fields (e.g., `stream: bool = False` in
  `ChatCompletionRequest`) can be specified directly in the struct definition.5
- The `forbid_unknown_fields` parameter in `msgspec.Struct` controls behavior
  when extra fields are encountered during decoding.5 Setting
  `forbid_unknown_fields=True` on _request_ structs is generally advisable to
  catch typos or incorrect field names during development. For _response_
  structs, the decision is more nuanced. While `True` enforces strict adherence
  to the known schema and helps detect unexpected API changes, it can also make
  the client brittle if OpenRouter adds new, non-breaking informational fields.
  In a library intended for wider use, `forbid_unknown_fields=False` (the
  default) for response structs may offer greater resilience to minor API
  evolutions. This design will default to `False` for response structs to
  prioritize robustness but use `True` for request structs.

### Table 1: Key `msgspec` Data Models for OpenRouter API

| msgspec Struct Name     | Key Fields (with Python Type Hints)                                                                                                              | Corresponding OpenRouter API Object/Concept                               | Notes                                                                                                  |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| ChatMessage             | role: Literal["system", "user", "assistant", "tool"], content: Union\[str, List[ContentPart]\], name: Optional[str], tool_call_id: Optional[str] | Item in the messages array of a Chat Completion Request                   | content can be a list of ContentPart for user multimodal input. tool_call_id relevant for role="tool". |
| ChatCompletionRequest   | model: str, messages: List[ChatMessage], stream: bool = False, temperature: Optional[float], tools: Optional\]                                   | Main request body for /chat/completions                                   | model and messages are typically required. Many optional parameters for controlling generation.        |
| ChatCompletionResponse  | id: str, choices: List[ChatCompletionChoice], usage: Optional, model: str                                                                        | Response object for non-streaming chat completions                        | Contains the full response from the model.                                                             |
| StreamChunk             | id: str, choices: List, usage: Optional, model: str                                                                                              | Individual Server-Sent Event data: payload in a streaming chat completion | usage is typically only present in the final chunk with empty choices.                                 |
| OpenRouterErrorResponse | error: OpenRouterAPIErrorDetails                                                                                                                 | JSON body of an API error response (e.g., HTTP 4xx/5xx)                   | Used to parse structured error information from OpenRouter.                                            |
| UsageStats              | prompt_tokens: int, completion_tokens: int, total_tokens: int                                                                                    | Token usage information in responses                                      | Provided in non-streaming responses and the final chunk of streaming responses.                        |

This table serves as an essential reference, bridging the OpenRouter API's JSON
structures with the Python client's typed data models, thereby enhancing
developer understanding and reducing integration errors.

## 4. API Endpoint Interactions

The client will interact with specific OpenRouter API endpoints, primarily
focusing on chat completions.

### 4.1. Configuration

- **Base URL**: The client will use `https://openrouter.ai/api/v1/` as its
  default base URL for all API calls.1 This will be configurable during client
  initialization.
- **Authentication Header**: All requests to the API will automatically include
  the `Authorization: Bearer <YOUR_API_KEY>` header. The API key is provided
  during client initialization.1
- **Default Headers**: For POST requests sending JSON data, the
  `Content-Type: application/json` header is standard. `httpx` automatically
  sets this header when the `json=` parameter is used for the request body.11 If
  `content=` is used with pre-encoded JSON bytes, this header must be set
  explicitly. User-provided `default_headers` will be merged with these.

### 4.2. Internal `_request` Helper Method

To centralize common request logic, an internal asynchronous helper method,

```python
async def _request(
    self,
    method: str,
    endpoint: str,
    payload_struct: Optional = None,
    params: Optional = None,
    stream_response: bool = False,
)
```

may be implemented. This method would:

1. Take the HTTP method, endpoint path, an optional `msgspec.Struct` for the
   payload, optional query parameters, and a flag indicating if the response
   should be streamed.
2. If `payload_struct` is provided, serialize it to JSON bytes using
   `msgspec.json.Encoder().encode(payload_struct)`. 7
3. Construct the full URL using the client's `base_url` and the provided
   `endpoint`.
4. Make the HTTP request using the internal `self._client` (e.g.,
   `self._client.request(method, url, content=encoded_payload, params=params)`
   or `self._client.stream(...)`). 3
5. Perform initial response validation (e.g., checking status codes for non-2xx
   errors if not streaming, or immediately after stream context entry).
6. Handle `httpx` exceptions and potentially wrap them in custom client
   exceptions.

### 4.3. Chat Completions (`/chat/completions`) - Non-Streaming

This functionality allows for sending a chat request and receiving the entire
response at once.

- **Method Design**:
  `async def create_chat_completion(self, request: ChatCompletionRequest) -> ChatCompletionResponse:`
- **Request Payload Construction**: The input `request` parameter is an instance
  of the `ChatCompletionRequest` struct. The method should ensure its `stream`
  attribute is set to `False` (or explicitly override it to `False` if the
  `stream` field is mutable on the passed struct).
- `msgspec` **Serialization**: The `ChatCompletionRequest` struct will be
  serialized to a JSON byte string using
  `msgspec.json.Encoder().encode(request)`.7
- **Sending Request**: The request will be sent using
  `await self._client.post(endpoint_path, content=encoded_payload, headers=...)`.
  The `endpoint_path` will be `/chat/completions`. 4
- **Response Handling**:
  - The HTTP response status code will be checked. If it's not a 2xx success
    code, the error response body (if any) will be parsed using the
    `OpenRouterErrorResponse` struct, and a custom exception (e.g.,
    `OpenRouterAPIStatusError`, see Section 6) will be raised containing the
    details.8
  - If the status code indicates success (typically 200 OK), the JSON response
    body will be deserialized into a `ChatCompletionResponse` object using
    `msgspec.json.Decoder(type=ChatCompletionResponse).decode(response.content)`.7
  - The deserialized `ChatCompletionResponse` object is then returned.

### 4.4. Chat Completions (`/chat/completions`) - Streaming

This functionality allows for receiving the chat response as a stream of events
(chunks), enabling real-time display or processing of the generated text.

- **Method Design**:
  `async def stream_chat_completion(self, request: ChatCompletionRequest) -> AsyncIterator:`
  This method will be an asynchronous generator, yielding `StreamChunk` objects.

- **Enabling Streaming**: The input `ChatCompletionRequest` struct must have its
  `stream` attribute set to `True`.

- **Request Serialization**: Similar to the non-streaming version, the
  `ChatCompletionRequest` (with `stream=True`) is serialized to JSON using
  `msgspec.json.Encoder()`. 7

- **Sending Request**: The streaming request will be initiated using `httpx`'s
  streaming capabilities:

  ```python
  # endpoint_path will be "/chat/completions"
  # encoded_payload will be the msgspec-encoded ChatCompletionRequest
  # Assume necessary headers are prepared in a 'headers' dictionary

  try:
    async with self._client.stream(
        "POST",
        endpoint_path,
        content=encoded_payload,
        headers=headers,
    ) as response:  # [3, 4]
          # Immediately check for non-successful status codes after establishing the stream
          if response.status_code >= 400:
              error_body = await response.aread() # [4]
              await response.aclose() # Ensure the response is closed [4]
              try:
                  # Attempt to parse the error response using OpenRouterErrorResponse
                  error_data = msgspec.json.Decoder(type=OpenRouterErrorResponse).decode(error_body) # [7]
                  # Raise a specific custom exception, e.g., OpenRouterAPIStatusError
                  raise OpenRouterAPIStatusError( # Custom exception defined in section 6
                      message=f"API error {response.status_code} during stream initiation.",
                      status_code=response.status_code,
                      error_details=error_data.error
                  )
              except (msgspec.ValidationError, msgspec.DecodeError) as e: # [6, 7]
                  # If parsing fails, raise a more generic error with the raw body
                    raise OpenRouterAPIError(  # Custom exception defined in section 6
                        message=(
                            f"API error {response.status_code} during stream initiation. "
                            f"Failed to parse error response: {error_body.decode(errors='ignore')}"
                        ),
                        status_code=response.status_code,
                    )

          # Process Server-Sent Events (SSE)
          async for line in response.aiter_lines(): # [4]
              if not line:  # Skip empty lines
                  continue
              if line.startswith(':'):  # Skip comment lines [13]
                  continue
              if line.startswith('data: '):
                  json_payload_str = line[6:]  # Extract JSON payload
                  if json_payload_str == '':  # End of stream signal [13]
                      break
                  try:
                      # Decode the JSON payload into a StreamChunk object
                      chunk = msgspec.json.Decoder(type=StreamChunk).decode(json_payload_str) # [7]
                      yield chunk
                  except (msgspec.ValidationError, msgspec.DecodeError) as e: # [6, 7]
                      # Handle or log malformed JSON chunks, potentially raise a custom error
                      # For example:
                        # raise OpenRouterResponseDataValidationError(
                        #     f"Failed to decode stream chunk: {json_payload_str}. Error: {e}"
                        # )
                      # Depending on desired robustness, you might log and continue, or raise.
                      # For this design, we'll assume logging and continuing for partial errors,
                      # but a production client might offer configurable behavior.
                        # print(
                        #     f"Warning: Failed to decode stream chunk: {json_payload_str}. Error: {e}"
                        # )  # Placeholder for logging
                      # For a library, raising an error might be more appropriate:
                        raise OpenRouterResponseDataValidationError(
                            f"Failed to decode stream chunk: {json_payload_str}. "
                            f"Original error: {e}"
                        ) from e
          # Ensure the response is closed if the loop finishes normally or breaks
          await response.aclose() # [4]
  except httpx.HTTPStatusError as e: # Should be caught by the status check above, but as a fallback
      error_content = e.response.content
      try:
          error_data = msgspec.json.Decoder(type=OpenRouterErrorResponse).decode(error_content) # [7]
          raise OpenRouterAPIStatusError( # Custom exception defined in section 6
              message=str(e),
              status_code=e.response.status_code,
              error_details=error_data.error,
              response=e.response
          ) from e
      except (msgspec.ValidationError, msgspec.DecodeError): # [6, 7]
          raise OpenRouterAPIError( # Custom exception defined in section 6
              message=f"HTTP Status Error {e.response.status_code} during stream: {error_content.decode(errors='ignore')}",
              status_code=e.response.status_code,
              response=e.response
          ) from e
  except httpx.RequestError as e: # Catches network errors, timeouts etc. [4]
      raise OpenRouterNetworkError(f"Network error during streaming request: {e}") from e # Custom exception


  ```

It is crucial to check `response.status_code` immediately after the `async with`
block is entered. If the status indicates an error (e.g., 401, 402), the error
response body should be read (e.g., `await response.aread()`), parsed using
`OpenRouterErrorResponse`, an appropriate custom exception raised, and then
`await response.aclose()` called to ensure resources are freed. `httpx.stream`
does not automatically raise for bad statuses upon entering the context.

- **Processing Server-Sent Events (SSE)**: The OpenRouter API uses Server-Sent
  Events for streaming.8 The client will process these events by iterating over
  the response lines:
  - Use `async for line in response.aiter_lines():` to read the stream line by
    line.4
  - **Line Processing Logic** (adapted from Python examples for SSE 13):
    1. Skip empty lines.
    2. Ignore comment lines, which start with a colon (`:`) (e.g.,
       `: OPENROUTER PROCESSING` 13).
    3. If a line starts with `data:`:
       - Extract the JSON payload string (the part of the line after `data:`).
       - If this payload string is \`\`, it signifies the end of the stream.13
         The loop should be broken, or the generator should stop yielding.
       - Otherwise, the JSON payload string is decoded into a `StreamChunk`
         object using
         `msgspec.json.Decoder(type=StreamChunk).decode(json_payload_str)`.7
       - The deserialized `StreamChunk` object is then `yield`ed by the
         generator.
  - Potential `msgspec.ValidationError` or `msgspec.DecodeError` during the
    decoding of a chunk should be caught and wrapped in a custom client
    exception (e.g., `OpenRouterResponseDataValidationError`).6

The use of `response.aiter_lines()` is particularly well-suited for SSE, as SSE
is a line-delimited protocol. The core of robust SSE handling lies in
meticulously parsing each line according to the SSE format rules: identifying
data-bearing lines, correctly extracting the JSON payload, recognizing and
acting upon the \`\` termination signal, and safely ignoring comment lines. This
structured approach ensures the accurate transformation of the raw SSE stream
from the API into a validated, type-safe asynchronous iterator of `StreamChunk`
objects for the client user.

Regarding stream cancellation, OpenRouter documentation indicates that for
supported providers, aborting the connection can stop model processing and
billing.13 When using `httpx` with `asyncio`, if the `asyncio` task consuming
the stream is cancelled, `httpx` typically aborts the underlying network
connection. This implies that the client, when used within standard `asyncio`
applications, should support stream cancellation implicitly through `asyncio`'s
task cancellation mechanisms, without requiring explicit cancellation methods in
the client library itself.

### Table 2: OpenRouter API Endpoint Summary for Client Methods

| Client Method / Endpoint Path                         | HTTP Method                                           | Key msgspec Request Struct                            | Key msgspec Response Struct / AsyncIterator Type      | Purpose                                               |
| ----------------------------------------------------- | ----------------------------------------------------- | ----------------------------------------------------- | ----------------------------------------------------- | ----------------------------------------------------- |
| create_chat_completion (/chat/completions)            | POST                                                  | ChatCompletionRequest (with stream=False)             | ChatCompletionResponse                                | Standard, non-streaming LLM chat completion.          |
| stream_chat_completion (/chat/completions)            | POST                                                  | ChatCompletionRequest (with stream=True)              | AsyncIterator                                         | Streaming LLM chat completion via Server-Sent Events. |

This table provides a concise overview of the primary client methods, their
corresponding API endpoints, and the data structures involved, facilitating
easier understanding for developers using the client.

## 5. Authentication

Secure and straightforward authentication is paramount for an API client.

### 5.1. API Key Handling

The `OpenRouterAsyncClient` will require an OpenRouter API key for
authentication.

- The API key will be provided as a string during the client's initialization
  (`api_key: str`).

- This key will be used to construct the `Authorization` header for every API
  request, formatted as `Authorization: Bearer <YOUR_API_KEY>`.1

- This header can be set as a default header on the internal `httpx.AsyncClient`
  instance when it's created (e.g., in `__aenter__` or by passing it to
  `httpx.AsyncClient(headers=...)`). For example:

  ```python
  # Part of client initialization or __aenter__
  # merged_default_headers = {**self.user_default_headers}
  # merged_default_headers["Authorization"] = f"Bearer {self.api_key}"
  # self._client = httpx.AsyncClient(..., headers=merged_default_headers)

  ```

### 5.2. Securely Managing and Providing the API Key

The report will strongly advise users to manage their OpenRouter API keys
securely. Best practices include:

- Using environment variables to store the API key.
- Employing secrets management tools (e.g., HashiCorp Vault, AWS Secrets
  Manager).
- Storing keys in secure configuration files that are not checked into version
  control. It is critical that API keys are **not** hardcoded directly into
  source code. The client library itself will not be responsible for storing or
  persisting the API key; it will only use the key provided to it at runtime for
  constructing authentication headers.

### 5.3. Mention of Other Authentication Methods (Out of Scope for Core Design)

OpenRouter supports additional authentication methods beyond simple API keys,
such as OAuth 2.0 PKCE (Proof Key for Code Exchange) for user-delegated access
14, and Provisioning API Keys for programmatic management of API keys.1 While
the initial design of this client focuses on the common direct API key
authentication suitable for backend applications, these other methods are noted
as relevant for more advanced scenarios. For instance, an application could use
the PKCE flow to obtain a user-controlled API key, which could then be used with
this client. The client's core request logic, which relies on a bearer token,
remains compatible even if the token is obtained through such alternative
mechanisms, highlighting a degree of inherent flexibility in its applicability.

## 6. Error Handling and Resilience

A robust client must gracefully handle various types of errors, from network
issues to API-specific rejections.

### 6.1. `httpx` Exceptions

The client will catch and handle common exceptions raised by the `httpx`
library:

- `httpx.HTTPStatusError`: This exception is raised by
  `response.raise_for_status()` if the HTTP status code is 4xx or 5xx.3 The
  client will catch this, attempt to parse the OpenRouter JSON error response
  body (if available, using `OpenRouterErrorResponse` struct), and then raise a
  more specific custom client exception that includes these details.
- `httpx.TimeoutException` (and its subclasses like `httpx.ConnectTimeout`,
  `httpx.ReadTimeout`): These indicate that a request timed out at various
  stages.11 They will be caught and re-raised as a custom client timeout
  exception (e.g., `OpenRouterTimeoutError`).
- `httpx.RequestError` (and its subclasses like `httpx.ConnectError`,
  `httpx.NetworkError`): These represent general network issues or problems
  during request sending.4 They will be re-raised as a custom client network
  exception (e.g., `OpenRouterNetworkError`).

### 6.2. OpenRouter API Specific Errors

OpenRouter uses standard HTTP status codes to indicate various error conditions
8:

- `400 Bad Request`: Invalid parameters or request structure. 8
- `401 Unauthorized`: Invalid or missing API key, or expired OAuth session. 8
- `402 Payment Required`: Insufficient credits. 8
- `403 Forbidden`: Input flagged by moderation, or other permission issues. 8
- `408 Request Timeout`: Server-side timeout. 8
- `429 Too Many Requests`: Rate limit exceeded. 8
- `500 Internal Server Error`: Generic error on OpenRouter's side. 8
- `502 Bad Gateway`: Issue with an upstream model provider. 8
- `503 Service Unavailable`: No suitable model provider available. 8

When these errors occur, OpenRouter typically returns a JSON response body
detailing the error. The client will attempt to parse this JSON using the
`OpenRouterErrorResponse` and `OpenRouterAPIErrorDetails` msgspec Structs. Based
on the status code and parsed error details, specific custom exceptions will be
raised:

- `OpenRouterAuthenticationError(OpenRouterAPIError)` for 401.
- `OpenRouterInsufficientCreditsError(OpenRouterAPIError)` for 402.
- `OpenRouterPermissionError(OpenRouterAPIError)` for 403.
- `OpenRouterRateLimitError(OpenRouterAPIError)` for 429.
- `OpenRouterInvalidRequestError(OpenRouterAPIError)` for 400.
- `OpenRouterServerError(OpenRouterAPIError)` for 5xx errors.

### 6.3. `msgspec` Validation Errors

`msgspec` will raise a `msgspec.ValidationError` if:

- Data provided by the user for a request payload fails validation against the
  corresponding request `Struct` before the request is sent.
- Response data received from the API fails validation against the corresponding
  response `Struct` (e.g., `ChatCompletionResponse`, `StreamChunk`) during
  deserialization.6 These validation errors will be caught by the client and
  re-raised as custom exceptions, such as `OpenRouterClientDataValidationError`
  (for request data issues) or `OpenRouterResponseDataValidationError` (for
  response data issues), to provide clearer context to the user.

### 6.4. Defining Custom Client Exceptions

A hierarchy of custom exceptions will be defined to provide a structured way for
users to catch and handle errors originating from the client or the API:

- Base Exception: `OpenRouterClientError(Exception)`
- Network-related: `OpenRouterNetworkError(OpenRouterClientError)`
  - Timeout-specific: `OpenRouterTimeoutError(OpenRouterNetworkError)`
- API-related: `OpenRouterAPIError(OpenRouterClientError)`
  - This will store attributes like `status_code` and the parsed `error_details`
    (an `OpenRouterAPIErrorDetails` instance).
  - Specific API errors like `OpenRouterAuthenticationError`,
    `OpenRouterRateLimitError`, etc., will inherit from `OpenRouterAPIError`.
- Data Validation: `OpenRouterDataValidationError(OpenRouterClientError)`
  - Subclasses: `OpenRouterRequestDataValidationError` and
    `OpenRouterResponseDataValidationError`.

This hierarchy allows users to catch errors at different levels of granularity.

### 6.5. Retry Mechanisms

While the initial design may not include complex built-in retry logic to
maintain simplicity, this is a critical area for future enhancement. If
implemented, retries should be configurable and applied selectively:

- **Retryable Errors**: Typically, transient errors such as
  `429 Too Many Requests` (respecting any `Retry-After` header provided by the
  API), 5xx server errors, and network timeouts (`OpenRouterTimeoutError`,
  `OpenRouterNetworkError`).
- **Non-Retryable Errors**: Errors like `400 Bad Request`, `401 Unauthorized`,
  `402 Payment Required`, or `msgspec.ValidationError` should generally not be
  retried as they indicate fundamental issues with the request or account status
  that a retry is unlikely to resolve.

The selection of which errors are retryable is fundamental to creating a
resilient client. For example, a 429 error often suggests a temporary overload
or quota exhaustion and is a good candidate for a delayed retry, especially if a
`Retry-After` directive is provided. Conversely, a 400 error indicates an issue
with the request itself, and retrying the same malformed request will not yield
a different outcome. 5xx errors often point to transient problems on the server
side, making them suitable for retries with an appropriate backoff strategy
(e.g., exponential backoff with jitter). Libraries like `tenacity` or `httpx`'s
own transport-level retry capabilities (`httpx.AsyncHTTPTransport(retries=...)`
3\) can be leveraged for implementing such strategies.

### Table 3: Client Exception Hierarchy and Error Handling

| Source             | Condition    | Exception               | Notes               |
| ------------------ | ------------ | ----------------------- | ------------------- |
| httpx.HTTPStatus   | 401          | AuthError               | Verify key          |
| httpx.HTTPStatus   | 402          | CreditsError            | Add credits         |
| httpx.HTTPStatus   | 403          | PermissionError         | Check input         |
| httpx.HTTPStatus   | 429          | RateLimitError          | Wait and retry      |
| httpx.HTTPStatus   | 400          | InvalidRequest          | Review request      |
| httpx.HTTPStatus   | 5xx          | ServerError             | Retry later         |
| httpx.Timeout      | timeout      | TimeoutError            | Increase timeout    |
| httpx.NetworkError | network      | NetworkError            | Check connection    |
| ValidationError    | bad request  | RequestValidationError  | Fix payload         |
| ValidationError    | bad response | ResponseValidationError | Possible change     |

## 7. Client Configuration and Customization

The client should offer flexibility through various configuration options.

- **Configurable Timeouts**: As mentioned in Section 2.2, the client will accept
  an `httpx.Timeout` object during initialization. This object allows
  fine-grained control over different timeout phases: `connect`, `read`,
  `write`, and `pool` timeouts.3 Users should be guided to set appropriate
  values, especially longer `read` timeouts, as LLM responses can take time to
  generate.
- **Setting Custom Headers**:
  - Users can provide `default_headers` during client instantiation. These
    headers will be merged with the standard `Authorization` and `Content-Type`
    headers.
  - For per-request customization, client methods (like
    `create_chat_completion`) can accept an optional `headers: Optional] = None`
    parameter. These headers would be merged with (and potentially override)
    client-level default headers for that specific request. `httpx.Client`
    methods support this pattern.3
  - The documentation should mention OpenRouter-recognized optional headers like
    `HTTP-Referer` (to identify the application on openrouter.ai) and `X-Title`
    (to set/modify the application's title for discovery).8
- **Proxy Configuration**: `httpx.AsyncClient` supports proxy configuration
  through the `proxies` parameter in its constructor or via standard environment
  variables (`HTTP_PROXY`, `HTTPS_PROXY`).3 The `OpenRouterAsyncClient` will
  accept an optional `proxies` argument (a string URL or a dictionary mapping
  schemes to proxy URLs) and pass it directly to the internal
  `httpx.AsyncClient`.
- **SSL Verification**: `httpx.AsyncClient` allows control over SSL certificate
  verification via the `verify` parameter (boolean or path to CA bundle).3 The
  `OpenRouterAsyncClient` will accept a `verify` argument (defaulting to `True`)
  and pass it to the internal `httpx.AsyncClient`.

Exposing these underlying `httpx` configurations provides necessary flexibility.
While common options like `api_key` and `timeout_config` can be direct
parameters of `OpenRouterAsyncClient`, a more general approach for less common
`httpx` settings could be an optional `httpx_client_options: Optional]`
parameter. This dictionary would be unpacked and passed to the
`httpx.AsyncClient` constructor, allowing advanced users to fine-tune aspects
like HTTP/2 settings, connection limits, or event hooks without cluttering the
`OpenRouterAsyncClient`'s primary API.

## 8. Illustrative Usage Examples

Clear examples are essential for demonstrating the client's functionality and
ease of use.

- **Prerequisites**:

  ```bash
  # pip install openrouter-async-client msgspec httpx

  ```

  (Assuming `openrouter-async-client` is the package name).

- **Initializing the client**:

  ```python
  import asyncio
  from openrouter_client import (
      OpenRouterAsyncClient,
      ChatCompletionRequest,
      ChatMessage, # Assuming ChatMessage is exposed for direct use
      # Potentially other request/response structs if users build requests manually
      OpenRouterAPIError, # Base API error
      OpenRouterClientError, # Base client error
      OpenRouterAPIStatusError, # More specific error for HTTP status issues
      # Potentially OpenRouterResponseDataValidationError for stream chunk errors
  )

  # It's highly recommended to use environment variables for API keys
  # import os
  # api_key = os.getenv("OPENROUTER_API_KEY")
  api_key = "YOUR_OPENROUTER_API_KEY" # Replace with your actual key or load from env

  async def main():
      # Example: Configure a longer read timeout (e.g., 30 seconds)
      # import httpx
      # timeout_config = httpx.Timeout(5.0, read=30.0) # 5s connect, 30s read
      # async with OpenRouterAsyncClient(api_key=api_key, timeout_config=timeout_config) as client:
      async with OpenRouterAsyncClient(api_key=api_key) as client:
          # Use the client for API calls
          await run_non_streaming_example(client)
          await run_streaming_example(client)

  # Placeholder for actual method calls
  async def run_non_streaming_example(client: OpenRouterAsyncClient): pass
  async def run_streaming_example(client: OpenRouterAsyncClient): pass

  if __name__ == "__main__":
      asyncio.run(main())

  ```

- **Making a standard (non-streaming) chat completion request**:

  ```python
  async def run_non_streaming_example(client: OpenRouterAsyncClient):
      print("\n--- Non-Streaming Example ---")
      request_payload = ChatCompletionRequest(
          model="openai/gpt-3.5-turbo", # Or any other model like "mistralai/mistral-7b-instruct"
          messages=[
              ChatMessage(role="user", content="Hello, what is the capital of France?")
          ]
      )
      try:
          response = await client.create_chat_completion(request_payload)
          if response.choices and response.choices.message:
              print("Assistant:", response.choices.message.content)
          if response.usage:
            print(
                f"Tokens used: Prompt={response.usage.prompt_tokens}, "
                f"Completion={response.usage.completion_tokens}, "
                f"Total={response.usage.total_tokens}"
            )
      except OpenRouterAPIStatusError as e: # Catching a more specific error
          print(f"API Status Error ({e.status_code}): {e.error_details.message if e.error_details else 'No details provided'}")
          if e.error_details and e.error_details.code:
               print(f"  Error Code: {e.error_details.code}")
          # Example: Handle insufficient credits specifically
          if e.status_code == 402:
              print("  Action: Please check your OpenRouter account balance.")
      except OpenRouterClientError as e: # Catch-all for other client-side issues
          print(f"Client Error: {e}")

  ```

- **Iterating over a streaming chat completion response**:

  ```python
  async def run_streaming_example(client: OpenRouterAsyncClient):
      print("\n--- Streaming Example ---")
      stream_request_payload = ChatCompletionRequest(
          model="openai/gpt-4o-mini", # Example model [18]
          messages=,
          stream=True,
          max_tokens=150
      )
      full_response_content =
      try:
          print("Assistant (streaming): ", end="", flush=True)
          final_usage_stats = None
          async for chunk in client.stream_chat_completion(stream_request_payload):
              if chunk.choices and chunk.choices.delta and chunk.choices.delta.content:
                  content_piece = chunk.choices.delta.content
                  print(content_piece, end="", flush=True)
                  full_response_content.append(content_piece)

              # The final chunk in a stream might contain usage statistics [8]
              if chunk.usage:
                  final_usage_stats = chunk.usage

          print("\n--- End of Stream ---")
          # assembled_response = "".join(full_response_content)
          # print(f"Assembled full response: {assembled_response}") # Optional: print full assembled response

            if final_usage_stats:
                print("\n--- Stream Usage ---")
                print(
                    f"Tokens used: Prompt={final_usage_stats.prompt_tokens}, "
                    f"Completion={final_usage_stats.completion_tokens}, "
                    f"Total={final_usage_stats.total_tokens}"
                )

      except OpenRouterAPIStatusError as e:
        print(
            f"\nAPI Status Error during stream ({e.status_code}): "
            f"{e.error_details.message if e.error_details else 'No details'}"
        )
      except OpenRouterResponseDataValidationError as e: # Specific error for bad stream chunks
          print(f"\nError decoding stream data: {e}")
      except OpenRouterClientError as e: # General client error
          print(f"\nClient Error during stream: {e}")

  ```

  This example demonstrates printing content as it arrives and handling the
  final usage statistics chunk.

- **Basic error handling patterns**: The examples above show catching
  `OpenRouterAPIStatusError` and the general `OpenRouterClientError`. More
  specific exceptions like `OpenRouterAuthenticationError` or
  `OpenRouterRateLimitError` can be caught for tailored handling.

## 9. Advanced Features and Future Considerations

While the core design focuses on the chat completions endpoint, several advanced
features and potential future enhancements could further improve the client.

- **Support for other OpenRouter endpoints**:
  - `/completions` (Legacy non-chat endpoint 19): Support for this would require
    distinct `msgspec` request/response models tailored to its schema.
  - `/api/v1/models` (GET request to list available models 1): Implementing a
    method to fetch and parse the list of available models (with their
    properties like pricing, context length) would be highly beneficial for
    dynamic model selection. This would necessitate `msgspec` models for the
    model list response structure.
  - `/api/v1/auth/key` (GET request to check API key details, including rate
    limits and remaining credits 21): A utility method to retrieve this
    information could help applications manage their usage proactively.
- **Explicit Rate Limit Awareness and Handling**: Beyond reacting to 429 errors,
  the client could potentially parse rate limit information from response
  headers (if provided by OpenRouter beyond the `/auth/key` endpoint) to
  implement client-side rate limiting or more intelligent retry delays.
- **More Sophisticated Retry Strategies with Backoff**: As discussed in Section
  6.5, implementing configurable retry strategies with exponential backoff and
  jitter, particularly for 429 and 5xx errors, and explicit handling of
  `Retry-After` headers, would significantly enhance resilience.
- **Integration with Logging Frameworks**: Allowing users to inject a standard
  Python `logging.Logger` instance would enable the client to emit logs about
  its internal operations (e.g., requests sent, responses received, errors
  encountered). Configurable log levels for different event types would offer
  fine-grained control over verbosity.
- **Tool Use / Function Calling**: The `msgspec` models (`Tool`, `ToolCall`,
  `FunctionDescription`, `FunctionCall` within `ChatCompletionRequest` and
  response objects) are designed to support OpenRouter's tool-calling
  capabilities.8 The client's serialization and deserialization logic must
  correctly handle these structures.
- **Image/Multimodal Inputs**: The `ContentPart`, `ImageContentPart`, and
  `TextContentPart` structs within `ChatMessage.content` are designed to
  facilitate multimodal inputs, particularly images.8 The client must ensure
  these are correctly formatted in requests according to OpenRouter's
  specifications (e.g., image URLs or base64 encoded data).
- **Synchronous Wrapper**: While the primary design is asynchronous, a
  synchronous wrapper around the `OpenRouterAsyncClient` could be provided as a
  utility for developers working in synchronous codebases. This wrapper would
  internally use `asyncio.run()` to execute the async methods, offering a
  blocking API. This mirrors `httpx`'s own provision of both `Client` and
  `AsyncClient`. 4

The OpenRouter API platform is rich and continually evolving, offering access to
a wide array of models and features.1 Acknowledging these advanced features and
potential future enhancements provides a clear roadmap for the client's
development, manages expectations regarding the scope of an initial version, and
demonstrates a comprehensive understanding of the broader OpenRouter ecosystem.

## 10. Conclusion

The proposed design outlines an asynchronous Python client for the OpenRouter.ai
Completions API that prioritizes robustness, performance, type safety, and ease
of use. By leveraging `httpx` for efficient, non-blocking HTTP operations and
`msgspec` for high-speed data validation and serialization, the client aims to
provide a superior developer experience.

Key benefits of this design include:

- **Asynchronous Efficiency**: Native `async/await` support through
  `httpx.AsyncClient` allows for high-concurrency applications without the
  overhead of traditional threading. 4
- **Data Integrity and Performance**: `msgspec.Struct` ensures that data
  exchanged with the API is correctly formatted and validated, while its C-based
  implementation offers significant speed advantages for serialization and
  deserialization. 5
- **Comprehensive API Coverage**: Focus on the crucial `/chat/completions`
  endpoint, including robust support for Server-Sent Events (SSE) for streaming
  responses. 8
- **Structured Error Handling**: A clear hierarchy of custom exceptions
  simplifies error management for client users.
- **Configurability**: Options for timeouts, custom headers, and proxy settings
  provide necessary flexibility. 3

This client is designed to address common challenges in API interaction, such as
managing asynchronous communication, handling real-time data streams, and
gracefully recovering from errors. Its adoption should significantly simplify
the integration of OpenRouter's diverse LLM offerings into Python applications,
empowering developers to build more sophisticated and responsive AI-powered
services. The outlined future considerations also pave the way for continued
evolution, potentially expanding support to other OpenRouter API features and
further enhancing client resilience and utility.
