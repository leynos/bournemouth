# A Comprehensive Guide to Mocking httpx with pytest-httpx

## 1. Introduction to httpx and the Need for Mocking The httpx library has emerged

as a modern, powerful HTTP client for Python, offering support for both
synchronous and asynchronous programming paradigms, HTTP/1.1 and HTTP/2
protocols, and a feature set comparable to the widely-used requests library but
with significant enhancements. Its capabilities include connection pooling,
cookie persistence, automatic content decoding, support for proxies, and robust
timeout handling, making it suitable for a wide array of applications, from
simple API interactions to complex microservice communications and web scraping
tasks. The library's design prioritizes usability, type safety, and performance,
particularly in asynchronous contexts where concurrent I/O operations can
significantly improve application responsiveness. Testing applications that
interact with external HTTP services presents several challenges. Real network
calls introduce flakiness, as tests can fail due to network issues, server
downtime, or rate limiting, none of which reflect a bug in the application code
itself. Furthermore, these external calls can be slow, significantly increasing
test suite execution time. They may also have side effects (e.g., creating
resources on a live server) or incur costs if the API is a paid service. To
mitigate these issues, mocking HTTP requests is an essential practice in
software testing. Mocking involves replacing the parts of the system that
communicate with external services with controlled "test doubles" that simulate
the behavior of those services. This allows tests to run quickly, reliably, and
in isolation, focusing solely on the logic of the application under test.
pytest, a popular Python testing framework, excels at simplifying test creation
and reducing boilerplate through its fixture system and plugin architecture.
pytest-httpx is a pytest plugin specifically designed to facilitate the mocking
of httpx requests within tests. It provides a fixture, httpx_mock, that
intercepts outgoing httpx requests and allows developers to define custom
responses, thereby enabling comprehensive testing of network-dependent code
without making actual HTTP calls. This guide provides an in-depth exploration of
pytest-httpx, covering its installation, fundamental usage, advanced mocking
techniques, and best practices for effectively testing applications built with
httpx.

## 2. Understanding pytest and Fixtures pytest is a mature and flexible testing

