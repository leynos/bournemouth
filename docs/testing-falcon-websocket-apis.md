# A Comprehensive Guide to Testing Falcon-based WebSocket APIs with `pytest-asyncio`

## 1. Introduction to WebSocket Testing in Falcon

WebSockets provide a persistent, bidirectional communication channel between a
client and a server, crucial for real-time applications such as chat systems,
live data feeds, and online gaming.1 The Falcon framework, known for its
minimalist design and high performance, supports WebSocket implementations for
its ASGI (Asynchronous Server Gateway Interface) applications.3 Testing these
asynchronous, stateful connections requires specialized tools and techniques to
ensure reliability and correctness.

This guide provides a comprehensive approach to testing WebSocket APIs built
with Falcon in Python, leveraging the `pytest-asyncio` plugin for managing
asynchronous test execution and Falcon's own testing utilities.

### 1.1. The Importance of Testing WebSocket APIs

Unlike traditional RESTful APIs that follow a stateless request-response model,
WebSocket interactions are stateful and long-lived. This introduces complexities
such as connection management (establishment, maintenance, termination), message
sequencing, handling concurrent messages, and managing server-side state
associated with each connection. Rigorous testing is therefore essential to
validate:

- Correct handshake procedures and connection lifecycle management.
- Bidirectional message flow, including various data types (text, binary,
  structured media like JSON).
- Error handling, including abrupt disconnections and protocol errors.
- Authentication and authorization mechanisms.
- Behavior under specific network conditions (though simulating network issues
  is often beyond basic unit/integration testing).
- Subprotocol negotiation if used.

Effective testing ensures that the real-time features of an application function
as expected, providing a stable and reliable user experience.

### 1.2. Overview of Falcon's ASGI and WebSocket Support

Falcon's support for WebSockets is integrated into its ASGI application model.1
When a client initiates a WebSocket handshake request, Falcon routes it to a
resource class, similar to HTTP requests. If the resource implements an
`async def on_websocket(self, req, ws):` responder, this coroutine is invoked to
handle the WebSocket connection.1

The `req` object provides details about the initial handshake request, while the
`ws` object (`falcon.asgi.WebSocket`) is the primary interface for interacting
with the WebSocket connection. Key methods on the `ws` object include:

- `await ws.accept(subprotocol=None)`: To accept the incoming WebSocket
  connection.4
- `await ws.receive_text()`, `await ws.receive_data()`,
  `await ws.receive_media()`: To receive messages from the client.4
- `await ws.send_text(payload)`, `await ws.send_data(payload)`,
  `await ws.send_media(media)`: To send messages to the client.4
- `await ws.close(code=1000, reason=None)`: To close the WebSocket connection.4
- Properties like `ws.closed` and `ws.ready` provide information about the
  connection state.4

Falcon also allows WebSocket flows to be augmented with middleware components
and custom media handlers for structured data like JSON.4 If a connection is
lost, Falcon typically raises a `WebSocketDisconnected` exception within the
`on_websocket` handler when a receive or send operation is attempted.4

### 1.3. Introduction to `pytest` and `pytest-asyncio`

`pytest` is a mature and feature-rich testing framework for Python that
emphasizes ease of use and extensibility. It supports test discovery, fixtures
for managing test dependencies and state, and detailed reporting.6

`pytest-asyncio` is a `pytest` plugin specifically designed to facilitate the
testing of `asyncio`-based code.7 It enables test functions to be defined as
coroutines (`async def`) and handles the execution of these coroutines within an
`asyncio` event loop. This allows developers to use `await` directly within
their test functions, simplifying the testing of asynchronous operations.7 Test
functions intended to run asynchronously are typically marked with the
`@pytest.mark.asyncio` decorator.8

## 2. Setting Up the Testing Environment

A proper testing environment is foundational for writing effective WebSocket
tests. This involves installing necessary libraries and configuring
`pytest-asyncio`.

### 2.1. Required Installations

To test Falcon WebSocket APIs with `pytest-asyncio`, the following packages are
typically required:

- `falcon`: The Falcon framework itself. Ensure the version used supports ASGI
  and WebSockets.2
- `pytest`: The core testing framework.6
- `pytest-asyncio`: The plugin for `asyncio` support in `pytest`.8
- An ASGI server for running the Falcon application during development (e.g.,
  `uvicorn`, `hypercorn`), though not strictly required for the testing
  utilities like `ASGIConductor` which simulate the app directly.2

These can be installed using `pip`:

```bash
pip install falcon pytest pytest-asyncio
```

It is highly recommended to use a virtual environment to manage project
dependencies and avoid conflicts.9

### 2.2. Configuring `pytest-asyncio` Modes (`strict` vs. `auto`)

`pytest-asyncio` offers different modes of operation, primarily `strict` and
`auto`, which dictate how it discovers and handles asynchronous tests and
fixtures. This mode can be configured in `pytest.ini`, `pyproject.toml`, or via
a command-line option (`--asyncio-mode`).12

- `strict` **mode (default since** `pytest-asyncio` **>=0.19 12):**

  - Asynchronous test functions *must* be explicitly marked with
    `@pytest.mark.asyncio`.
  - Asynchronous fixtures *must* be decorated with `@pytest_asyncio.fixture`.
  - This mode is preferred when a project might use multiple asynchronous
    libraries (e.g., `asyncio` and `trio`) to ensure `pytest-asyncio` only
    handles items explicitly designated for it.12

- `auto` **mode:**

  - `pytest-asyncio` automatically treats any `async def` test function as an
    `asyncio` test, implicitly adding the `@pytest.mark.asyncio` marker.
  - It also treats `async def` fixtures decorated with the standard
    `@pytest.fixture` as `pytest-asyncio` fixtures.
  - This mode simplifies configuration for projects exclusively using
    `asyncio`.12

**Example** `pytest.ini` **configuration for** `auto` **mode:**

```ini
[pytest]
asyncio_mode = auto
```

For most new projects focusing solely on `asyncio` with Falcon, `auto` mode can
reduce boilerplate. However, `strict` mode's explicitness can prevent ambiguity,
especially in complex setups or when integrating with other async tools.
Understanding the active mode is crucial, as it affects whether markers and
specific fixture decorators are mandatory. If tests or async fixtures seem to be
ignored or misbehave, an incorrect mode configuration or missing markers (in
`strict` mode) is a common cause.

## 3. Understanding Falcon's Testing Utilities for ASGI and WebSockets

Falcon provides testing utilities designed to simulate requests to ASGI
applications, including WebSocket interactions. For WebSockets,
`falcon.testing.ASGIConductor` is the key component.

### 3.1. `falcon.testing.TestClient` vs. `falcon.testing.ASGIConductor`

Falcon offers two primary classes for testing: `falcon.testing.TestClient` and
`falcon.testing.ASGIConductor`.

- `falcon.testing.TestClient`: This class is a convenient wrapper for simulating
  HTTP requests to WSGI or ASGI applications.6 It simulates the entire app
  lifecycle for a request in a single shot. However, `TestClient` is **not
  suitable** for testing streaming endpoints like WebSockets or Server-Sent
  Events, nor for simulating multiple interleaved requests.14 Attempting to use
  `TestClient` for WebSocket testing will not provide the necessary control over
  the persistent connection.

- `falcon.testing.ASGIConductor`: This class is specifically designed for more
  fine-grained control over the lifecycle of simulated requests in ASGI
  applications. It is the **recommended tool for testing WebSockets** and other
  streaming protocols.14 `ASGIConductor` allows for simulating the ASGI lifespan
  events and provides methods to establish and interact with simulated WebSocket
  connections. Its asynchronous interface is essential for testing the
  back-and-forth nature of WebSocket communication.14

The distinction is critical: for any WebSocket testing with Falcon,
`ASGIConductor` must be used.

### 3.2. Setting Up an `ASGIConductor` Fixture in `pytest`

To use `ASGIConductor` in `pytest` tests, it's conventional to create a fixture
that provides an instance of it. This fixture can then be injected into test
functions.

Assuming the Falcon ASGI application instance is named `app` (e.g.,
`app = falcon.asgi.App()`), a `pytest` fixture for `ASGIConductor` would look
like this:

```python
# conftest.py or your test file
import pytest
from falcon import testing
from my_falcon_app import app # Assuming your Falcon ASGI app is 'app'

@pytest.fixture
def conductor():
    return testing.ASGIConductor(app)
```

This `conductor` fixture can now be used by any asynchronous test that needs to
interact with the Falcon application's WebSocket endpoints. The `ASGIConductor`
itself is instantiated synchronously; its methods for simulating WebSocket
connections are asynchronous and will be `await`ed within the tests.

### 3.3. Using `conductor.simulate_ws()` for Test Connections

The primary method for establishing a simulated WebSocket connection with
`ASGIConductor` is `simulate_ws(path, **kwargs)`.14 This method is an
asynchronous context manager.

When used with `async with`, it attempts to perform a WebSocket handshake with
the specified `path` on the Falcon application. If the handshake is successful
(typically meaning the server-side `on_websocket` handler calls
`await ws.accept()`), it yields a `falcon.testing.ASGIWebSocketSimulator`
object. This simulator object acts as the test client's interface to the
WebSocket, providing methods to send and receive messages.

**Example structure:**

```python
@pytest.mark.asyncio
async def test_websocket_connection(conductor): # conductor fixture is injected
    async with conductor.simulate_ws('/your_websocket_endpoint') as ws_client:
        # ws_client is an instance of falcon.testing.ASGIWebSocketSimulator
        # Interactions with the WebSocket occur here using ws_client methods
        # e.g., await ws_client.send_text("Hello")
        # e.g., response = await ws_client.receive_text()
        pass
    # When the 'async with' block exits, the WebSocket connection is closed.
```

The `ASGIWebSocketSimulator` object (`ws_client` in the example) will have
methods such as `send_text()`, `receive_text()`, `send_data()`,
`receive_data()`, `send_media()`, `receive_media()`, and `close()`, mirroring
the capabilities of a real WebSocket client and corresponding to the server-side
`falcon.asgi.WebSocket` methods.4 This setup provides the necessary tools to
begin writing detailed WebSocket tests.

## 4. Writing Asynchronous WebSocket Tests with `pytest-asyncio`

With the environment and Falcon's `ASGIConductor` set up, tests for various
WebSocket functionalities can be written using `pytest-asyncio`.

### 4.1. Structuring Async Tests: The `@pytest.mark.asyncio` Decorator

All test functions that involve `await` operations, which is standard for
WebSocket interactions, must be decorated with `@pytest.mark.asyncio` (unless
`pytest-asyncio` is in `auto` mode, where it might be implicit for `async def`
test functions).7 This decorator ensures that `pytest` runs the test coroutine
within an `asyncio` event loop.