framework for Python that has gained widespread adoption due to its concise
syntax, powerful features, and extensive plugin ecosystem. It simplifies test
discovery, execution, and reporting, allowing developers to write tests ranging
from simple unit tests to complex functional and integration test scenarios. One
of pytest's cornerstone features is its fixture system. Fixtures are functions
that pytest runs before (and sometimes after) test functions. They are primarily
used to set up and tear down resources or states required for tests, such as
database connections, temporary files, or, in the context of this guide, mock
objects. By encapsulating setup and teardown logic, fixtures promote modularity
and reusability, allowing the same setup to be used across multiple tests
without code duplication. This ensures a consistent and correctly configured
environment for each test, isolating test cases and improving reproducibility.
Fixtures can be scoped (e.g., function, class, module, session) to control their
lifecycle and can be automatically applied to tests using the autouse=True
attribute. The pytest-httpx library leverages this fixture system by providing
the httpx_mock fixture. This fixture, once included as an argument in a test
function, automatically intercepts all HTTP requests made by the httpx library
during that test's execution. This seamless integration means developers do not
need to manually patch httpx functions or manage the lifecycle of mock objects;
pytest and pytest-httpx handle this transparently. This approach significantly
simplifies the test setup process compared to manual patching techniques (e.g.,
using unittest.mock.patch or pytest-mock's mocker.patch.object ), reducing
boilerplate code and minimizing the risk of errors associated with incorrect
patch management, such as patches not being applied correctly or persisting
beyond the intended test scope. The fixture mechanism ensures that mocking is
active only during the test and is properly cleaned up afterward, contributing
to test isolation.

## 3. Setting Up pytest-httpx 3.1. Installation To begin using pytest-httpx, it

must be installed in the Python environment alongside pytest and httpx. Use `uv`
to add it to the `dev` dependency group and install the dependencies:

```bash
uv add --group dev pytest-httpx
uv venv
uv pip install --group dev -e .
```

These commands update `pyproject.toml`, lock the new dependency, and install all
development dependencies (including your project in editable mode). pytest-httpx
requires Python 3.9 or higher, while httpx itself requires Python 3.8 or higher.
Ensure that the project's Python version meets these requirements. 3.2. Basic
Fixture Usage (httpx_mock) Once installed, pytest-httpx makes its primary
fixture, httpx_mock, available to pytest. To use it, a test function simply
needs to accept httpx_mock as an argument. This signals to pytest to inject and
activate the fixture for the duration of that test. A minimal synchronous test
example demonstrating the fixture usage is as follows: import httpx from
pytest_httpx import HTTPXMock # For type hinting

def test_sync_example(httpx_mock: HTTPXMock):
httpx_mock.add_response(url="https://test_url", json={"data": "success"}) # Code
under test that makes a GET request to "https://test_url" response =
httpx.get("https://test_url") assert response.json() == {"data": "success"}

In this example, httpx_mock.add_response() is used to define a mock response for
requests to "https://test_url". Any call to httpx.get("https://test_url") within
this test will be intercepted and receive the defined JSON response. For
asynchronous code utilizing httpx.AsyncClient, pytest-httpx works seamlessly
with pytest.mark.asyncio. The test function should be an async def function:
import pytest import httpx from pytest_httpx import HTTPXMock # For type hinting

@pytest.mark.asyncio async def test_async_example(httpx_mock: HTTPXMock):
httpx_mock.add_response(url="https://test_url", json={"data": "async_success"})
\# Code under test that uses httpx.AsyncClient async with httpx.AsyncClient() as
client: response = await client.get("https://test_url") assert response.json()
== {"data": "async_success"}

Using the HTTPXMock type hint (httpx_mock: HTTPXMock) is recommended for better
editor support, such as autocompletion and type checking, enhancing the
development experience. The httpx_mock fixture's ability to implicitly support
both top-level httpx functions (e.g., httpx.get()) and client instances
(httpx.Client, httpx.AsyncClient) without requiring different setup procedures
indicates a deep integration with httpx's internal mechanisms. This is likely
achieved by patching httpx at the transport layer level. Such an approach
ensures that pytest-httpx is robust across various httpx usage patterns commonly
found in applications. If the patching were at a higher level, for instance,
only targeting the httpx.get function, it might fail to intercept requests made
through client instances or other httpx methods, necessitating more complex and
pattern-specific mocking setups. The consistent fixture usage for all types of
httpx calls points to a unified and reliable interception mechanism. 4. Basic
Mocking Techniques with httpx_mock.add_response() The cornerstone of defining
mock responses with pytest-httpx is the httpx_mock.add_response() method. This
versatile method allows developers to specify the characteristics of the
response that httpx should receive when a request matches certain criteria. If
add_response() is invoked without any arguments, it registers a default mock
that matches any HTTP request. This default response is an HTTP/1.1 200 OK with
an empty body. This can be particularly useful for initial test scaffolding or
This "fail open" characteristic for basic mock setup allows developers to
quickly establish a baseline mock and iteratively refine its specificity. This
can accelerate the initial phases of test writing, enabling a focus on the core
logic before detailing every aspect of the HTTP interaction.

Typically, a mock response is targeted at a specific URL. For simple GET
requests:

```python
httpx_mock.add_response(url="https://api.example.com/data")
# A call like client.get("https://api.example.com/data") will be matched
```

To mock different HTTP methods such as POST, PUT, DELETE, PATCH, HEAD, or
OPTIONS, the method parameter is used. This parameter accepts a string
representing the HTTP method; it is case-insensitive as pytest-httpx internally
converts it to uppercase. httpx_mock.add_response(method="POST",
url="<https://api.example.com/submit>") httpx_mock.add_response(method="PUT",
url="<https://api.example.com/update/1>")
httpx_mock.add_response(method="DELETE",
url="<https://api.example.com/resource/1>")

The HTTP status code of the mocked response can be customized using the
status_code parameter, which takes an integer value :
httpx_mock.add_response(url="<https://api.example.com/notfound>",
status_code=404)
httpx_mock.add_response(url="<https://api.example.com/created>",
status_code=201, method="POST")

Defining the content of the mocked response is crucial. pytest-httpx offers
several convenient parameters for this:

- JSON: The json parameter accepts a Python dictionary or list. pytest-httpx
  automatically serializes this to a JSON string, sets the Content-Type header
  to application/json, and uses it as the response body. Given the prevalence of
  JSON in modern APIs , this automation significantly reduces boilerplate
  compared to manual serialization and header setting.
  httpx_mock.add_response(url="<https://api.example.com/user/123>",
  json={"message": "Success!", "id": 123})

- Text: For plain text responses, the text parameter is used. The Content-Type
  may default to text/plain or can be explicitly set via the headers parameter.
  httpx_mock.add_response(url="<https://api.example.com/greeting>", text="Hello,
  world!")

- Bytes: The content parameter is used for providing a binary response body as
  bytes. httpx_mock.add_response(url="<https://api.example.com/binary-data>",
  content=b"\\x00\\x01\\x02\\x03")

- HTML: While some documentation hints at a dedicated `html` parameter, a more
  general approach is to use the `text` parameter with an appropriate
  Content-Type header:

```python
httpx_mock.add_response(
    url="https://api.example.com/page",
    text="<h1>Title</h1><p>Content</p>",
    headers={"Content-Type": "text/html"},
)
```

- Multipart body: pytest-httpx supports defining responses that simulate
  multipart content, although the primary focus in documentation snippets is on
  matching incoming multipart requests. For sending a multipart response, one
  would typically construct the multipart body manually (or using appropriate
  Python libraries) and provide it via the content parameter along with the
  correct Content-Type header including the boundary. Response headers can be
  customized using the headers parameter, which accepts a dictionary :
  httpx_mock.add_response(url="<https://api.example.com/custom>",
  headers={"X-Custom-Header": "TestValue", "Content-Language": "en-US"})

For testing interactions with servers using HTTP/2.0, the http_version parameter
can be set:
httpx_mock.add_response(url="<https://api.example.com/http2_service>",
http_version="HTTP/2.0")

The design philosophy of providing high-level abstractions like the json
parameter for common patterns, while still allowing low-level control via
content and headers for other data types, underscores a commitment to developer
experience for frequent tasks. A summary of key httpx_mock.add_response()
parameters is provided below: | Parameter | Type | Description | Example Usage |
|---|---|---|---| | url | str, re.Pattern, httpx.URL | The URL to match. If not
provided, matches any URL. | url="<https://example.com/data>" | | method | str |
The HTTP method to match (e.g., "GET", "POST"). Case-insensitive. |
method="POST" | | status_code | int | The HTTP status code for the response.
Defaults to 200. | status_code=404 | | json | dict, list | Python object to be
serialized as JSON response body. Sets Content-Type: application/json. |
json={"key": "value"} | | text | str | String content for the response body. |
text="Hello" | | content | bytes | Byte content for the response body. |
content=b"\\x01\\x02" | | headers | dict | Dictionary of HTTP headers for the
response. | headers={"X-API-KEY": "secret"} | | http_version | str | HTTP
version string for the response (e.g., "HTTP/1.1", "HTTP/2.0"). Defaults to
"HTTP/1.1". | http_version="HTTP/2.0" | This table centralizes information that
is otherwise distributed across various examples , serving as a quick reference.
5\. Advanced Request Matching Beyond basic URL and method matching, pytest-httpx
provides a rich set of parameters to define more specific criteria for when a
mock response should be applied. This precision is vital for ensuring that tests
accurately reflect the intended interactions with external services and for
robust contract testing. The url parameter itself offers advanced capabilities.
It can accept an exact string, a Python re.Pattern object for regular expression
matching, or an httpx.URL instance. Matching is performed on the full URL,
including any query parameters. The order of query parameters in the request URL
string generally does not affect matching; however, for parameters that can have
multiple values, the order of those values is significant.

```python
import re
import httpx

# Exact string match
httpx_mock.add_response(url="https://example.com/data?param1=val1&param2=val2")

# Regex match for URLs like /users/1, /users/42, etc
httpx_mock.add_response(url=re.compile(r"https://example.com/users/\d+"))

# httpx.URL match, useful for programmatically building URLs with params
httpx_mock.add_response(url=httpx.URL("https://example.com/data", params={"param1": "val1"}))
```

The ability to use regular expressions or unittest.mock.ANY (for JSON matching,
discussed below) provides valuable flexibility. It allows tests to be resilient
against minor, irrelevant variations in requests—such as a dynamically generated
timestamp in a URL path or a unique ID in a JSON payload—while still rigorously
asserting the critical components of the request. This balance between
specificity and flexibility is key to writing maintainable tests that do not
break with every inconsequential change. To match requests based on specific
HTTP headers, the match_headers parameter is used. It takes a dictionary where
keys are header names and values are the expected header values. Matching is
performed on equality for each provided header, and header names are typically
treated case-insensitively. httpx_mock.add_response(
url="<https://api.example.com/protected>", match_headers={"Authorization":
"Bearer testtoken", "X-API-Version": "2"} )

This mock will match a request to the URL if it includes an 'Authorization'
header with the value 'Bearer testtoken' and an 'X-API-Version' header with the
value '2'.

- match_content: This parameter expects the full HTTP request body as bytes and
  performs an exact equality match. httpx_mock.add_response(method="POST",
  url="<https://example.com/binary_upload>", match_content=b"Exact byte content
  of the request")

- match_json: For requests with a JSON body, this parameter takes a Python
  dictionary or list. pytest-httpx will parse the request's JSON body and
  compare it to the provided object. For partial matching within the JSON

```python
from unittest.mock import ANY
httpx_mock.add_response(
    method="POST",
    url="https://example.com/submit_json",
    match_json={"key1": "value1", "timestamp": ANY, "user_id": 123},
)
# A POST request to the URL with JSON body
# {"key1": "value1", "timestamp": "2023-10-27T10:00:00Z", "user_id": 123} would match
```

- match_data: If the request sends form-encoded data
  (application/x-www-form-urlencoded), this parameter takes a dictionary to
  match against the form fields. httpx_mock.add_response(method="POST",
  url="<https://example.com/form_submit>", match_data={"field1": "data1",
  "field2": "another_value"})

- match_files: For multipart/form-data requests (typically file uploads),
  match_files allows matching based on the uploaded files. The expected
  structure is a dictionary where keys are field names and values are tuples,
  often ("filename.ext", b"File content"). This can be combined with match_data
  for other form fields in the same multipart request. httpx_mock.add_response(
  method="POST", url="<https://example.com/upload_file>",
  match_files={"document": ("report.txt", b"This is the report content.")},
  match_data={"description": "Monthly financial report"} )

If the application under test routes requests through an HTTP proxy,
pytest-httpx can match requests based on the proxy_url. This parameter accepts a
string, a re.Pattern instance, or an httpx.URL instance, and matching is

```python
httpx_mock.add_response(proxy_url="http://myproxy.example.com:8080?user=test_user")
# This mock would apply to requests made via an httpx.Client configured with
# client = httpx.Client(proxy="http://myproxy.example.com:8080?user=test_user")
```

```python
httpx_mock.add_response(match_extensions={"custom_timeout_config_key": "aggressive_profile"})
# This would match client.get("...", extensions={"custom_timeout_config_key": "aggressive_profile"})
```

When multiple mock responses are registered that could potentially match an
incoming request, pytest-httpx employs a specific selection logic: it chooses
the first response (based on the order of registration with add_response or
add_callback) that has not yet been sent. Once a matching response has been
provided for a request, it is considered "used" and will not be selected again
for subsequent requests, unless the can_send_already_matched_responses
configuration option is explicitly enabled. This behavior is fundamental for
testing scenarios involving sequential API calls where an endpoint might be hit
multiple times, potentially with different expected outcomes each time (e.g.,
pagination or retry mechanisms). The combination of precise matching criteria
and this ordered selection rule enables the simulation of complex interaction
sequences. The comprehensive suite of matching criteria (match_headers,
match_content, match_json, etc.) empowers developers to create highly specific
and therefore robust tests. This level of specificity is crucial for ensuring
that the code under test is not merely making a request to the correct URL and
method, but is also transmitting the correct payload and headers. This is
particularly important for effective contract testing with external APIs, where
adherence to the API's expected request format is paramount. A summary of
advanced request matching parameters for httpx_mock.add_response() is useful: |
Parameter | Type | Description | |---|---|---| | url | str, re.Pattern,
httpx.URL | Matches the full request URL, including query parameters. Regex and
httpx.URL objects allow flexible matching. | | match_headers | dict | Dictionary
of request headers to match. Equality match for each provided header.
Case-insensitive keys. | | match_content | bytes | Matches the entire request
body as bytes. Exact equality match. | | match_json | dict, list | Matches a
JSON request body. Can use unittest.mock.ANY for partial matching. | |
match_data | dict | Matches form-encoded data in the request body
(application/x-www-form-urlencoded). | | match_files | dict | Matches files in a
multipart/form-data request. Structure: {"name": ("filename", b"content")}. | |
proxy_url | str, re.Pattern, httpx.URL | Matches the URL of the proxy used for
the request. | | match_extensions | dict | Matches based on httpx request
extensions. | This table consolidates details about parameters that allow
fine-grained control over which requests a mock applies to, aiding in the
creation of precise tests. 6. Crafting Dynamic and Complex Responses While
static responses defined via httpx_mock.add_response() cover many testing
scenarios, some situations require responses that are generated dynamically
based on the specifics of the incoming request, or sequences of calls that yield
different results over time. pytest-httpx provides mechanisms for these advanced
use cases, primarily through callbacks. 6.1. Using Callbacks for Dynamic
Response Generation When a predetermined static response is insufficient,
httpx_mock.add_callback() allows a Python function (the callback) to be
registered. This function is invoked when an HTTP request matches the specified
criteria (e.g., url, method). The callback function receives the httpx.Request
object as an argument, providing access to all details of the incoming request,
such as its headers, body, and URL. The callback must then return an
httpx.Response object. This powerful feature enables the simulation of complex
server behaviors where the response content or status might depend on the data
sent in the request.

```python
import httpx
from pytest_httpx import HTTPXMock
def dynamic_response_callback(request: httpx.Request) -> httpx.Response: try: #
Attempt to read and decode JSON, fallback for other content types request_data =
request.json() name = request_data.get("name", "Guest") except Exception: #
Broad exception for simplicity, could be more specific name = "Guest"
request_data_str = request.read().decode(errors='replace') if "special_param" in
request_data_str: return httpx.Response(200, json={"status": "special_text",
"greeting": f"Hello, {name} based on text!"})


if "admin" in name.lower(): return httpx.Response(200, json={"status":
"admin_greeting", "message": f"Welcome, Admin {name}!"}) return
httpx.Response(200, json={"status": "user_greeting", "message": f"Hello,
{name}!"})

```

def test_dynamic_response_with_callback(httpx_mock: HTTPXMock):
httpx_mock.add_callback( dynamic_response_callback,
url="<https://api.example.com/greet>", method="POST" )

```python
# Call 1: Regular user
response1 = httpx.post("https://api.example.com/greet", json={"name": "Alice"})
assert response1.status_code == 200
assert response1.json()["status"] == "user_greeting"
assert response1.json()["message"] == "Hello, Alice!"

# Call 2: Admin user
response2 = httpx.post("https://api.example.com/greet", json={"name": "SuperAdmin Bob"})
assert response2.status_code == 200
assert response2.json()["status"] == "admin_greeting"
assert response2.json()["message"] == "Welcome, Admin SuperAdmin Bob!"

# Call 3: Text payload with special parameter
response3 = httpx.post("https://api.example.com/greet", content="request_with_special_param")
assert response3.status_code == 200
assert response3.json()["status"] == "special_text"
```

Callbacks effectively shift mocking logic from a declarative style (fixed
responses) to an imperative one (programmatic response generation). This is
indispensable for simulating intricate server behaviors that might depend on
request history, specific combinations of query parameters, or complex
validation rules not easily expressed through static matchers. 6.2. Handling
Sequential Requests with Different Responses Testing scenarios like pagination,
retries, or stateful interactions often involves making multiple requests to the
same endpoint, with each request expected to yield a different response.
pytest-httpx supports this in two primary ways:

- Multiple add_response Calls: By registering multiple add_response (or
  add_callback) entries for the same URL and method, they will be consumed in
  the order of registration. This relies on the "first one not yet sent" rule
  for response selection. This method is straightforward for fixed, predictable

```python
def test_sequential_calls_pagination(httpx_mock: HTTPXMock):
    base_url = "https://api.example.com/items"

    # First page of items
    httpx_mock.add_response(url=base_url, params={"page": "1"}, json=[{"id": 1, "name": "Item 1"}])

    # Second page of items
    httpx_mock.add_response(url=base_url, params={"page": "2"}, json=[{"id": 2, "name": "Item 2"}])

    # Attempt to get a third page, results in no more items (e.g., empty list or 404)
    httpx_mock.add_response(url=base_url, params={"page": "3"}, json=[])

    assert httpx.get(base_url, params={"page": "1"}).json() == [{"id": 1, "name": "Item 1"}]
    assert httpx.get(base_url, params={"page": "2"}).json() == [{"id": 2, "name": "Item 2"}]
    assert httpx.get(base_url, params={"page": "3"}).json() == []
```

- Using a Callback with Internal State: For more complex sequences where the
  response logic itself is intricate or depends on an accumulated state from
  previous requests, a callback function or method of a class instance can
  maintain its own state (e.g., a counter, a list of previously seen IDs). This
  import httpx from pytest_httpx import HTTPXMock

```python
class StatefulAPISimulator:
    def __init__(self):
        self.call_count = 0
        self.items_created = []

    def process_request(self, request: httpx.Request) -> httpx.Response:
        self.call_count += 1
        if request.method == "POST":
            new_item_id = f"item_{self.call_count}"
            self.items_created.append(new_item_id)
            return httpx.Response(201, json={"id": new_item_id, "status": "created"})
        elif request.method == "GET":
            return httpx.Response(200, json={"items": self.items_created, "count": len(self.items_created)})
        return httpx.Response(405, text="Method Not Allowed")
```

def test_stateful_api_simulation(httpx_mock: HTTPXMock): simulator =
StatefulAPISimulator() # Register the same callback for multiple methods on the
same URL pattern httpx_mock.add_callback(simulator.process_request,
url="<https://api.example.com/resource_manager>")

```python
# Create first item
response_post1 = httpx.post("https://api.example.com/resource_manager", json={"data": "first"})
assert response_post1.status_code == 201
assert response_post1.json()["id"] == "item_1"

# Create second item
response_post2 = httpx.post("https://api.example.com/resource_manager", json={"data": "second"})
assert response_post2.status_code == 201
assert response_post2.json()["id"] == "item_2"

# Get all items
response_get = httpx.get("https://api.example.com/resource_manager")
assert response_get.status_code == 200
assert response_get.json()["items"] == ["item_1", "item_2"]
assert response_get.json()["count"] == 2
assert simulator.call_count == 3
```

but implemented with pytest-httpx's callback mechanism\]. The choice between
these two methods depends on the complexity of the interaction. Multiple
add_response calls are generally simpler and more declarative for fixed
sequences. Stateful callbacks, however, provide the necessary power for
sequences where the response logic is more involved or relies on evolving state
derived from the history of requests in the sequence. This implies a best
practice: employ the simplest mechanism that adequately models the required
behavior. 7. Verifying Request Interactions (httpx_mock.get_requests()) Beyond
defining how the server should respond, it is often crucial to verify that the
application under test (SUT) is making the correct requests. pytest-httpx
facilitates this through the httpx_mock.get_requests() method and configuration
options. The httpx_mock.get_requests() method returns a list of all
httpx.Request objects that were intercepted and handled by pytest-httpx during
the execution of a test. By examining this list, tests can assert various
aspects of the outgoing requests. For instance, one can check the number of
requests made: from pytest_httpx import HTTPXMock import httpx

def test_single_request_was_made(httpx_mock: HTTPXMock):
httpx_mock.add_response(url="<https://api.example.com/action>") # Code under
test that calls the API once httpx.get("<https://api.example.com/action>")

```python
requests_made = httpx_mock.get_requests()
assert len(requests_made) == 1
```

Each item in the list returned by get_requests() is an instance of
httpx.Request. This object exposes attributes like url, method, headers, and
content (or read() for the body as bytes), allowing for detailed inspection and
assertions: def test_inspect_request_details_example(httpx_mock: HTTPXMock):
target_url = "<https://api.example.com/submit_data>" request_payload =
{"data_key": "test_payload_value"} custom_request_headers = {"X-Trace-ID":
"abcdef12345", "Content-Type": "application/json"}

```python
httpx_mock.add_response(method="POST", url=target_url) # Mock the response
# Code under test making the POST request
httpx.post(target_url, json=request_payload, headers={"X-Trace-ID": "abcdef12345"}) # httpx auto-adds Content-Type for json

made_requests = httpx_mock.get_requests()
assert len(made_requests) == 1

request_object = made_requests
assert str(request_object.url) == target_url # httpx.URL needs string conversion for simple comparison
assert request_object.method == "POST"
assert request_object.headers["x-trace-id"] == "abcdef12345" # Header keys are case-insensitive
assert request_object.headers["content-type"] == "application/json"
# Request content is bytes, so compare with encoded JSON
assert request_object.read() == b'{"data_key": "test_payload_value"}'
```

The ability to inspect raw httpx.Request objects allows for extremely
fine-grained assertions, potentially going beyond what the match\_\* parameters
used in add_response might cover. This is particularly useful for verifying
complex request construction logic within the SUT or when needing to check
subtle details like specific encoding or header formatting that are not covered
by simple equality checks in the matching parameters. pytest-httpx includes a
configuration option, assert_all_responses_were_requested, which is enabled by
default. This means that if a test registers mock responses (via add_response or
add_callback) that are not subsequently requested by the SUT during the test's
execution, the test will fail at the teardown phase. This feature is a proactive
error detection mechanism. It helps catch scenarios where the SUT is not
behaving as expected (e.g., failing to make an anticipated API call) or where
tests have become outdated due to changes in the SUT's behavior. If a mock is
defined but never used, it could indicate dead code in the SUT or a
misunderstanding in the test's assumptions about the SUT's interactions. This
default behavior promotes test suite health and accuracy. This option can be
turned off if necessary (e.g., by setting assert_all_responses_were_requested =
False in pytest.ini or via a marker, though the exact method needs to be
confirmed from detailed documentation), which might be useful for tests where
some mocks are intentionally optional or provide broader coverage than a
specific test path exercises. The combination of get_requests() for inspecting
actual calls and the default assert_all_responses_were_requested=True provides a
robust two-way assertion mechanism. Not only does the SUT receive correctly
mocked responses (inputs), but the test also verifies that the SUT made all the
expected requests (outputs) and that the test's definition of expected
interactions is complete. This creates a tighter feedback loop and leads to
higher confidence in the tested behavior. Additionally, pytest-httpx allows
certain hosts to bypass mocking entirely through a configuration like
non_mocked_hosts. This is useful for hybrid testing scenarios where some
requests (e.g., to localhost or a known internal staging service) should proceed
as real network calls, while others are mocked. The specific mechanism for
configuring non_mocked_hosts (e.g., pytest.ini, fixture configuration) should be
consulted in the official documentation. 8. Testing Asynchronous Code with
httpx.AsyncClient A key strength of httpx is its native support for asynchronous
operations using async and await, primarily through the httpx.AsyncClient.
pytest-httpx provides seamless and unified support for testing such asynchronous
code. To test asynchronous functions that use httpx.AsyncClient, the test
functions themselves must be defined as async def and should be decorated with
@pytest.mark.asyncio. This decorator, typically provided by the pytest-asyncio
plugin (a common dependency or companion for async testing with pytest), ensures
the test runs within an asyncio event loop. The httpx_mock fixture functions
identically in these asynchronous tests, intercepting calls made by
httpx.AsyncClient. import pytest import httpx from pytest_httpx import HTTPXMock

@pytest.mark.asyncio async def test_async_client_interaction_example(httpx_mock:
HTTPXMock): mock_url = "<https://async.service.example.com/data>"
mock_response_json = {"key": "async_value_example"}

```python
httpx_mock.add_response(url=mock_url, json=mock_response_json)

# Code under test using httpx.AsyncClient
async with httpx.AsyncClient() as client:
    response = await client.get(mock_url)

assert response.status_code == 200
assert response.json() == mock_response_json

# Verify the request was made as expected
requests_made = httpx_mock.get_requests()
assert len(requests_made) == 1
assert str(requests_made.url) == mock_url
assert requests_made.method == "GET"
```

When using callbacks with httpx_mock.add_callback() in asynchronous tests, the
callback functions themselves can also be defined as async def. pytest-httpx
will correctly await these asynchronous callbacks if they are provided for an
asynchronous client interaction. import pytest import httpx from pytest_httpx
import HTTPXMock

@pytest.mark.asyncio async def test_async_callback_example(httpx_mock:
HTTPXMock): async def my_async_callback(request: httpx.Request) ->
httpx.Response: # Simulate some async work, e.g., an internal async lookup or
delay # await asyncio.sleep(0.01) return httpx.Response(200, text="Response from
async callback")

```python
httpx_mock.add_callback(my_async_callback, url="https://async.service.example.com/dynamic_resource")

async with httpx.AsyncClient() as client:
    response = await client.get("https://async.service.example.com/dynamic_resource")

assert response.text == "Response from async callback"
```

It is crucial that the code under test correctly uses await for all AsyncClient
methods that are awaitable. Common pitfalls in asynchronous Python, such as
forgetting to await an asynchronous call, are general programming errors but can
manifest during testing when expected mocked interactions fail to occur or tests
hang. The efficient use of httpx in async contexts, for example, by gathering
multiple requests concurrently rather than awaiting them sequentially in a loop,
is also an important consideration for application performance, though
pytest-httpx primarily focuses on mocking the individual interactions. The
transparent support for httpx.AsyncClient by the same httpx_mock fixture,
without necessitating a different fixture or a significantly altered setup API
compared to synchronous testing, is a significant design advantage. This unifies
the testing experience for applications that use httpx for both synchronous and
asynchronous HTTP calls. This consistency simplifies test development and
maintenance, especially in codebases that progressively adopt asynchronous
patterns or need to support both execution models. The httpx_mock fixture's
compatibility with @pytest.mark.asyncio indicates that it is designed to be
async-aware, correctly managing its patching mechanisms and state within the
asyncio event loop context provided by pytest-asyncio. 9. Testing Edge Cases and
Error Handling Robust applications must gracefully handle various network issues
and error responses from external services. pytest-httpx provides the tools to
simulate these conditions, enabling thorough testing of an application's error
handling logic and resilience. 9.1. Simulating httpx Exceptions The most
flexible way to simulate httpx exceptions (such as timeouts or connection
errors) is by using httpx_mock.add_callback() to register a callback function
that raises the desired exception. httpx defines a hierarchy of exceptions for
different error conditions , including:

- httpx.TimeoutException (and its more specific variants like
  httpx.ConnectTimeout, httpx.ReadTimeout, httpx.WriteTimeout,
  httpx.PoolTimeout)
- httpx.ConnectError
- httpx.NetworkError (base class for network-related issues)
- httpx.ReadError, httpx.WriteError
- httpx.TooManyRedirects
- httpx.HTTPStatusError (typically raised by response.raise_for_status()) Here's
  an example of simulating an httpx.ConnectError: import pytest import httpx
  from pytest_httpx import HTTPXMock

def raise_connect_error_callback(request: httpx.Request, # type:
ignore[no-untyped-def] \*\*kwargs) -> httpx.Response: # type:
ignore[no-untyped-def] raise httpx.ConnectError("Mocked connection establishment
failed", request=request)

@pytest.mark.asyncio # This test could also be synchronous async def
test_application_handles_connect_error(httpx_mock: HTTPXMock): service_url =
"<https://unreachable.internal.service.com/api/data>" httpx_mock.add_callback(
raise_connect_error_callback, url=service_url )

```python
# Assume 'fetch_data_from_service' is a function in the SUT
# that calls the service_url and has error handling for httpx.ConnectError
with pytest.raises(httpx.ConnectError, match="Mocked connection establishment failed"):
    # Example of a direct call for demonstration; in practice, this would be SUT code
    async with httpx.AsyncClient() as client:
         await client.get(service_url)
```

. The ability to raise exceptions directly from callbacks is particularly
powerful because it allows the simulation of transport-level errors (like
httpx.ConnectError or httpx.TimeoutException). These errors occur before an HTTP
response status code is even received from a server. This is essential for
testing an application's lower-level network resilience, which cannot be
achieved merely by setting an error status code on a mock response. 9.2.
Simulating Non-2xx HTTP Status Codes To test how an application handles HTTP
error statuses (e.g., 400 Bad Request, 401 Unauthorized, 403 Forbidden, 404 Not
Found, 500 Internal Server Error, 503 Service Unavailable), the status_code
parameter in httpx_mock.add_response() can be used. The SUT can then be
inspected to ensure it processes these status codes correctly, for example, by
checking response.status_code or by observing its behavior when
response.raise_for_status() is called (which would raise an
httpx.HTTPStatusError). def test_application_handles_403_forbidden(httpx_mock:
HTTPXMock): forbidden_resource_url =
"<https://api.example.com/restricted_resource>"
httpx_mock.add_response(url=forbidden_resource_url, status_code=403,
json={"detail": "Access denied"})

```python
# SUT makes a request to forbidden_resource_url
response = httpx.get(forbidden_resource_url) # Simulating SUT call

assert response.status_code == 403
assert response.json()["detail"] == "Access denied"

# If the SUT is expected to call response.raise_for_status():
with pytest.raises(httpx.HTTPStatusError) as exc_info:
    response.raise_for_status()
assert exc_info.value.response.status_code == 403
# Further assertions can be made on how the SUT propagates or handles this exception
```

9.3. Testing Retry Logic and Timeout Handling Applications often implement retry
mechanisms for transient errors or have specific timeout configurations.
pytest-httpx can facilitate testing these:

- Retry Logic: To test retries, one can use a sequence of add_response calls or
  a stateful callback. The initial call(s) can be configured to return an error
  (e.g., a 503 status code or raise httpx.ConnectTimeout), followed by a
  successful response. The test would then verify that the SUT indeed retries
  the operation and eventually succeeds or exhausts its retry attempts.
- Timeout Handling: To test timeout handling, a callback can be designed to
  raise an httpx.TimeoutException (or one of its specific variants). The test
  should then assert that the SUT handles this timeout gracefully, perhaps by
  logging an error, returning a default value, or propagating a custom
  application-level exception. httpx itself provides built-in support for
  timeouts and retries. pytest-httpx is instrumental in testing how an
  application configures these httpx features or how it reacts to them, as well
  as testing any custom retry or timeout logic implemented within the
  application itself. Simulating exceptions and error statuses with pytest-httpx
  is not merely about verifying if a specific error is caught, but critically,
  how it is handled by the application. This enables comprehensive testing of
  the application's networking layer's resilience and robustness, ensuring that
  fallback mechanisms, retry strategies, logging, and user-facing error
  reporting function as intended, which is paramount for production stability. A
  table summarizing common httpx exceptions and their simulation with
  pytest-httpx can be a valuable reference: | httpx Exception | Description
  (from ) | Simulation Method with pytest-httpx | |---|---|---| |
  httpx.ConnectError | Failed to establish a connection. | add_callback raising
  httpx.ConnectError(request=request,...) | | httpx.ReadTimeout | Timed out
  while receiving data from the host. | add_callback raising
  httpx.ReadTimeout(request=request,...) | | httpx.WriteTimeout | Timed out
  while sending data to the host. | add_callback raising
  httpx.WriteTimeout(request=request,...) | | httpx.PoolTimeout | Timed out
  waiting to acquire a connection from the pool. | add_callback raising
  httpx.PoolTimeout(request=request,...) | | httpx.TooManyRedirects | Exceeded
  maximum redirect limit. | add_callback raising
  httpx.TooManyRedirects(request=request,...) | | httpx.HTTPStatusError |
  Response had an error HTTP status (4xx or 5xx). |
  add_response(status_code=4xx_or_5xx). SUT calls response.raise_for_status() to
  trigger exception. | This mapping helps ensure that tests cover a wide
  spectrum of potential failure scenarios.

## 10. Working with Custom httpx Transports httpx offers an advanced feature

```python
allowing users to customize how requests are sent by providing a custom
transport class to an httpx.Client instance via the transport argument.
Standard transports include HTTPTransport (the default for network
requests), WSGITransport (for testing WSGI applications like Flask directly
in-process), and ASGITransport (for testing ASGI applications like FastAPI
in-process). Users can also create their own transport classes by
subclassing httpx.BaseTransport (for synchronous clients) or
httpx.AsyncBaseTransport (for asynchronous clients) to implement specialized
request handling logic. When considering how pytest-httpx interacts with
clients using custom transports, it's important to understand the mocking
mechanism. pytest-httpx generally operates by patching httpx's request
dispatching at a level that intercepts requests before they would be handled
by a transport designed for actual network communication. The primary goal
of pytest-httpx is to prevent real network calls and substitute mock
responses. If the objective is to test the internal logic of a custom
transport itself, pytest-httpx might not be the most direct tool. Instead,
httpx provides its own httpx.MockTransport class. This class, part of httpx
core, accepts a handler function that maps incoming httpx.Request objects to
predetermined httpx.Response objects. import httpx import os # For the
example from httpx docs
```

def my_mock_handler(request: httpx.Request) -> httpx.Response: # Example: return
a specific response based on request URL or method if request.url.path ==
"/special_endpoint": return httpx.Response(200, json={"message": "Handled by

```python
if os.environ.get("TESTING_WITH_MOCK_TRANSPORT", "").upper() == "TRUE":
    transport_to_use = httpx.MockTransport(my_mock_handler)
else:
    transport_to_use = httpx.HTTPTransport()

client_with_custom_or_mock_transport = httpx.Client(transport=transport_to_use)
# Calls made with client_with_custom_or_mock_transport will use the specified transport
```

httpx.MockTransport offers a foundational, direct way to control request
dispatching at the transport level for testing purposes. pytest-httpx, on the
other hand, is a higher-level pytest plugin providing a more feature-rich and
pytest-idiomatic API for general httpx call mocking within a test suite. The
httpx documentation itself suggests looking at pytest-httpx or RESPX for "more
advanced use-cases" beyond what httpx.MockTransport offers directly , indicating
that pytest-httpx is generally preferred for application-level test mocking in a
pytest environment. Strategies for testing applications that use custom httpx
transports depend on what is being tested:

- Testing an application that uses a client with a custom transport, where the
  transport makes external HTTP calls you want to mock: pytest-httpx should
  intercept these calls as usual. The fact that a custom transport is involved
  is often an implementation detail from pytest-httpx's perspective, as long as
  the calls eventually attempt to go through httpx's standard dispatch
  mechanisms that pytest-httpx patches. For example, if an OpenAI client is
  configured with a custom httpx.Client , pytest-httpx would mock the calls made
  by that underlying httpx.Client.
- Testing an application that uses WSGITransport or ASGITransport: These
  transports are designed for in-process testing of web applications (e.g.,
  Flask, FastAPI). In such cases, pytest-httpx is typically not used to mock
  these interactions, as the goal is to test the actual behavior of the
  WSGI/ASGI application itself.
- Testing the internal logic within a custom transport: This is a more nuanced
  scenario. If the custom transport wraps another transport, one might mock the
  handle_request or handle_async_request methods of the nested transport using
  standard Python mocking tools (like unittest.mock or pytest-mock).
  Alternatively, direct input/output testing of the custom transport's methods
  might be appropriate. pytest-httpx is primarily designed for mocking the
  outcome of calls like httpx.Client(...).get(...), not necessarily the
  intricate internal workings of every possible custom transport implementation,
  especially if those transports don't result in standard HTTP requests that
  pytest-httpx can intercept. In essence, a layered approach to testing is often
  beneficial. httpx.MockTransport provides a basic tool for controlling request
  dispatching at the transport level. pytest-httpx builds upon such concepts (or
  offers an alternative) with a comprehensive, pytest-centric API suitable for
  most application testing needs. When custom transports are involved, the
  crucial question is what component or interaction is the target of the mock.
  If it's the apparent external HTTP interactions that the custom transport
  ultimately facilitates (or attempts to facilitate), pytest-httpx is generally
  the appropriate tool. If the custom transport itself is the unit under test,
  or if it communicates via non-HTTP means that pytest-httpx cannot intercept,
  then other unit testing techniques, potentially including direct use of
  httpx.MockTransport or standard Python mocking libraries, would be more
  suitable.

## 11. Testing Streaming Responses Modern web applications often deal with large

```python
data responses or continuous data streams (e.g., file downloads, server-sent
events). httpx supports response streaming to handle such scenarios
efficiently, allowing data to be processed in chunks without loading the
entire response into memory at once. pytest-httpx provides capabilities to
mock these streaming responses, enabling tests to verify how an application
consumes and processes streamed data. To mock a streaming response, the
stream parameter is used within httpx_mock.add_response(). This parameter
should be an instance of httpx.SyncByteStream for synchronous clients or
httpx.AsyncByteStream for asynchronous clients. pytest-httpx includes a
convenient utility, pytest_httpx.IteratorStream, which can create a byte
stream from an iterable (like a list of byte strings or a generator function
yielding byte strings). This significantly simplifies the process of
defining mock streams, as developers do not need to implement the
SyncByteStream or AsyncByteStream interface manually. For synchronous
streaming: import httpx import pytest # Only if using pytest features like
markers, not strictly needed for this example from pytest_httpx import
HTTPXMock, IteratorStream
```

def test_synchronous_streaming_response_mock(httpx_mock: HTTPXMock): data_chunks
\=

```python
httpx_mock.add_response(
    url="https://example.com/large_data_stream",
    stream=IteratorStream(data_chunks) # Create a stream from the list of byte chunks
)

full_content_received = b""
with httpx.Client() as client:
    # SUT uses client.stream() to get a streaming response
    with client.stream("GET", "https://example.com/large_data_stream") as response:
        assert response.status_code == 200 # Check status before streaming
        # SUT iterates over the response content
        for chunk in response.iter_bytes():
            full_content_received += chunk
        
assert full_content_received == b"".join(data_chunks)
```

The same principle applies to testing asynchronous streaming with
httpx.AsyncClient. The test function would be async def and marked with
@pytest.mark.asyncio. The SUT would use async for chunk in
response.aiter_bytes(): to consume the stream. IteratorStream can also wrap
asynchronous iterables or generators for use with AsyncByteStream. import httpx
import pytest from pytest_httpx import HTTPXMock, IteratorStream

@pytest.mark.asyncio async def
test_asynchronous_streaming_response_mock(httpx_mock: HTTPXMock): async def
generate_async_data_chunks(): yield b"Async data chunk 1. " # await
asyncio.sleep(0.01) # Optionally simulate delay between chunks yield b"Async
data chunk 2. " yield b"Async data chunk 3, the end."

```python
httpx_mock.add_response(
    url="https://example.com/asynchronous_stream_source",
    # IteratorStream can wrap async iterables for async responses
    stream=IteratorStream(generate_async_data_chunks())
)

full_content_received = b""
async with httpx.AsyncClient() as client:
    async with client.stream("GET", "https://example.com/asynchronous_stream_source") as response:
        assert response.status_code == 200
        async for chunk in response.aiter_bytes():
            full_content_received += chunk
            
expected_content = b"Async data chunk 1. Async data chunk 2. Async data chunk 3, the end."
assert full_content_received == expected_content
```

When verifying streamed content, tests can iterate over response.iter_bytes()
(for synchronous streams) or response.aiter_bytes() (for asynchronous streams)
and accumulate the content for a final assertion, or process/assert each chunk
individually as it arrives. This allows testing for the integrity of the
complete data, the number of chunks, the content of specific chunks, or how the
application behaves as it consumes the stream incrementally. Testing streaming
responses is crucial not only for verifying data integrity but also for
assessing how an application handles aspects like partial data reception,
backpressure (if applicable in the streaming mechanism), and resource management
when dealing with potentially very large or continuous data flows. pytest-httpx,
through its stream parameter and IteratorStream utility, provides the necessary
tools to simulate these varied streaming scenarios and validate the
application's stream processing logic effectively. The provision of
IteratorStream is a notable convenience, lowering the barrier to entry for
testing this advanced httpx feature. 12. Best Practices and Common Patterns
Adopting best practices and common patterns when using pytest-httpx can lead to
more maintainable, readable, and robust test suites.

- Organizing Mock Setups: For mock configurations that are reused across
  multiple tests within a module or even across the entire project, pytest
  fixtures offer an excellent way to encapsulate this logic. These fixtures can
  be defined in individual test files or, for broader use, in conftest.py. A
  fixture can perform the necessary httpx_mock.add_response() or
  httpx_mock.add_callback() calls and can either return the httpx_mock instance
  for further customization or simply set up the mocks.

```python
import pytest
from pytest_httpx import HTTPXMock

@pytest.fixture
def mock_successful_user_retrieval(httpx_mock: HTTPXMock):
    """Mocks a successful GET request to /api/users/{user_id}."""
    httpx_mock.add_response(
        method="GET",
        url=re.compile(r"https://api.example.com/users/\d+"),
        json={"id": 123, "name": "Mocked User", "email": "user@example.com"},
    )
    # Optionally, return httpx_mock if tests need customization
    # return httpx_mock
```

In a test file, e.g., test_user_module.py

```python
def test_fetch_user_details_success(mock_successful_user_retrieval, user_service_instance):
    user = user_service_instance.get_user_by_id(123)
    assert user is not None
    assert user.name == "Mocked User"
```

- Keeping Mocks Specific and Readable: It is advisable to use precise matching
  criteria (URL, method, match_headers, match_json, etc.) for mocks. This
  ensures that a mock only applies to the intended request, preventing
  accidental interception of other requests which could lead to confusing test
  failures or mask issues. Callback functions and any classes used for stateful
  callbacks should be named descriptively. Complex mock setups benefit from
  comments explaining their purpose and behavior.
- Avoiding Over-Mocking: While pytest-httpx makes mocking easy, it's important
  to mock only at the necessary boundaries, typically between the system under
  test and the external HTTP service it communicates with. Over-mocking, such as
  mocking internal application logic or creating mocks that are too simplistic,
  can lead to tests that pass even if the application is functionally broken in
  a real environment ("testing the mocks themselves") or tests that are
  excessively coupled to implementation details. The focus should be on
  functional tests for code paths involving HTTP requests, using pytest-httpx to
  simulate the external world's boundary faithfully, rather than creating an
  artificial internal environment.
- Following httpx Best Practices in Application Code: The application code being
  tested should ideally follow httpx best practices, such as using httpx.Client
  as a context manager (with httpx.Client() as client:) for multiple requests to
  the same host. This enables connection pooling and improves efficiency. Tests
  for such code will naturally exercise these patterns, and pytest-httpx will
  mock the requests made by these client instances.
- Idempotency of Tests: Tests should be independent and produce the same results
  regardless of the order in which they are run. pytest-httpx inherently
  supports this by ensuring that the httpx_mock fixture's state (i.e.,
  registered mocks) is isolated to each test function. Mocks added in one test
  do not leak into or affect other tests.
- Test One Behavior Per Test Function: Each test function should ideally focus
  on verifying a single behavior or scenario of the HTTP interaction. This
  approach, aligned with the Single Responsibility Principle (SRP) for tests,
  makes individual tests easier to understand, debug when they fail, and
  maintain over time. By adhering to these practices, developers can leverage
  the full potential of pytest-httpx to build comprehensive and reliable test
  suites for their httpx-based applications.

## 13. Troubleshooting Common Issues and Pitfalls Even with a well-designed library

- Configuration Mistakes:
  - Missing httpx_mock fixture: Forgetting to include httpx_mock as an argument
    to the test function means mocking will not be active.
  - Incorrect matching criteria: This is a frequent cause of mock failures. If
    the actual request made by the SUT does not precisely match the criteria
    defined in add_response or add_callback, pytest-httpx will not find a
    corresponding mock. This often results in an error like
    pytest_httpx.exceptions.HTTPXMockError: No matching response for request...
    (the exact exception message should be verified from library usage). Common
    mistakes include:
    - Mismatched URL (e.g., http vs https, presence or absence of a trailing
      slash, subtle typos).
    - Incorrect method string (e.g., "GET" vs "POST").
    - Discrepancies in match_json, match_content, or match_headers (e.g.,
      different payload structure, encoding issues, case sensitivity in header
      values if not handled by the SUT).
- Debugging Failing Tests:
  - Inspect actual requests: The most valuable tool for debugging mock
    mismatches is httpx_mock.get_requests(). This method returns a list of
    httpx.Request objects that were actually made by the SUT and intercepted.
    Print the attributes of these request objects (e.g., request.url,
    request.method, request.headers, request.read() for content) and compare
    them meticulously against the mock's defined expectations. This process
    often reveals the subtle differences causing the mismatch.
  - Simplify and incrementally specify: If a complex mock isn't matching,
    temporarily broaden its criteria (e.g., remove match_headers or match_json,
    match only on URL). If the simpler mock matches, incrementally add back the
    specific matchers one by one to pinpoint which criterion is failing.
  - Use pytest -s: This pytest option allows print() statements within test
    functions or callbacks to be displayed in the console output, which can be
    helpful for debugging.
  - Examine failure messages: pytest-httpx error messages, particularly
    HTTPXMockError, often provide context about the request that failed to find
    a match, which can guide debugging.
- Potential Conflicts or Hangs:
  - Name conflicts: An environmental issue can arise from a name collision
    between the httpx Python library and a command-line tool also named httpx
    (e.g., by Project Discovery) if both are in the system's PATH and invoked
    ambiguously from scripts. This is not specific to pytest-httpx but can
    affect test environments that use such tools.
  - Hangs in asynchronous tests: These can be particularly tricky. Common causes
    include:
    - Un-awaited asynchronous calls in the SUT or the test itself.
    - Issues with the asyncio event loop configuration (ensure pytest-asyncio is
      correctly set up).
    - Problems in the SUT's asynchronous logic, such as deadlocks or unhandled
      exceptions in tasks. A reported issue with httpx-ws (a related library for
      WebSockets) highlighted that tests could hang if a WebSocket endpoint
      didn't properly accept or close a connection, underscoring the need for
      correct asynchronous resource management in the SUT.
  - Python Version Incompatibility: Ensure the Python version used meets the
    minimum requirements for both httpx (Python 3.8+ ) and pytest-httpx (Python
    3.9+ ). Using incompatible versions can lead to unexpected errors or
    behavior.
- Understanding pytest-httpx Error Messages:
  - The primary error, often an HTTPXMockError or similar, typically signifies
    either that no registered response matched an outgoing request, or, if
    assert_all_responses_were_requested is true (the default), that not all
    registered responses were actually requested by the SUT during the test.
- Forgetting await in Asynchronous Code: This is a general Python asynchronous
  programming pitfall but is highly relevant when testing code that uses
  httpx.AsyncClient. If an await is missed on an asynchronous httpx call, the
  call might not execute as expected, leading to mocked interactions not
  occurring or tests behaving unpredictably.
- Order of Mock Registration: Recall that pytest-httpx selects the first
  registered, unused mock that matches an incoming request. If multiple generic
  mocks are registered before more specific ones, the generic mocks might be
  consumed unexpectedly, leading to the specific mocks not being hit as
  intended. It's generally better to register more specific mocks first or
  ensure that matching criteria are distinct enough. Many troubleshooting
  scenarios ultimately boil down to a discrepancy between the developer's mental
  model of the HTTP request their code should be making, and the request it
  actually makes. pytest-httpx, especially through httpx_mock.get_requests(),
  serves as a crucial diagnostic tool to verify and refine this mental model,
  leading to more accurate tests and a better understanding of the SUT's
  behavior. Furthermore, the default behavior of
  assert_all_responses_were_requested=True acts as a proactive safeguard,
  helping to detect "dead" or outdated mocks and changes in application behavior
  where expected requests are no longer made, thus preventing tests from
  becoming stale or providing a false sense of security.

## 14. Migrating from Other Mocking Libraries Developers transitioning to httpx and

pytest-httpx may have experience with mocking libraries for older HTTP clients
like requests or aiohttp. pytest-httpx documentation acknowledges this by
providing direct comparisons, which can significantly ease the The responses
library is a popular choice for mocking HTTP requests made by the requests
library. pytest-httpx shares conceptual similarities but is tailored for httpx.
Key API mappings include : | Feature | responses Syntax | pytest-httpx Syntax
(httpx_mock) | |---|---|---| | Add a response | responses.add(...) |
add_response(...) | | Add a callback | responses.add_callback(...) |
add_callback(...) | | Retrieve requests made | responses.calls (list of Call
objects) | get_requests() (list of httpx.Request objects) | | Specify HTTP
method | method=responses.GET (constants) | method="GET" (string) | | Response
body (bytes) | body=b"sample" | content=b"sample" | | Response body (string) |
body="sample" | text="sample" | | Response body (JSON) | json={"key": "value"} |
json={"key": "value"} | | Response status code | status=201 | status_code=201 |
| Response headers | adding_headers={"name": "value"} | headers={"name":
"value"} | | Content-Type header | content_type="application/custom" |
headers={"content-type": "application/custom"} | | Match full query string |
match_querystring=True (influences URL matching) | URL matching (url param)
always includes query params. | 14.2. Comparison with aioresponses (for aiohttp
library) aioresponses serves a similar purpose for the aiohttp asynchronous HTTP
client. The mapping to pytest-httpx is also straightforward : | Feature |
aioresponses Syntax | pytest-httpx Syntax (httpx_mock) | |---|---|---| | Add a
response (for specific method) | aioresponses_instance.get(url,...) |
add_response(method="GET", url=url,...) | | Add a callback (for specific method)
| aioresponses_instance.get(url, callback=my_callback,...) |
add_callback(my_callback, method="GET", url=url,...) | 14.3. Key Differences and
Advantages The primary difference is the target library: pytest-httpx is
exclusively for httpx. Its design leverages pytest's fixture system for seamless
integration. The request matching capabilities in pytest-httpx are extensive,
covering URL (with regex), method, headers, various body types (JSON with
partial matching, content, data, files), proxy URLs, and httpx extensions. A
significant advantage of the httpx and pytest-httpx ecosystem is the unified
handling of synchronous and asynchronous code. httpx itself provides both Client
and AsyncClient with largely symmetrical APIs. pytest-httpx mirrors this by
using the single httpx_mock fixture to mock calls from both client types,
employing the same add_response and add_callback API. This contrasts with older
ecosystems where separate libraries (e.g., responses for sync requests,
aioresponses for async aiohttp) were often needed, leading to different mocking
paradigms for sync and async code. This unification simplifies development and
testing, especially for projects that utilize modern asynchronous Python or are
transitioning towards it. The explicit comparison tables in the pytest-httpx
documentation demonstrate a pragmatic approach to user adoption, recognizing
that developers often bring experience from these established tools and aiming
to lower the learning curve.

## 15. Conclusion and Further Resources pytest-httpx stands out as an essential

benefits are numerous:

- Seamless pytest Integration: It leverages pytest's powerful fixture system,
  making mock setup and teardown transparent and straightforward.
- Unified Sync/Async Mocking: A single, consistent API (httpx_mock) caters to
  both synchronous (httpx.Client) and asynchronous (httpx.AsyncClient) code,
  mirroring httpx's own design philosophy.
- Rich Request Matching: Extensive criteria allow for precise targeting of
  requests to be mocked, ensuring tests are robust and specific.
- Flexible Response Definition: Responses can be static (JSON, text, bytes,
  custom headers, status codes) or dynamically generated via callbacks,
  including support for streaming responses.
- Comprehensive Error Simulation: Enables thorough testing of application
  resilience by simulating various httpx exceptions and HTTP error statuses. The
  strength of pytest-httpx is amplified by its synergy with both httpx, a client
  built for modern HTTP interactions (including HTTP/2 and async), and pytest, a
  framework that promotes modern, efficient testing practices. This combination
  empowers developers to write high-quality, reliable tests for complex
  network-dependent applications with greater ease and confidence. For further
  information and detailed API references, the following official documentation
  sources are recommended:
- pytest-httpx Documentation:
  - PyPI Project Page: (Provides installation instructions, basic usage, and
    often links to more detailed docs)
  - Official Documentation (Colin Bounouar's GitHub pages): (Comprehensive
    guide, API details, advanced features)
- httpx Documentation:
  - Official Website: (General information, features)
  - Quickstart Guide:
  - Advanced Usage (Transports, etc.):
  - Exceptions Hierarchy:
- pytest Documentation:
  - Official Website: (Fixtures, best practices, general pytest usage)
    Developers are encouraged to explore these resources, experiment with
    pytest-httpx's features, and consider contributing to these open-source
    projects to further enhance the Python testing ecosystem.