### 4.2. Basic Connection Tests

These tests verify the fundamental ability to establish and, if necessary,
reject WebSocket connections.

#### 4.2.1. Testing Successful Handshake and Acceptance

A primary test is to ensure that a client can successfully connect to a
WebSocket endpoint and that the server accepts the connection. The
`conductor.simulate_ws()` context manager handles the handshake. If the
server-side `on_websocket` handler calls `await ws.accept()`, the `async with`
block will be entered.

```python
# tests/test_chat_websocket.py
import pytest
from falcon import testing # For ASGIConductor and WebSocketDisconnected
# Assuming 'app' is your Falcon ASGI application instance

# @pytest.fixture for 'conductor' should be defined as shown previously

@pytest.mark.asyncio
async def test_websocket_accepts_connection(conductor):
    async with conductor.simulate_ws('/chat') as ws_client:
        # If this block is entered, the server has successfully accepted the connection.
        # The server's on_websocket handler must have called await ws.accept().
        assert not ws_client.closed  # Verify the connection is initially open
        # Optionally, check for an initial greeting message if the server sends one upon connection.
        # try:
        #     initial_message = await ws_client.receive_text(timeout=0.1) # Use a small timeout
        #     assert initial_message == "Welcome to the chat!"
        # except TimeoutError: # Or asyncio.TimeoutError depending on library
        #     # Handle case where no initial message is sent, or assert it shouldn't be sent
        #     pass
```

If the server does not call `await ws.accept()` and instead closes the
connection or the `on_websocket` handler finishes without accepting, the
behavior of `simulate_ws()` might vary. Falcon typically translates an
unaccepted WebSocket closure by the server into an HTTP 403 Forbidden response
during the handshake phase.4

#### 4.2.2. Testing Connection Rejection Scenarios

It is equally important to test scenarios where the server should reject a
WebSocket connection. This could be due to failed authentication during the
handshake, an invalid path, or other application-specific rules.

If the server rejects the connection by raising an `falcon.HTTPError` (e.g.,
`falcon.HTTPForbidden`) within the `on_websocket` handler *before* calling
`accept()`, or if no `on_websocket` responder is found for the route,
`simulate_ws()` will raise that `HTTPError`.4 `pytest.raises` can be used to
assert this.

```python
import pytest
from falcon import HTTPForbidden, testing

@pytest.mark.asyncio
async def test_websocket_rejects_unauthorized_connection(conductor):
    # This test assumes '/secure_chat' endpoint requires some form of authorization
    # in the handshake headers, and rejects if not present or invalid.
    with pytest.raises(HTTPForbidden):
        # Attempt to connect without providing the required 'X-Auth-Token' header.
        async with conductor.simulate_ws('/secure_chat', headers={'X-Client-Version': '1.0'}) as ws_client:
            # This part should not be reached if the connection is correctly rejected.
            pass
```

Similarly, if the server explicitly calls `await ws.close()` *before*
`await ws.accept()`, Falcon's default behavior is to respond with an HTTP 403
status code to the handshake request.5 This scenario would also be caught by
`pytest.raises(HTTPForbidden)`. Verifying these rejection pathways is crucial
for security and robust connection management, ensuring the server correctly
denies access to unauthorized or malformed connection attempts.

### 4.3. Message Exchange Tests

These tests focus on the core functionality of WebSockets: bidirectional message
passing.

#### 4.3.1. Client Sending, Server Receiving and Responding

This pattern involves the test client sending a message and then asserting the
server's response.

```python
@pytest.mark.asyncio
async def test_websocket_echo_text_message(conductor):
    async with conductor.simulate_ws('/echo') as ws_client: # Assuming an '/echo' endpoint
        message_to_send = "Hello, WebSocket Server!"
        await ws_client.send_text(message_to_send)

        # Wait for the server's response.
        # The server's on_websocket should receive "Hello, WebSocket Server!"
        # and then send back a response, e.g., "Server echoes: Hello, WebSocket Server!"
        response = await ws_client.receive_text(timeout=1) # Use a timeout
        assert response == f"Server echoes: {message_to_send}"
```

The server-side `on_websocket` for such an echo service would typically include
`data = await ws.receive_text()` followed by
`await ws.send_text(f"Server echoes: {data}")`. Tests should cover various
message contents and ensure correct processing and response generation.

#### 4.3.2. Server Sending, Client Receiving

This scenario tests the server's ability to send messages to the client,
potentially unsolicited (e.g., notifications, broadcasts). While `ASGIConductor`
simulates a single client, it can verify that this client receives messages that
would be part of a broader broadcast or server-initiated event stream.

```python
@pytest.mark.asyncio
async def test_websocket_server_sends_greeting(conductor):
    # Assuming the '/chat' endpoint sends a welcome message upon successful connection.
    async with conductor.simulate_ws('/chat') as ws_client:
        # The server's on_websocket, after ws.accept(), might immediately send a message.
        greeting_message = await ws_client.receive_text(timeout=1)
        assert greeting_message == "Welcome to the Chat Room!"
```

Testing true broadcast functionality to multiple clients simultaneously is
complex with single-client simulators like `ASGIConductor`. However, one can
test that a single client correctly receives a message that the server logic
intends to broadcast. For instance, if a message from client A should be
broadcast to all clients (including client A, or excluding client A), one can
simulate client A sending the message, and then check if client A (the same
`ws_client`) receives the broadcasted version if applicable, or simulate another
client (requiring another `ASGIConductor` or more advanced test setup) to verify
receipt. For the scope of typical unit/integration tests with `ASGIConductor`,
focusing on a single client's perspective of a broadcast (i.e., receiving a
message intended for multiple recipients) is a common approach.5

### 4.4. Testing Different Payload Types

WebSockets can transmit text, binary data, and, through application-level
protocols, structured data like JSON.

- **Text Payloads:** Already demonstrated with `ws_client.send_text()` and
  `ws_client.receive_text()`.

- **Binary Payloads:** Use `ws_client.send_data(b'some_binary_data')` and
  `binary_response = await ws_client.receive_data()`.

```python
  @pytest.mark.asyncio
  async def test_websocket_binary_message_exchange(conductor):
      async with conductor.simulate_ws('/binary_processor') as ws_client:
          binary_payload = b'\x01\x02\x03\x04\x05'
          await ws_client.send_data(binary_payload)

          # Assuming server processes and responds with modified binary data
          processed_data = await ws_client.receive_data(timeout=1)
          assert processed_data == b'\x05\x04\x03\x02\x01' # Example response

```

- **JSON (or other Media Types):** Falcon's WebSocket support includes media
  handlers (e.g., `JSONHandlerWS`, `MessagePackHandlerWS`) that can
  automatically serialize and deserialize structured data.4 The `ws_client`
  (ASGIWebSocketSimulator) also supports this via `send_media()` and
  `receive_media()`.

```python
  @pytest.mark.asyncio
  async def test_websocket_json_media_exchange(conductor):
      # Ensure your Falcon app has JSONHandlerWS configured for WebSockets
      # (it's often a default for text-based media if not overridden).
      async with conductor.simulate_ws('/json_echo') as ws_client:
          json_payload = {"type": "command", "action": "start", "params": }
          await ws_client.send_media(json_payload)

          # Server's on_websocket: received_json = await ws.receive_media()
          #                         await ws.send_media(received_json)
          response_json = await ws_client.receive_media(timeout=1)
          assert response_json == json_payload

```

Testing with media handlers ensures that the serialization/deserialization logic
on both the client (simulator) and server sides works correctly for the chosen
media type. This is particularly important for APIs that rely heavily on
structured data formats like JSON.

### 4.5. Testing WebSocket Closure

Properly handling WebSocket closures from both client and server perspectives is
vital.

#### 4.5.1. Client-Initiated Closure

The test client can initiate a closure using
`await ws_client.close(code=1000, reason='Testing client closure')`.

```python
@pytest.mark.asyncio
async def test_websocket_client_initiates_closure(conductor):
    async with conductor.simulate_ws('/chat') as ws_client:
        assert not ws_client.closed
        await ws_client.send_text("A quick message before closing.")
        # Client decides to close the connection.
        await ws_client.close(code=1000, reason="Client finished interaction")
        assert ws_client.closed
        # Server-side on_websocket should detect this closure,
        # typically when trying to receive or send, or via WebSocketDisconnected.
        # Verifying server-side cleanup might require log inspection or checking side effects.
```

After the client closes, the `ws_client.closed` property should reflect this. On
the server side, the `on_websocket` handler would typically encounter a
`falcon.WebSocketDisconnected` exception upon its next attempt to `receive_` or
`send_` on the `ws` object, allowing it to perform any necessary cleanup.4

#### 4.5.2. Server-Initiated Closure

If the server initiates the closure (e.g., `await ws.close()` in
`on_websocket`), the client should detect this. When the
`ASGIWebSocketSimulator` attempts an operation like `receive_text()` on a
connection closed by the server, it should raise an exception indicating the
disconnection. The specific exception is typically
`falcon.testing.WebSocketDisconnected` (from the testing module).

```python
from falcon.testing import WebSocketDisconnected as TestClientWebSocketDisconnected

@pytest.mark.asyncio
async def test_websocket_server_initiates_closure(conductor):
    # Assuming '/timed_chat' endpoint closes the connection after a specific message or timeout.
    async with conductor.simulate_ws('/timed_chat') as ws_client:
        await ws_client.send_text("trigger_server_close_event")

        # Now, the server should close the connection.
        # Any subsequent attempt by the client to receive should raise an error.
        with pytest.raises(TestClientWebSocketDisconnected):
            # This receive call should fail because the server has closed the connection.
            await ws_client.receive_text(timeout=1) # Use timeout to avoid indefinite hang

        assert ws_client.closed
        # Optionally, check ws_client.close_code if the server sends a specific code.
```

The `falcon.testing.ASGIWebSocketSimulator` (`ws_client`) should provide a way
to inspect the close code and reason sent by the server, often as attributes on
the raised exception or on the `ws_client` object itself after closure. This
allows verification that the server is closing connections with appropriate
codes as per the application logic or WebSocket protocol standards.

## 5. Advanced WebSocket Testing Scenarios

Beyond basic connection and message exchange, several advanced scenarios warrant
testing to ensure a robust WebSocket API.

### 5.1. Testing Error Handling

Robust error handling is crucial for WebSocket applications.

#### 5.1.1. Simulating and Verifying Server-Side `WebSocketDisconnected`

When a client disconnects abruptly (e.g., network drop, browser tab closed), the
server-side on_websocket handler should gracefully handle the
falcon.WebSocketDisconnected exception that Falcon raises during subsequent
send/receive attempts.4

Testing this with ASGIConductor can be done by simply exiting the async with
conductor.simulate_ws(...) block, which simulates the client closing the
connection.

```python
# In your Falcon app (e.g., app.py):
# class MyResource:
#     async def on_websocket(self, req, ws):
#         try:
#             await ws.accept()
#             while True:
#                 data = await ws.receive_text() # Will raise WebSocketDisconnected if client drops
#                 #... process data...
#         except falcon.WebSocketDisconnected:
#             print("Client disconnected, cleaning up resources...") # Or log, update DB, etc.
#             # Perform cleanup actions here
#         finally:
#             # ws.close() is often called automatically by Falcon context or if an error propagates
#             pass

# In your tests (e.g., test_app.py):
@pytest.mark.asyncio
async def test_server_handles_client_abrupt_disconnect(conductor, capsys): # capsys for capturing stdout
    async with conductor.simulate_ws('/my_resource_ws') as ws_client:
        await ws_client.send_text("initial message")
    # Exiting the 'async with' block simulates the client disconnecting.
    # The server's on_websocket should now hit the WebSocketDisconnected block.
    # This assertion depends on the server-side cleanup action (e.g., logging).
    captured = capsys.readouterr()
    assert "Client disconnected, cleaning up resources..." in captured.out
```

Verifying the server's cleanup actions might involve checking logs (as above
with `capsys`), database state, or other side effects.

#### 5.1.2. Testing Custom Error Responses and Close Codes from Server

If the on_websocket handler raises an falcon.HTTPError (e.g.,
falcon.HTTPForbidden due to an operational constraint after connection), Falcon
typically converts this into a WebSocket close frame with a specific close code
(usually 3000 + HTTP status code, so 3403 for a 403 error).4

Alternatively, the server can explicitly close the connection with a custom
application-specific code: await ws.close(code=4001,
reason='Application-specific error').

The test client should be able to observe these close codes.

```python
from falcon.testing import WebSocketDisconnected as TestClientWebSocketDisconnected

@pytest.mark.asyncio
async def test_websocket_server_sends_custom_error_close_code(conductor):
    # Assume '/error_trigger_ws' is an endpoint that, upon receiving a specific message,
    # closes the WebSocket connection with a custom code 4001.
    async with conductor.simulate_ws('/error_trigger_ws') as ws_client:
        await ws_client.send_text("trigger_custom_error")

        # Wait for the server to process the message and close the connection.
        # Attempting to receive should raise WebSocketDisconnected.
        with pytest.raises(TestClientWebSocketDisconnected) as exc_info:
            await ws_client.receive_text(timeout=1) # This should detect the server-initiated close.

        assert ws_client.closed
        # The close code should be available on the ws_client or the exception.
        # Falcon's ASGIWebSocketSimulator stores it on itself.
        assert ws_client.close_code == 4001
        # assert ws_client.close_reason == 'Application-specific error' # If reason is also sent and testable
```

#### 5.1.3. Handling Malformed Messages or Unexpected Client Behavior

The server should gracefully handle malformed messages (e.g., invalid JSON when
JSON is expected) or other unexpected client inputs. Falcon's media handlers
might raise `falcon.MediaMalformedError` or `falcon.PayloadTypeError` if
deserialization fails.4 The `on_websocket` handler should catch such exceptions
and respond appropriately (e.g., send an error message over the WebSocket, close
with a specific code, or log and ignore) rather than crashing.

```python
@pytest.mark.asyncio
async def test_websocket_server_handles_malformed_json(conductor):
    # Assuming '/json_processor_ws' expects JSON messages.
    async with conductor.simulate_ws('/json_processor_ws') as ws_client:
        malformed_json_text = "{'this_is_not_valid_json': " # Missing closing brace and quotes
        await ws_client.send_text(malformed_json_text)

        # The server should ideally detect this as malformed.
        # It might send an error message back or close the connection.
        # Option 1: Server sends an error message back
        # error_response = await ws_client.receive_media(timeout=1) # Assuming it sends JSON error
        # assert error_response.get("error") == "Malformed JSON received"

        # Option 2: Server closes connection with a specific code
        with pytest.raises(TestClientWebSocketDisconnected) as exc_info:
            await ws_client.receive_text(timeout=1) # Or receive_media if it tries to send structured error before close
        assert ws_client.close_code == 1003 # Example: "Unsupported Data" or a custom app code
          # (or 3000 + HTTP 400 if default error handling applies)

        # The exact behavior (error message vs. close code) depends on server implementation.
```

Testing these edge cases ensures the server's robustness against potentially
misbehaving or malicious clients.

### 5.2. Testing Authentication and Authorization

Securing WebSocket endpoints is critical. Authentication can occur at the
handshake phase or via messages after connection.

#### 5.2.1. Handshake-Based Authentication

This is the most common method. Credentials (e.g., tokens, API keys) are
typically passed in headers or query parameters during the initial HTTP
handshake request. The server-side `on_websocket` handler inspects `req.headers`
or `req.params` (available from the `req` object passed to `on_websocket`)
before deciding to call `await ws.accept()`.4

```python
@pytest.mark.asyncio
async def test_websocket_handshake_auth_valid_token(conductor):
    # '/secure_ws_endpoint' requires a valid 'X-Auth-Token' header.
    valid_token = "secret-token-123"
    async with conductor.simulate_ws('/secure_ws_endpoint', headers={'X-Auth-Token': valid_token}) as ws_client:
        assert not ws_client.closed # Connection should be accepted with a valid token.
        # Further interactions can occur here.

@pytest.mark.asyncio
async def test_websocket_handshake_auth_invalid_token(conductor):
    invalid_token = "invalid-token-000"
    with pytest.raises(HTTPForbidden): # Or another appropriate falcon.HTTPError
        async with conductor.simulate_ws('/secure_ws_endpoint', headers={'X-Auth-Token': invalid_token}) as ws_client:
            pass # Should not be reached.
```

These tests verify that only clients presenting valid credentials can establish
a WebSocket connection. Falcon's middleware can also be employed to handle such
authentication checks during the `process_request_ws` phase.1

#### 5.2.2. Message-Based Authentication

Less common for the initial connection but sometimes used for subsequent
authorization of actions over an established WebSocket, this involves the client
sending a specific authentication message after the connection is accepted. The
server then validates this message.

```python
@pytest.mark.asyncio
async def test_websocket_message_based_auth(conductor):
    async with conductor.simulate_ws('/auth_via_message_ws') as ws_client:
        # Connection is accepted, but further actions might require an auth message.
        auth_payload = {"type": "auth", "token": "session-specific-token"}
        await ws_client.send_media(auth_payload)

        auth_response = await ws_client.receive_media(timeout=1)
        assert auth_response.get("status") == "authenticated"

        # Now try a protected action
        await ws_client.send_media({"type": "action", "command": "do_something_sensitive"})
        action_response = await ws_client.receive_media(timeout=1)
        assert action_response.get("result") == "sensitive_action_completed"
```

This requires careful sequencing of messages in the test to simulate the
authentication flow.

### 5.3. Testing WebSocket Middleware

Falcon middleware can intercept the WebSocket handshake request using
`process_request_ws(self, req, ws)` (before routing) and
`process_resource_ws(self, req, ws, resource, params)` (after routing, if a
route matches).4 This is useful for cross-cutting concerns like logging,
metrics, or centralized authentication.

To test middleware, one would typically:

1. Define a Falcon application instance that includes the middleware.
2. Create an `ASGIConductor` fixture using this app.
3. Write tests that trigger the middleware's logic and verify its effects (e.g.,
   request modification, connection rejection, attributes added to `req` or
   `ws.scope`).

**Conceptual Example:**

*Application Code (*`app_with_middleware.py`*):*

```python
import falcon
import falcon.asgi

class WSLoggingMiddleware:
    async def process_request_ws(self, req, ws):
        print(f"WebSocket handshake request received for: {req.path}")
        req.context.custom_attribute = "set_by_middleware"

class MyWSRoute:
    async def on_websocket(self, req, ws):
        await ws.accept()
        # Middleware should have added this
        middleware_attr = req.context.custom_attribute
        await ws.send_text(f"Attribute: {middleware_attr}")
        await ws.close()

middleware =
app_mw = falcon.asgi.App(middleware=middleware)
ws_resource = MyWSRoute()
app_mw.add_route('/ws_with_middleware', ws_resource)
```

*Test Code (*`test_middleware.py`*):*

```python
import pytest
from falcon import testing
from app_with_middleware import app_mw # Import the app with middleware

@pytest.fixture
def conductor_with_middleware():
    return testing.ASGIConductor(app_mw)

@pytest.mark.asyncio
async def test_websocket_middleware_adds_attribute(conductor_with_middleware, capsys):
    async with conductor_with_middleware.simulate_ws('/ws_with_middleware') as ws_client:
        response = await ws_client.receive_text(timeout=1)
        assert response == "Attribute: set_by_middleware"

    captured = capsys.readouterr()
    assert "WebSocket handshake request received for: /ws_with_middleware" in captured.out
```

This example demonstrates testing that a middleware component correctly
processes the handshake request and that its modifications are visible to the
`on_websocket` responder. If the middleware were to reject a connection (e.g.,
by raising `falcon.HTTPForbidden`), that would also be testable using
`pytest.raises`.

### 5.4. Testing Subprotocol Negotiation

WebSockets allow clients and servers to negotiate an application-level
subprotocol during the handshake. The client sends a list of desired
subprotocols, and the server can choose one to accept. Falcon supports this via
`await ws.accept(subprotocol='chosen_protocol')`.4

The `ASGIConductor.simulate_ws()` method accepts a `subprotocols` argument (a
list of strings). The `ASGIWebSocketSimulator` object (the `ws_client`) should
then provide a way to inspect the subprotocol selected by the server (e.g., a
`ws_client.subprotocol` attribute).

```python
@pytest.mark.asyncio
async def test_websocket_subprotocol_negotiation_success(conductor):
    client_protocols = ['chat.v1', 'chat.v2', 'legacy.chat']
    # Server is configured to accept 'chat.v2' from this list.
    async with conductor.simulate_ws('/chat_subprotocol', subprotocols=client_protocols) as ws_client:
        # Assuming the ASGIWebSocketSimulator instance (ws_client) exposes the accepted subprotocol.
        # The exact attribute name might vary; check Falcon's documentation for ASGIWebSocketSimulator.
        # Let's assume it's `ws_client.accepted_subprotocol` or `ws_client.subprotocol`.
        # For this example, we'll hypothesize `ws_client.subprotocol`.
        assert ws_client.subprotocol == 'chat.v2' # This needs verification against actual attribute name.
        # If the server doesn't accept any, ws_client.subprotocol might be None or an empty string.

@pytest.mark.asyncio
async def test_websocket_subprotocol_negotiation_failure(conductor):
    client_protocols = ['unsupported.protocol']
    # Server does not support 'unsupported.protocol'.
    # The behavior if no common subprotocol is found can vary:
    # 1. Server might accept the connection without a subprotocol.
    # 2. Server might reject the connection (e.g., HTTP 400 or other error).
    # This depends on the server's implementation.
    async with conductor.simulate_ws('/chat_subprotocol', subprotocols=client_protocols) as ws_client:
        # Assuming server accepts without a subprotocol if none match.
        assert ws_client.subprotocol is None # Or an empty string
```

Testing subprotocol negotiation ensures that the application correctly handles
protocol versioning or different message formats as agreed during the handshake.

### 5.5. Considerations for Testing Broadcast/Multi-Client Scenarios

`ASGIConductor` is designed to simulate a single client connection.14 Testing
true multi-client scenarios (e.g., ensuring a message sent by client A is
received by clients B and C in a chat room) with `ASGIConductor` directly is
challenging.

Conceptual approaches include:

- **Testing one leg of the broadcast:** Verify that *a* client receives a
  message that was intended for broadcast. For instance, if a server broadcasts
  an event, a single simulated client can check if it receives that event.
- **More complex orchestration:** For more rigorous multi-client testing, one
  might need to:
  - Instantiate multiple `ASGIConductor` objects.
  - Run their `simulate_ws()` interactions concurrently, perhaps using
    `asyncio.gather` to manage multiple client simulation tasks.
  - Use shared state or `asyncio.Queue` objects to coordinate actions and
    assertions between these simulated clients. This type of setup is
    significantly more complex and moves beyond typical unit/integration testing
    with a single `ASGIConductor` instance. It often borders on end-to-end
    testing.

For most applications, testing the server's logic for *emitting* a broadcast
(e.g., ensuring it attempts to send to all known connections in its internal
state) and then testing that a *single* client correctly *receives* such a
message provides a good level of confidence. The inherent limitation of client
simulators means that full, simultaneous multi-client interaction testing might
require different tools or strategies.

## 6. Best Practices for Robust WebSocket Testing

Adhering to best practices in testing leads to more reliable, maintainable, and
effective test suites for WebSocket APIs.

### 6.1. Clear and Maintainable Test Structure

Organize tests logically, for example, by WebSocket endpoint, feature, or
message type. Use descriptive names for test functions and test files to clearly
indicate their purpose.

```python
# e.g., tests/websockets/test_chat_room.py

@pytest.mark.asyncio
async def test_user_joins_chat_and_receives_welcome(conductor):...

@pytest.mark.asyncio
async def test_user_sends_message_is_echoed_to_self(conductor):...
```

### 6.2. Effective Use of Pytest Fixtures

Pytest fixtures are powerful for managing test setup, teardown, and
dependencies.6

- Use `@pytest.fixture` (or `@pytest_asyncio.fixture` for asynchronous
  setup/teardown 12) to provide common resources like the `ASGIConductor`
  instance, pre-configured client states, or mock objects.
- Consider fixture scopes (`function`, `class`, `module`, `session`) to optimize
  resource creation and sharing.19 For instance, an `ASGIConductor` for a
  stateless app might be function-scoped, while one for an app that loads
  expensive resources at startup could be module or session-scoped if the tests
  don't modify shared app state in a conflicting way.

```python
# conftest.py
import pytest
import pytest_asyncio # If using @pytest_asyncio.fixture
from falcon import testing
from my_app import create_app # Your app factory

@pytest.fixture(scope="module") # Example: module scope if app setup is expensive
def app_instance():
    return create_app()

@pytest_asyncio.fixture(scope="function") # Function scope for conductor ensures clean state per test
async def conductor(app_instance):
    async with testing.ASGIConductor(app_instance) as cond: # ASGIConductor can be an async context manager itself
        yield cond
    # Teardown for conductor, if any, happens after yield (handled by ASGIConductor's __aexit__)
```

Using `ASGIConductor` as an async context manager within an async fixture
ensures proper lifespan management if the conductor itself needs async
setup/teardown.

### 6.3. Mocking External Dependencies

WebSocket handlers (`on_websocket`) often interact with external systems like
databases, caches, or other microservices. To isolate the WebSocket logic for
testing, these external dependencies should be mocked.

- Use `unittest.mock.AsyncMock` for mocking asynchronous functions or methods
  called by the `on_websocket` handler.
- The `mocker` fixture, provided by the `pytest-mock` plugin (often included or
  easily added), is a convenient way to patch objects. Falcon itself provides
  "WSGI/ASGI testing helpers and mocks" which refers to its simulation
  capabilities rather than general purpose mocking libraries.20

```python
from unittest.mock import AsyncMock

@pytest.mark.asyncio
async def test_websocket_saves_message_to_db(conductor, mocker):
    # Assume MyDbService.save_message is an async method
    mock_save_message = AsyncMock()
    mocker.patch('my_app.services.MyDbService.save_message', new=mock_save_message)

    async with conductor.simulate_ws('/chat_persistent') as ws_client:
        await ws_client.send_text("Store this message")
        # Allow some time for server to process and call the mock
        await asyncio.sleep(0.01) # Small delay if needed, or wait for a response

    mock_save_message.assert_called_once_with("Store this message")
```

Mocking ensures that tests are focused on the WebSocket interaction logic
itself, making them faster, more reliable, and independent of external system
states or availability.

### 6.4. Managing Test Data and State

Develop strategies for providing varied and representative inputs to WebSocket
handlers. Parameterized testing with `pytest.mark.parametrize` can be very
effective for this. Ensure that each test starts with a clean, predictable
state, especially if the application or its dependencies are stateful. Fixtures
are key to managing this state.

### 6.5. Ensuring Test Isolation

Each test should run independently and not interfere with other tests. This
means avoiding shared mutable state between tests unless explicitly managed by
higher-scoped fixtures with proper setup and teardown. Function-scoped fixtures
for resources like `ASGIConductor` generally promote good isolation.

### 6.6. Timeouts for Robustness

Asynchronous operations, particularly network-dependent ones like
`ws_client.receive_*()`, can potentially hang if the expected message never
arrives. Using the `timeout` parameter available in `ASGIWebSocketSimulator`'s
receive methods (e.g., `await ws_client.receive_text(timeout=1.0)`) is crucial
for preventing tests from stalling indefinitely.

```python
@pytest.mark.asyncio
async def test_websocket_receive_with_timeout(conductor):
    async with conductor.simulate_ws('/no_reply_endpoint') as ws_client:
        with pytest.raises(asyncio.TimeoutError): # Or specific timeout exception from Falcon/async lib
            await ws_client.receive_text(timeout=0.1) # Expect this to timeout
```

This practice makes the test suite more resilient and provides faster feedback
on failures.

## 7. Troubleshooting Common Pitfalls

When testing asynchronous WebSocket applications, certain common issues may
arise.

### 7.1. Event Loop Issues with `pytest-asyncio`

While `pytest-asyncio` generally manages the event loop well via its
`event_loop` fixture 9, incorrect manual loop management or interactions between
different async libraries can sometimes lead to errors like "Got Future \<Future
pending> attached to a different loop." Sticking to `pytest-asyncio`'s
conventions usually avoids these problems.

### 7.2. `pytest-asyncio` Mode Misconfigurations

If tests are not being discovered as async, or if async fixtures are not working
as expected, verify the `pytest-asyncio` mode (`strict` vs. `auto`). In `strict`
mode (the default), ensure `@pytest.mark.asyncio` is used on async test
functions and `@pytest_asyncio.fixture` on async fixtures.12

### 7.3. Incorrect `ASGIConductor` Usage

- **Forgetting** `async with`**:** `conductor.simulate_ws()` returns an
  asynchronous context manager and must be used with `async with`.14
- **Using** `TestClient` **for WebSockets:** `falcon.testing.TestClient` is not
  suitable for WebSockets; `ASGIConductor` must be used.14

### 7.4. Timeouts and Race Conditions in Async Tests

Asynchronous tests can sometimes be prone to intermittent failures due to timing
issues or race conditions if not carefully written.

- Ensure all asynchronous operations are properly `await`ed.
- Use explicit synchronization mechanisms (`asyncio.Event`, `asyncio.Queue`) if
  coordinating multiple asynchronous tasks within a test.
- Be cautious about relying on fixed `asyncio.sleep()` delays for
  synchronization; prefer event-driven logic where possible (e.g., waiting for a
  specific message).

### 7.5. Forgetting `await ws.accept()` on the Server

A very common error when implementing WebSocket handlers is forgetting to call
`await ws.accept()` at the beginning of the `on_websocket` coroutine.4 If the
server does not accept the connection, the client-side `simulate_ws()` will
likely fail to establish the connection, often resulting in an HTTP error during
the handshake (e.g., 403 Forbidden if the handler exits or closes before
accepting) or the test client hanging until a timeout. This is a fundamental
part of the WebSocket protocol; without acceptance, no further communication can
occur. Test failures related to connection establishment should prompt a check
for `await ws.accept()` in the server code.

## 8. Conclusion and Further Learning

### 8.1. Recap of Key Testing Strategies for Falcon WebSockets

Testing WebSocket APIs implemented with Falcon and ASGI requires a shift from
traditional stateless API testing. The combination of Falcon's `ASGIConductor`
and `pytest-asyncio` provides a robust framework for this purpose. Key
strategies involve:

- Utilizing `ASGIConductor` and its `simulate_ws()` method to establish and
  interact with simulated WebSocket connections.
- Employing `pytest-asyncio` with the `@pytest.mark.asyncio` decorator to write
  asynchronous test functions.
- Thoroughly testing the connection lifecycle: handshake success and rejection,
  various message types (text, binary, media-handled), client- and
  server-initiated closures.
- Validating error handling, authentication mechanisms, middleware integration,
  and subprotocol negotiation.
- Adopting best practices such as clear test structure, effective fixture usage,
  mocking external dependencies, and using timeouts.

### 8.2. Pointers to Official Documentation

For more in-depth information and the latest updates, consult the official
documentation:

- **Falcon Framework:**
  - General Documentation: 3
  - ASGI Support: (Refer to ASGI sections within Falcon docs, e.g., related to
    `falcon.asgi.App`) 3
  - WebSocket Usage: 4
  - Testing Helpers (including `ASGIConductor`): 14
- `pytest-asyncio`**:**
  - Plugin Documentation: 7 (Primary documentation sources).

### 8.3. Encouragement for Comprehensive Testing

Real-time applications built with WebSockets introduce unique complexities.
Comprehensive testing across all aspects of WebSocket communication is not
merely a best practice but a necessity for building reliable, secure, and
high-performing applications. By diligently applying the techniques outlined in
this guide, developers can significantly improve the quality and robustness of
their Falcon-based WebSocket services.
