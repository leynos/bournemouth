# Design Document: Surprise-Aware Knowledge Graph & RAG Chatbot System

## Functional Requirements

**Chat API Service (`chat-api`):** A stateless Python 3.13 web service (Falcon
framework) that handles user chat requests and performs Retrieval-Augmented
Generation (RAG) to incorporate knowledge graph data into LLM prompts.

- **Authentication & Authorization:** Accepts requests only from authenticated
  users via Google Sign-In (OIDC). The client must provide a valid Google OIDC
  ID token (e.g. in an `Authorization: Bearer <ID_TOKEN>` header). The service
  validates the token’s signature and expiration using Google's public keys and
  extracts the user's unique identifier (Google `sub` claim). All requests are
  thus tied to a verified Google user identity.

- **User Request Handling:** Exposes a RESTful endpoint (e.g. **POST** `/chat`)
  to receive chat messages. The request contains the user’s prompt (and
  optionally recent conversation context if needed for continuity). The chat-api
  does **not** maintain persistent session state; any conversation history must
  be provided by the client or retrieved ephemerally (to keep the service
  stateless aside from auth). Each request is handled in isolation, using the ID
  token to identify the user and authorize access.

- **RAG Pipeline:** Upon receiving a user message, the chat-api performs the RAG
  process in real-time (targeting sub-second latency overhead):

  1. **Embed the Query:** The user’s prompt is converted to an embedding vector
     (using a fast embedding model or API). This could leverage an OpenRouter
     embedding endpoint or a local embedding model for speed.
  2. **Retrieve Knowledge Graph Context:** Using the embedding, the service
     performs a vector similarity search against the knowledge graph’s content.
     Relevant facts/nodes are retrieved by semantic similarity. Additionally,
     Cypher queries are executed on the Neo4j knowledge graph to fetch related
     facts (e.g. nodes or subgraphs matching key entities or keywords in the
     query). The retrieval may combine vector search (for semantic matches) with
     structured Cypher queries (for precise matches or graph neighborhood
     expansion). This ensures the most relevant knowledge graph facts for the
     query are identified.
  3. **Isolated Multi-Tenant Knowledge:** The Cypher queries always filter by
     the user’s context, so that only the requesting user’s data (and any
     permitted public/shared data) is retrieved. Each knowledge graph
     node/relationship is tagged with the owning user’s ID (or a tenant
     identifier). The query adds conditions like
     `WHERE node.user_id = $currentUser` (or checks a `tenantId` property) to
     enforce isolation. This gives each user an isolated view of the shared
     Neo4j graph – users cannot retrieve or see another user’s facts.
  4. **Augment Prompt with Facts:** The chat-api then constructs an augmented
     prompt for the LLM. For example, it may prepend a system message or context
     section that includes the retrieved knowledge graph facts (formatted in
     natural language or as a list of relevant facts). This follows the RAG
     approach of supplementing the user’s query with external knowledge,
     ensuring the LLM has the necessary context to answer accurately.
  5. **LLM Inference via OpenRouter:** The service calls the OpenRouter API to
     get a completion for the augmented prompt. OpenRouter provides a unified
     API for various large language models, and our service uses it with
     OAuth-based user tokens. The user must have connected their OpenRouter
     account or provided an API token (“Bring Your Own Key”). The chat-api
     includes the user’s OpenRouter API key in the request to OpenRouter’s
     completion endpoint (as an `Authorization: Bearer <API_KEY>` header).
     OpenRouter then routes the prompt to the chosen LLM (e.g. GPT-4 or other)
     and returns the model’s response. The chat-api should handle this HTTP call
     asynchronously or with proper timeouts. If the OpenRouter call succeeds,
     the assistant’s answer (the LLM’s generated message) is obtained.
  6. **Send Response:** The chat-api immediately returns the LLM’s answer back
     to the user in the HTTP response. The client sees the chatbot’s answer with
     minimal delay beyond the model’s own generation time. The API’s response
     format is JSON (e.g. `{ "answer": "...generated text..." }`), potentially
     including metadata like used sources or tokens (if needed, though minimal
     viable product (MVP) might just return the text).

- **Novelty Detection (“Surprise” Identification):** The chat-api analyzes each
  user message **after** obtaining the LLM response (or in parallel, to save
  time) to detect any novel information not already in the knowledge graph:

  - It uses simple **Named Entity Recognition (NER)** on the user’s prompt (and
    possibly the LLM answer if we consider new facts may appear there, though
    typically we trust user inputs more). If the user mentions entities (people,
    places, items, etc.) that are not currently represented in the knowledge
    graph (as determined by a quick lookup or query by name/label in Neo4j),
    those entities are flagged as new.
  - It may also use basic **Relation Extraction (RE)** or heuristics to identify
    relationships stated in the user’s input. For example, if the user says
    “**Alice** is Bob’s sister,” the system would identify entities "Alice" and
    "Bob" and the relationship "sister". If such a relation (Alice -> sister ->
    Bob) is not in the KG, that’s a novel fact.
  - This novelty detection is done *quickly* using local NLP (e.g. spaCy or a
    lightweight ML model) to avoid slowing the response. The chat-api does
    **not** update the KG itself (to remain responsive); instead it delegates
    this to the background worker.
  - For any new entity or fact found, the chat-api creates a **Celery task**
    (asynchronous job) containing the details (e.g. the raw text or extracted
    candidates, plus the user’s ID) and enqueues it to a message broker (Redis).
    This enqueuing is non-blocking and happens after the main response is sent,
    so the user isn’t kept waiting for knowledge base updates.

- **Statelessness:** The chat-api service itself holds no long-term state
  between requests (no session storage of conversations). It relies solely on
  the input (which carries context or tokens) and external systems (the
  knowledge graph and user’s data stored in DB). This stateless design allows
  horizontal scaling and easy deployment on Kubernetes. Ephemeral data like the
  current conversation turn or a short-lived cache of recent interactions may
  reside in memory per request, but nothing is persisted in the chat-api layer.
  Logging of requests can be done to an audit store (PostgreSQL) but that does
  not affect handling of each request.

- **Error Handling & Logging:** The chat-api must handle error cases gracefully:

  - If the Google ID token is missing or invalid, respond with HTTP 401
    Unauthorized.
  - If the OpenRouter call fails or times out, respond with an error message
    (and possibly an HTTP 502/503) indicating the model service is unavailable.
    These errors should be propagated in a user-friendly way.
  - If knowledge graph retrieval fails (Neo4j down, etc.), the service can still
    attempt the LLM call without KG context, but should log the incident and
    perhaps notify the user that some knowledge could not be accessed.
  - Each chat request (and its outcome) should be logged to the audit trail in
    Postgres: including timestamp, user ID, perhaps a hashed or truncated
    version of the query for privacy, and any error codes. This ensures
    traceability.

- **OpenRouter Integration:** The chat-api does not host any model locally; it
  relies on OpenRouter’s API for inference. Users must **bring their own
  OpenRouter token**, meaning each user’s LLM usage is tied to their own
  OpenRouter account/credits. The system should facilitate users providing this
  token:

  - Ideally, implement the OAuth PKCE flow with OpenRouter: The front-end can
    redirect the user to OpenRouter’s auth page, and OpenRouter returns an
    authorization code. The chat-api (or front-end) exchanges this code for an
    API key (LLM access token) via OpenRouter’s API. The obtained API key
    represents the user’s permission to use OpenRouter’s LLMs.
  - The chat-api should store this API key securely (associated with the user’s
    account in Postgres) or accept it from the client each time. Storing in the
    backend DB (encrypted at rest) allows the user not to re-enter the key each
    session and enables server-side inclusion of the token in LLM requests.
    According to OpenRouter docs, the API key should be stored securely on the
    client or server – our design opts to keep it in our database (server-side)
    for convenience, encrypted or hashed to protect it.
  - The chat-api uses the stored token when calling OpenRouter. If a user hasn’t
    provided a token, the chat-api should return an error or a message prompting
    them to connect their OpenRouter account (e.g., “LLM token not found; please
    link your OpenRouter API token”). An endpoint (e.g. **POST**
    `/auth/openrouter-token`) can allow the user to submit an API key manually
    as an alternative to the OAuth flow, which the service then saves in
    Postgres via SQLAlchemy.

**Background Worker Service (`worker`):** A Python 3.13 service running Celery,
responsible for processing asynchronous tasks (primarily knowledge graph update
jobs triggered by novel information in chats). It ensures the knowledge graph
and related indices stay updated with new facts, without impacting the latency
of the chat-api.

- **Asynchronous Task Processing:** The worker subscribes to the Celery queue
  (using Redis as the message broker). When a new “update knowledge graph” task
  is enqueued by chat-api, a worker process picks it up. This decoupling allows
  the chat-api to respond immediately while the heavy lifting is done in the
  background. It improves user experience by offloading intensive operations
  (NLP parsing, database writes) outside the request/response cycle.

- **NER and Relation Extraction Pipeline:** For each task, the worker runs an
  NLP pipeline on the text content provided (e.g. the user’s message that
  contained novel info). It performs:

  - **Named Entity Recognition (NER):** Identify any proper nouns or entities in
    the text. Using an NLP library or model (such as spaCy or transformers), tag
    entities and classify their types (Person, Organization, Location, etc.).
    For each recognized entity, check if it already exists in the knowledge
    graph for that user. This is done via a Neo4j Cypher query (e.g.,
    `MATCH (e:Entity {name: "Alice", user_id: <UID>}) RETURN e`). If not found,
    the entity is new.
  - **Relation Extraction (RE):** Analyze the text for relationships between the
    identified entities or between an entity and some attribute. This could be a
    rule-based parse (for simple patterns like “X is Y’s Z”) or a small ML model
    to predict triples. For instance, from “Alice is Bob’s sister,” extract
    subject=Alice, relation=SIBLING_OF (or a generic “sister”), object=Bob. If
    the schema allows, determine a standardized relation type (perhaps from a
    predefined ontology like `:Sibling` relationship). If a clear relation isn’t
    detected, the system might skip or mark the fact for later manual curation.
  - The worker may also use the LLM in a non-user-facing way for extraction
    (prompting OpenRouter for triples from the text), but this is optional and
    might be overkill for MVP. A simpler deterministic approach suffices
    initially.

- **Knowledge Graph Updates:** Using the Neo4j Python driver (e.g., neo4j Bolt
  protocol via `neo4j` library), the worker writes new nodes/edges to the graph:

  - **Entity Nodes:** For each new entity, create a node with an appropriate
    label (e.g., `:Person`, `:Location`, etc., based on NER type, or a generic
    `:Entity` if uncertain). Include properties such as `name`, `user_id`
    (owner), `created_at` timestamp, and provenance info (like
    `source = "user_chat"` or a reference to the chat message ID).
  - **Relationships:** For each new relationship discovered between entities (or
    between an entity and a literal value), create a relationship edge in Neo4j.
    Use a relationship type that fits the semantic (if a standard schema is
    defined) or a generic type (e.g., `:RELATED_TO`) with a `relation_name`
    property describing it (like `"sister"`). Each relationship also carries the
    `user_id` (if we choose to tag relationships for multi-tenancy), a
    timestamp, and source provenance.
  - **Novel Fact Versioning:** If the new information updates or contradicts an
    existing fact, the worker should **version the knowledge** rather than
    simply overwrite. For example, if previously the KG has node `Alice` with
    property `lives_in = London` and the user now says “Alice lives in Paris,”
    the worker can mark the old relationship (Alice -[LIVES_IN]-> London) as
    outdated. This could be done by adding an `ended_at` timestamp to that
    relationship or a boolean `active=false`, and then inserting the new
    relationship Alice -[LIVES_IN]-> Paris with `started_at = now`. This way,
    historical data isn’t lost and the KG is *surprise-aware*, preserving old
    knowledge with context while reflecting new facts. Each such update
    increments the knowledge version implicitly. (In a more advanced setup, one
    could maintain version numbers on nodes or use a separate audit trail in the
    KG, but timestamps suffice for MVP.)
  - The worker ensures all Cypher write operations are done in a transaction,
    and handles potential conflicts (e.g., if two tasks try to create the same
    entity concurrently, it should either merge nodes or ignore duplicates by
    using Cypher’s `MERGE` clause).
  - After updating Neo4j, the worker may also update any auxiliary indexes. In
    particular, if we maintain a vector embedding index of nodes or facts (for
    similarity search), the worker should compute embeddings for the new
    knowledge and upsert them into the index. For example, if a new node “Alice”
    is added with a description, generate its embedding (via an embedding model)
    and store it (perhaps as a property on the node or in an external vector
    store). This ensures the next semantic search can discover “Alice” when
    relevant. (If using Neo4j only, we might store a vector property and utilize
    Neo4j’s index or Graph Data Science library for similarity queries.)

- **Persistent State & Database Operations:** The worker uses PostgreSQL (via
  SQLAlchemy ORM) for any persistent state beyond the graph:

  - **User Metadata:** Manage a table for user accounts, storing at minimum the
    Google user’s unique ID (`sub`), their email or name (if needed for
    display), and their OpenRouter API key (if we choose to store it
    server-side). The OpenRouter token should be encrypted or stored as a hashed
    reference for security. This allows the chat-api to fetch the token when
    needed by querying this table by user ID.
  - **Audit Logs:** Insert records into an audit log table for significant
    events. Each chat message from a user could be logged (user ID, timestamp,
    possibly the prompt text or a content hash, and maybe the response length or
    model used). Each knowledge graph update is definitely logged: recording
    user ID, what was added (e.g. “node:Alice, relation: LIVES_IN Paris”),
    timestamp, and source (which chat message triggered it). These logs aid in
    debugging, compliance, and analyzing system behavior over time. Using
    SQLAlchemy, we define models for these tables and interact in a high-level
    way, making use of transactions and connection pooling.
  - The worker ensures database integrity; for example, if a user is deleted or
    logged out, their data in Postgres and knowledge graph can be cleaned up
    (though user deletion is beyond MVP scope, it’s a consideration).

- **Task Acknowledgment & Retry:** After successfully processing a task, the
  worker should acknowledge the message so it is removed from the Redis queue.
  If processing fails (due to a transient error like database connection
  issues), Celery can be configured to retry the task a certain number of times.
  The tasks should be designed to be **idempotent** or check-before-write, so
  that retries don’t duplicate data. For example, if a task fails after creating
  an entity but before creating a relationship, a retry should detect the entity
  exists and avoid creating a duplicate.

- **Isolation and Multi-user Data:** The worker, like chat-api, must respect
  user data isolation. When writing to Neo4j or Postgres, it always associates
  data with the correct user ID and never mixes data between users. Even though
  all users’ nodes reside in the same Neo4j database, the `user_id` property
  (and possibly labels or separate subgraph per user) is used to segregate their
  knowledge. This extends to embeddings: e.g., a vector index query must filter
  or partition by user if we don’t want cross-user results. (Alternatively, a
  separate index namespace per user could be maintained.)

- **Resource Management:** The worker may perform CPU-heavy operations (NER,
  etc.). It can be scaled horizontally by running multiple Celery worker
  processes/pods to handle load. Each worker process can also run multiple
  threads or processes (Celery concurrency settings) to parallelize tasks. The
  design should account for potentially simultaneous tasks from different users.
  Heavy NLP models can be loaded once per worker to reuse in multiple tasks
  (amortizing load time), but one must watch memory usage. For MVP, using
  efficient libraries and perhaps limiting to smaller models (or calling cloud
  APIs for NER if available) can keep resource use reasonable.

## Non-Functional Requirements

**Performance:**

- **Low Latency RAG:** The chat-api’s goal is to add minimal latency on top of
  the LLM’s response time. The RAG retrieval (embedding + knowledge graph query)
  should typically complete in well under 1 second. To achieve this, use
  optimized methods: pre-compute embeddings for KG facts and store them for fast
  cosine similarity lookup (using an ANN index or indexing features in Neo4j).
  Ensure Neo4j queries (Cypher) are indexed and targeted (e.g., an index on
  `:Entity(name)` for direct lookups, index on `user_id` for filtering) so they
  execute in milliseconds. The Falcon framework is chosen for its efficiency in
  processing HTTP requests; it has a small overhead and can sustain high
  throughput, aligning with the sub-second target.

- **Throughput & Concurrency:** The system should handle multiple concurrent
  users. Chat-api (Falcon) being stateless can be replicated (scale-out) to
  handle many requests in parallel. Each instance should be able to process
  requests concurrently (if using an async server or threads under the hood).
  The OpenRouter calls will be the main bottleneck (as each call might take a
  few seconds depending on the model and prompt length), so we expect to handle
  at least dozens of simultaneous requests by scaling out or by allowing
  concurrent async calls. The Redis + Celery backend can queue a high volume of
  background tasks; the worker can scale to consume tasks quickly if there’s a
  burst of novelty detections.

- **Scalability:** All components are designed to scale horizontally:

  - We can run multiple replicas of chat-api behind a load balancer to
    distribute incoming chats. Because there is no sticky session required (JWT
    auth in each request), any instance can handle any user’s request.
  - For Celery, we can run multiple worker processes (or pods). Celery will
    distribute tasks among them. As usage grows, we simply increase the number
    of workers or the concurrency per worker to throughput more KG update jobs.
  - The databases (Neo4j, Postgres, Redis) can be scaled or upgraded as needed.
    Neo4j can be clustered (with read replicas) if we have heavy read loads from
    many chat-api instances, though initial usage may not require that. Postgres
    can be vertically scaled or use read replicas for offloading heavy read
    scenarios (mostly we have light writes for logs and occasional reads for
    tokens). Redis as a broker typically handles high message rates; if needed,
    a clustered Redis or moving to a more robust broker (like RabbitMQ) is
    possible, but likely not needed in MVP.

- **Availability & Reliability:** The system should be resilient to failures:

  - If a chat-api instance crashes, the load balancer (Kubernetes will handle
    via liveness probes) will stop routing to it; other instances continue
    serving users. New pods can spin up (auto-healing).
  - If the worker crashes mid-task, Celery will detect the lost worker and
    re-queue unacknowledged tasks to another worker instance. This way,
    background jobs are not lost. We may configure at-least-once processing
    semantics for safety (meaning a task might retry, with idempotent handling
    ensuring no duplicate graph entries).
  - Persistent data ensures recovery: If Redis goes down temporarily, queued
    tasks may be lost (unless Redis persistence is enabled). To mitigate that,
    we could enable AOF persistence on Redis or use a more durable broker. In
    practice, the knowledge updates are nice-to-have (the primary chat function
    will still work even if some updates are lost), but for reliability we treat
    the broker as critical. Deploying Redis in a high-availability mode or using
    a managed service with persistence is recommended.
  - The knowledge graph and databases should be backed up periodically.
    Especially Neo4j (which holds user knowledge) and Postgres (user accounts,
    logs) should have backup snapshots or point-in-time recovery to handle data
    loss scenarios.

- **Consistency:** The chat-api and worker operate in eventually consistent
  manner regarding the KG. A new fact from a user will not be available for
  retrieval until the background task completes and updates the KG. This is
  acceptable given the use case (the next user question will include it). We
  should strive to have short delays: the pipeline from detection to KG update
  should typically finish in a few seconds. In rare cases of high load, some
  updates might queue up; as a result, the knowledge graph might lag slightly
  behind the latest conversation. This eventual consistency is a design
  trade-off to ensure user-facing latency stays low. In future, a streaming or
  on-demand update approach could be considered, but for MVP the asynchronous
  model suffices.

- **Security & Privacy:** (Detailed in Security Model below) – Non-functional
  security requirements include protecting user data, using encryption for data
  in transit (TLS for all external calls and between services if possible), and
  safe storage of credentials. The system should also enforce quotas or
  validations to prevent misuse (for example, disallow extremely large prompts
  that could crash the system, or rate-limit the number of requests per minute a
  user can make to avoid spam or runaway costs).

- **Maintainability:**

  - The codebase should be modular: separate modules for the Falcon API (routes,
    authentication, RAG logic) and for Celery tasks (task definitions, NLP
    utility functions, database models). This separation of concerns makes it
    easier to modify one component without affecting the other. For example, one
    could swap out Neo4j for another graph DB in the future by adjusting the
    data access layer in the worker and chat-api (since all KG queries go
    through a well-defined interface or service layer).
  - Using SQLAlchemy for Postgres provides an ORM that improves maintainability
    (models, migrations, and query building are easier to manage than raw SQL).
  - Configuration (like database URLs, API keys, etc.) will be externalized (via
    config files or environment variables), making the application portable
    across environments (development, staging, production). We avoid hard-coding
    values.
  - We should include unit and integration tests for critical pieces: e.g.,
    testing that the chat-api properly constructs prompts and handles auth,
    testing the worker’s NER/RE pipeline on sample texts, etc., to catch issues
    early and facilitate safe refactoring.

- **Observability:**

  - **Logging:** Both chat-api and worker will produce structured logs. Chat-api
    logs each request (with user ID and relevant request info, excluding
    sensitive content ideally) and whether it succeeded. Worker logs each task
    processing outcome (e.g., "Added entity X, relation Y for user U").
    Errors/exceptions are logged with stack traces. These logs will be
    invaluable for debugging and can feed into monitoring systems.
  - **Monitoring:** We should collect metrics such as request latency, number of
    requests, task queue length, task processing time, etc. Using tools like
    Prometheus (with an exporter for Python apps/Celery) or Cloud provider’s
    monitoring, we can set up alerts (e.g., if the queue backlog grows too large
    or if response latency spikes).
  - **Health Checks:** The chat-api will expose a simple health endpoint (e.g.,
    **GET** `/health`) that responds with 200 OK if the service is up (and
    possibly checks connectivity to Redis/Neo4j minimally). This can be used by
    Kubernetes liveness/readiness probes to manage pod health.
  - **Audit & Analytics:** The data in Postgres (audit logs) can be periodically
    analyzed to understand usage patterns: e.g., how many novel facts are added
    per user, which knowledge categories are growing, etc. This is not core to
    functionality but is a useful non-functional aspect for improving the system
    over time.

## API Interfaces and Queue Contracts

**HTTP API Endpoints (chat-api):**

- **POST `/chat`** – *Chat Query Endpoint* **Description:** Accepts a user’s
  chat prompt and returns the assistant’s answer. Performs authentication, RAG
  retrieval, and calls the LLM via OpenRouter. **Request:** JSON body with at
  least a `message` field containing the user’s input. Optionally, it may
  include a `history` field (list of recent messages in `{role, content}`
  format) if the client wants the server to maintain some dialogue context for
  the prompt (the server can include this in the LLM call). If no history is
  provided, the server treats the message as standalone (or the client might
  always send the last N turns to keep the server stateless). The request
  **must** include the user’s Google ID token in the header for auth. If the
  user’s OpenRouter token isn’t stored on the backend, the request could also
  include an `openrouter_api_key` (e.g., in headers or body) – however, the
  preferred design is that the server has it from a prior auth step.
  **Response:** JSON containing the assistant’s reply. For example:

  ```json
  { "answer": "Sure! Here's the information you requested..."}
  ```

  Additional metadata can be included as needed, such as `sources` (if the
  system decides to provide citations from the KG) or `timestamp`. On error,
  returns appropriate HTTP status codes and error messages (e.g., 401 for auth
  failure, 500 for internal errors, 503 for upstream LLM issues).

- **POST `/auth/openrouter-token`** – *Provide OpenRouter Token* **(optional)**
  **Description:** Allows the user to supply their OpenRouter API key/token to
  the system. This is an alternative to the OAuth flow for MVP simplicity.
  **Request:** JSON body with a field `api_key` (the token string obtained from
  OpenRouter). User’s Google ID token must also be provided (to associate the
  API key with the correct user). **Response:** 200 OK on success (after
  verifying the token can be used, e.g., by calling a lightweight OpenRouter
  endpoint or simply storing it). The server stores the token (likely in an
  encrypted form in Postgres linked to the user’s record). After this,
  subsequent `/chat` calls for this user will automatically include the token
  when calling OpenRouter. **Errors:** 401 if user not authenticated. 400 if
  token is missing or invalid format. 502 if OpenRouter verification fails.

- **GET `/auth/openrouter`** – *Initiate OpenRouter OAuth* **(optional
  advanced)** **Description:** Redirects the user to OpenRouter’s OAuth
  authorization URL. This endpoint is used if implementing the full PKCE OAuth
  flow. It would construct the OpenRouter `/auth` URL with the required
  `callback_url` and `code_challenge`, then redirect the user’s browser to that.
  **Behavior:** The user will authenticate on OpenRouter and authorize our app.
  OpenRouter will then redirect back to our specified callback (e.g.,
  `/auth/openrouter/callback?code=...`). (Note: In many implementations, the
  front-end could handle constructing the URL and redirecting directly. We might
  not need a dedicated backend endpoint for this if front-end is doing PKCE.)

- **GET `/auth/openrouter/callback`** – *OpenRouter OAuth Callback* **(optional
  advanced)** **Description:** Handles the redirect from OpenRouter after user
  authorization. It expects a `code` query parameter. **Behavior:** The endpoint
  will read the `code`, verify state if used, then use the OpenRouter API
  (`POST /api/v1/auth/keys`) to exchange the code (plus the PKCE verifier) for
  an API key. On success, it stores the API key in Postgres associated with the
  user (the user’s identity can be retrieved from session or by decoding a JWT
  that was stored during the redirect flow, since the user would have already
  been authed with Google – we may need to tie the OAuth process to an
  authenticated session). After storing, it might redirect the user to a
  front-end page indicating success. **Errors:** If exchange fails, log and
  possibly show an error page or message to the user.

- **GET `/health`** – *Health Check Endpoint* **Description:** Returns a simple
  status (e.g., `{"status": "ok"}`) if the service is running. Optionally, it
  could perform shallow checks like ability to connect to Redis or Postgres.
  Kubernetes liveness/readiness probes will call this to ensure the service is
  healthy.

*(Additional endpoints like user profile or listing knowledge could be
envisioned (e.g., GET `/me` to get user info, or GET `/knowledge` to query the
KG directly), but they are out of scope for the MVP and not required by the
prompt.)*

**Celery Task Interface (worker \<-> queue):**

- **Task Name:** `"kg_update"` (for example). This task is produced by chat-api
  and consumed by the worker. It could be identified by a module path if using
  Celery’s automatic task discovery (e.g., `tasks.update_kg`). We configure
  Celery with a queue (e.g., `knowledge_updates`) that these tasks go into, or
  just use the default queue for simplicity.

- **Task Payload:** The message body should contain all information needed to
  perform the KG update. Proposed structure (as Celery supports args or kwargs):

  - `user_id` (str or int): The unique identifier of the user (e.g., Google
    `sub` or an internal UUID). This tells the worker which user’s domain the
    new knowledge belongs to.
  - `text` (str): The raw text from which to extract knowledge. Typically this
    is the user’s message that was flagged to contain novelty. In some cases, we
    might include the LLM response too if we wanted to extract facts from it
    (less likely in MVP).
  - (Optional) `context` or `meta`: Could include additional metadata like a
    message ID, or the conversation ID, or a flag indicating the type of novelty
    detected. For instance, if chat-api already did a quick check and found a
    specific entity name, it could send that along. However, to keep the worker
    flexible, it’s fine to just send the raw text and let the worker re-derive
    entities.

- **Task Handling:** When the worker receives `"kg_update"`:

  - It logs receipt of the task (with task ID and user_id).

  - Performs NER, RE as described in functional requirements.

  - Interacts with Neo4j: likely using a Neo4j driver instance. This requires
    the Neo4j connection URI and credentials configured in the worker’s
    environment. The worker will translate extracted info into Cypher `CREATE`
    or `MERGE` queries. For example, pseudo-Cypher:

    ```cypher
    MERGE (e1:Person {name: "Alice", user_id: $user}) 
      ON CREATE SET e1.created_at = datetime(), e1.source = "chat";
    MERGE (e2:Person {name: "Bob", user_id: $user}) 
      ON CREATE SET e2.created_at = datetime(), e2.source = "chat";
    MERGE (e1)-[r:SIBLING_OF {user_id: $user}]->(e2) 
      ON CREATE SET r.created_at = datetime(), r.source = "Alice said she is Bob's sister";
    ```

    (The actual Cypher and data model might differ, but the idea is to create
    nodes if new and a relationship if new. If nodes already existed, `MERGE`
    will match them and just create the relation if needed.)

  - Interacts with Postgres via SQLAlchemy: e.g.,

    ```python
    session.add(
        KnowledgeLog(
            user_id=user_id,
            entity="Alice",
            relation="SIBLING_OF",
            object="Bob",
            timestamp=datetime.utcnow(),
            source_text="Alice is Bob's sister.",
        )
    )
    session.commit()
    ```

    And possibly update a Users table if new info about the user profile was
    gleaned (though likely not – most knowledge is separate from user’s own
    profile except they might talk about themselves).

  - No return value is needed for the task (we fire-and-forget). Celery will
    mark it successful or failed. We might use a result backend in Celery (like
    Redis or DB) for debugging, but it’s not strictly required since we aren’t
    waiting for results in the frontend.

- **Error Handling & Retry in Tasks:** If a task throws an exception or cannot
  complete (e.g., Neo4j is unavailable), Celery can automatically retry it after
  a delay. We can configure a max retry count (for example, try 3 times with
  exponential backoff). The task code should be structured so that partial
  failures don’t corrupt data: e.g., if it created some nodes before crashing,
  the MERGE ensures retry won’t duplicate nodes. If a non-recoverable error
  occurs (e.g., bad data causing NER to fail), the task can be marked failed and
  the error recorded. The system can continue to function even if some updates
  fail (the chat service is not directly affected), but those failures should be
  visible to developers (via logs or Celery’s monitoring like Flower) for
  troubleshooting.

- **Queue/Broker Details:** We use **Redis** as the Celery broker (with a
  specific connection URL configured). All `"kg_update"` tasks are published to
  Redis and workers listen on the same. Optionally, for separation, we could
  define multiple Celery queues (e.g., a high-priority queue for critical tasks
  vs. low-priority), but here all knowledge updates are similar priority. The
  Celery configuration (in Python) will specify Redis as broker and may also use
  Redis as the result backend (or simply `ignore_result=True` for tasks if we
  don’t need to track results).

- **Rate & Ordering:** Generally, tasks are handled in the order they were
  queued, but parallel workers mean they could complete out of order. This is
  normally fine because each task is independent per user. Even if two tasks for
  the same user are running (say the user mentioned two separate new facts in
  quick succession), Neo4j will eventually have both. If ordering ever matters
  (perhaps if fact B depends on fact A being in place), we might enforce
  sequential processing per user by using task chaining or a dedicated queue per
  user, but that’s likely over-complicating. MVP assumption: facts are
  independent enough that concurrent updates are okay.

## Security Model

**User Authentication (Google OIDC):** We exclusively rely on Google Sign-In for
user authentication, which provides a robust, secure login without managing our
own passwords. Users authenticate with Google, and our client obtains an ID
token (JWT) that asserts the user’s identity. The chat-api verifies this token
on each request:

- It uses Google’s public keys (retrieved from Google’s OIDC discovery doc) to
  validate the JWT signature and checks the `aud` (audience) claim to ensure the
  token was intended for our application’s OAuth client ID. It also checks `exp`
  to ensure the token is not expired.
- Once validated, the token’s payload yields the user’s info. We use the `sub`
  claim (a Google unique user ID string) as the primary user key in our system,
  as it’s stable and never re-used. This `user_id` will tag all data belonging
  to the user.
- We may also extract the user’s email and name if needed (the token often
  includes these if scopes allow). However, for privacy and minimalism, we only
  use email for display or contact purposes; authorization is based on the `sub`
  ID.
- No other authentication method is allowed (no username/password or other OAuth
  providers in MVP). This simplifies security – we trust Google’s identity
  assurance and do not have to implement account recovery, password storage,
  etc.

**API Authorization:** Every API call to the chat-api must include a valid ID
token. There is no separate session cookie or server-side session state. This
stateless auth (JWT per request) means the client must handle token refresh
(Google’s ID tokens last about 1 hour). Typically, the front-end would use
Google’s library to silently refresh tokens or prompt the user to sign in again
after expiration. Our server could reject expired tokens with 401, prompting the
client to re-auth.

**Access Control & Multi-Tenancy:** By design, each user can only access their
own data:

- **Knowledge Graph Isolation:** As described, each node/edge in Neo4j is tagged
  with `user_id`. The chat-api, when querying Neo4j for relevant facts, always
  includes a clause filtering on the user’s ID. Similarly, the worker when
  writing will attach the user’s ID. Thereby, even though all users’ data reside
  in one Neo4j instance (for MVP), no cross-user data mixing happens at the
  application level. We do **not** expose any generic Neo4j query interface to
  end-users; they only get data via the controlled chat pipeline. So, there’s no
  direct way for a user to craft a query that retrieves someone else’s nodes.

  - In the future or in enterprise scenarios, we could use Neo4j’s
    multi-database feature to give each user their own isolated database or use
    role-based security, but that’s more complex. The property-based filtering
    is sufficient for a MVP with trust in our application code.
  - It’s critical that every single Cypher query that reads or writes user data
    includes the appropriate user filter. This will be enforced by code review
    and can be encapsulated by utility functions (e.g., always call a function
    `get_user_facts(user_id, vector)` that adds the filter internally).

- **PostgreSQL Access:** The Postgres database holds user records and logs. The
  chat-api and worker services are the only ones with credentials to connect to
  Postgres. Each service uses a least-privilege database user; for example, the
  chat-api might have read-access to user tokens and write-access to logs,
  whereas the worker might have write-access for logs and full access for user
  records. In practice, we can use one user role for simplicity, but we ensure
  the connection string is not exposed to end users. The Postgres instance isn’t
  accessible from the internet – only internally from our services within the
  cluster. Thus, users cannot directly query or tamper with the database.

- **OpenRouter API Key Security:** The OpenRouter API key that users provide is
  sensitive (it permits billing usage on their behalf). Security measures for
  this token:

  - If we store it in Postgres, we will encrypt it. We can use a symmetric
    encryption (e.g., using a key stored in a Kubernetes Secret or using a
    library like Fernet to encrypt before save). At minimum, we store it hashed
    or base64-encoded, but encryption is preferred so we can retrieve the real
    token for API calls.
  - The token is never exposed to other users or logged in plaintext. Debug logs
    will not print it. If included in API requests, it should be in an
    Authorization header (which our logs will deliberately avoid recording) or
    in memory only.
  - When calling OpenRouter, we use HTTPS so the token is encrypted in transit.
    The token is only sent to OpenRouter’s official endpoint.
  - The system should allow the user to revoke or update the token. For
    instance, if a user disconnects their OpenRouter account, we should delete
    the stored token. This could be part of a future “Account settings” feature.

- **Data Privacy:** All user-provided content (chat messages, knowledge graph
  facts derived from them) is considered private to that user. We do not share
  this data across users or use it to retrain models globally (unless a user
  explicitly shares something, which is not in scope). The knowledge graph is
  essentially a personal knowledge base for each user, albeit stored in a common
  database.

  - We inform users that their chat inputs and retrieved facts will be sent to
    an external LLM service (OpenRouter/associated model providers) for the
    purpose of getting answers. OpenRouter itself likely has its own privacy
    policy (and possibly does not retain data or uses it for training, depending
    on settings). Users must *bring their own key*, which implicitly means they
    consent to using that third-party service.
  - As an additional measure, one could allow users to mark certain facts as
    sensitive and perhaps avoid sending those verbatim to the LLM. However, MVP
    will assume all relevant facts can be used for better answers, since the
    user’s goal is to leverage them in answers.

- **Prevention of Unauthorized Access:**

  - We’ll implement checks so that even within our system, a user can’t
    accidentally or maliciously cause another’s data to be touched. For example,
    the Celery task will trust the user_id it’s given (from chat-api); since
    chat-api set that based on the authenticated token, it’s safe. But imagine
    if someone tried to craft a Celery task manually with another’s user_id –
    that would require access to our broker which is protected by network rules
    (only our app connects to Redis, not end users).
  - The Google ID token verification includes checking the `aud` and issuer to
    avoid tokens from other clients or forged tokens.
  - We will enforce HTTPS for the chat-api endpoint (especially since ID tokens
    and potentially OpenRouter keys are in transit). In Kubernetes, we’ll use an
    Ingress or Load Balancer with TLS. If this is a web app scenario, the
    front-end will likely be served over HTTPS as well.
  - Rate limiting: To mitigate abuse or accidental overload, the chat-api can
    enforce a rate limit per user (e.g., using an in-memory counter or a
    Redis-based rate limiter). This is a security measure to prevent denial of
    service and also to control costs on the LLM side. For example, we might
    limit each user to, say, 5 requests per minute burst, with a refill rate.
    MVP might not include this, but it’s a consideration if open usage is
    allowed.
  - Input validation: We will validate and sanitize inputs where applicable.
    Chat messages are mostly free text, but for instance, if any part of the
    message is used in a Cypher query (even as a parameter), we must ensure it’s
    properly parameterized (never string-concatenated into a query) to prevent
    Cypher injection attacks. Using the Neo4j driver parameter binding protects
    against that. Similarly, ensure no SQL injection in any raw SQL (we use ORM
    which is safer by default).

- **Server-Side Security:**

  - Secrets management: The system will have a few secret values (e.g., Neo4j DB
    password, Postgres password, possibly Google OAuth client secret if needed
    for verifying tokens via library, OpenRouter client secret for OAuth if we
    do PKCE). These will all be stored in Kubernetes Secrets, not in code or
    images. The applications will read them from environment variables at
    runtime.
  - The containers will run with least privileges needed. For example, they
    don’t need root; we can use a non-root user in Docker. Network policies can
    restrict that only the chat-api can call out to OpenRouter or Google, and
    only the worker can talk to the databases, etc., but that might be overkill
    for MVP. At least, ensure the database endpoints are not publicly reachable,
    only inside cluster.
  - We will monitor for unusual activities via audit logs. For instance, if an
    attacker somehow got an ID token of another user (which is unlikely, as
    tokens are short-lived and bound to our audience), the audit log would show
    an unexpected user accessing data. The use of Google auth greatly reduces
    that risk due to its solidity.

**Compliance considerations:** Using Google and OpenRouter means user data is
flowing out to third parties. We should comply with relevant data protection
rules:

- If this system stores any personal data (like user email) or potentially
  sensitive knowledge graph content, the users should consent and we should
  protect it. Data at rest in Neo4j and Postgres can be encrypted via disk
  encryption. Backups should be secure.
- We also have to abide by Google’s OAuth policies (e.g., not misusing user
  info, providing a way to delete data if user disconnects).
- The system does not store highly sensitive personal info by itself (unless the
  user inputs it into the chat knowingly). In an enterprise context, additional
  steps like PII detection might be needed, but that’s beyond MVP.

## Deployment Notes

The entire system will be containerized and deployed on a Kubernetes cluster
(e.g., Azure AKS or AWS EKS). Here we describe the deployment architecture and
key configuration:

- **Containerization:** We will have at least two distinct container images:

  1. **chat-api Image:** A Python 3.13 environment with Falcon and required
     libraries (for OpenRouter API calls, JWT verification, Neo4j driver, etc.).
     This image will run the Falcon app (possibly under a WSGI/ASGI server like
     Gunicorn or Uvicorn for production stability). We might name the deployment
     `chat-api-deployment` with a corresponding service.
  2. **worker Image:** A Python 3.13 environment with Celery, Redis client,
     Neo4j driver, SQLAlchemy, and NLP libraries (spaCy model data could be
     included here). This image runs the Celery worker process. Multiple
     replicas of this can be run for scaling. Name it `worker-deployment`. Both
     images could be derived from a common base (to avoid duplication of shared
     dependencies). They will be built and pushed to a container registry. We
     will use a CI/CD pipeline to build these images whenever code is updated.

- **Kubernetes Objects:**

  - **Deployments:**

    - `chat-api-deployment`: spec with desired replica count (initially maybe 2
      for redundancy). Include readiness probe (HTTP GET on `/health`) to ensure
      traffic only flows when ready. Attach necessary environment variables (for
      DB URLs, etc. via ConfigMap/Secret). Mount a volume for certificates if
      needed (for example, if using certificate for Neo4j TLS). Resource
      requests: e.g., request 200m CPU and 256Mi memory (adjust based on load
      tests), with limits set higher (to handle bursts).
    - `worker-deployment`: similarly, set replicas (maybe start with 1). It
      doesn’t need a service because it’s not serving external traffic. Ensure
      it can reach Redis, Postgres, and Neo4j. Set an environment variable like
      `CELERY_BROKER_URL=redis://...` etc. Give it slightly more memory if NLP
      is heavy (e.g., 512Mi or more, depending on model sizes).

  - **Stateful Services:**

    - **Redis:** We need a Redis instance for the message broker. Options:

      - Use a managed Redis service (like AWS ElastiCache or Azure Cache for
        Redis) and configure the connection string in our app. This is ideal for
        reliability.
      - Or deploy Redis in-cluster (as a Deployment or StatefulSet with
        persistence). If in-cluster, we’d set a PersistentVolumeClaim for data
        if we want persistence, though for a broker ephemeral might be okay; but
        to avoid data loss on pod restart, enabling AOF persistence is safer. We
        will secure Redis by limiting access to it (network policy or at least
        not exposing it outside).

    - **PostgreSQL:** Again, could be managed (Azure Postgres, AWS RDS) –
      recommended for ease. If we self-deploy, use a StatefulSet with a
      persistent volume. Ensure to configure user and database. We’ll provide
      the DSN (host, port, user, password, db name) via a Secret to the apps.
      The worker will run migrations on startup (if using something like
      Alembic) to ensure the schema (for user table, logs) is up-to-date.

    - **Neo4j:** Deployment of Neo4j could be done via Neo4j’s Kubernetes Helm
      chart or manually as a StatefulSet. It will require a persistent volume to
      store the graph data. Alternatively, one might use Neo4j Aura DS (a cloud
      offering) and just provide the bolt URI and credentials. In MVP, a
      single-instance Neo4j community edition might be fine; for production, a
      causal cluster of Neo4j could be used for high availability. The
      connection info (bolt URI, username, password) will be given to worker and
      chat-api (since chat-api reads from the KG) as environment secrets.

  - **Services & Ingress:**

    - The chat-api will be exposed via a Kubernetes Service, likely of type
      ClusterIP (for internal) plus an Ingress for external exposure. On
      AKS/EKS, an Ingress controller (like NGINX or ALB on AWS) can handle TLS
      termination and routing. The ingress can be configured at
      `https://yourdomain/chat` or similar, pointing to the chat-api service. We
      enforce TLS so that all traffic is encrypted. The ingress could also
      require an auth check, but since we already do JWT verification inside,
      it’s not strictly necessary at ingress (though we could add an annotation
      to require a valid JWT to even enter, if using something like oauth2-proxy
      – not in MVP scope).
    - For internal communication, ensure DNS or environment variables allow
      chat-api and worker pods to reach the databases. For example, if using a
      Postgres service, chat-api can reach it at
      `postgres.default.svc.cluster.local:5432` or similar. We will configure
      these addresses appropriately.

  - **Scaling & Auto-scaling:** We enable Horizontal Pod Autoscaler (HPA) for
    the chat-api deployment. Criteria can be CPU or better, a custom metric like
    average response time if available. Since LLM calls might make CPU usage low
    while waiting I/O, CPU might not fully indicate load. We might choose to
    scale on concurrent request count if we had such metrics. However, as an
    approximation, CPU or memory usage can trigger adding pods when needed. For
    the worker, HPA can be tied to queue length – if Celery task queue grows (a
    metric we can export), then add more worker pods. In absence of that, we
    could at least scale by CPU if the NLP tasks use CPU.

  - **Configuration Management:** Use ConfigMaps for non-sensitive configs (like
    names of models to use, perhaps a flag to enable/disable some feature). Use
    Secrets for sensitive config:

    - Google OAuth client ID/secret (if needed for verifying tokens or using
      Google API – though token verification can also use Google’s certs without
      client secret).
    - OpenRouter client ID/secret (for OAuth PKCE flow).
    - Neo4j credentials, Postgres credentials.
    - Encryption key for OpenRouter tokens (if we implement encryption). These
      secrets are mounted as env vars into the pods. Developers and ops team
      will handle these values carefully (they won’t be in source code).

  - **Observability in Deployment:** We will deploy a logging solution (if not
    using cloud’s default). E.g., fluent-bit to collect logs to Elastic or Azure
    Monitor. For metrics, we might deploy Prometheus and Grafana or rely on
    cloud monitor. We ensure the pods have the proper annotations or sidecars
    for metrics. Celery can be instrumented or at least we can log task timings.

  - **Domain & SSL:** We will have a domain for the API (maybe something like
    `chat.example.com`). Google OAuth and OpenRouter OAuth will need redirect
    URIs pointing to this domain (for the callback). We’ll provision an SSL
    certificate (using Let’s Encrypt via Cert-Manager in K8s or a cloud
    certificate). All client interactions with chat-api go over HTTPS.
    Internally, traffic between pods can be plaintext, but we might consider
    enabling TLS on Neo4j and Postgres for extra security (that complicates
    setup slightly, so MVP might not).

- **Deployment Process:**

  - We will define Kubernetes manifests or use Helm charts for all components.
    For example, a Helm chart could parameterize the database connection info,
    replicas count, etc.
  - CI/CD (like GitHub Actions or Azure DevOps) will automate building Docker
    images and deploying to K8s on new commits (maybe in a dev environment
    first).
  - For versioning, we tag images (like `chat-api:v1.0.0`). We might use rolling
    updates so that new versions roll out without downtime. Ensure readiness
    checks so new pods handle traffic only when ready.
  - Before deploying to production, we will run load tests to tune the number of
    replicas and resources. Sub-second RAG means we must confirm the embedding
    model and Neo4j query speed meet the requirement; if not, we adjust (maybe
    warm up caches, use faster models, etc.).

- **Example Deployment Topology:** In Kubernetes, after deployment, the system
  might look like (textually described):

  - 2 pods running chat-api, each connected to the cluster’s ingress. They talk
    to Neo4j service (1 pod), Postgres service (1 pod), and Redis service (1
    pod) internally.
  - 1 pod running worker (Celery). It connects to the same Neo4j, Postgres,
    Redis.
  - The user’s browser interacts via the ingress to chat-api pods. Google OIDC
    and OpenRouter calls happen externally (browser to Google, chat-api to
    OpenRouter).
  - If any component fails, Kubernetes will restart it as per deployment
    settings. We have logs to debug issues.

- **Backup and Maintenance:**

  - We will set up a scheduled backup for Postgres (e.g., a daily dump or use
    managed DB snapshots).
  - For Neo4j, if using a persistent volume, schedule backups using Neo4j’s
    backup tool or by snapshotting the volume. Because the knowledge graph is
    crucial data (especially user-provided knowledge), we want the ability to
    restore it in case of accidental deletion or corruption.
  - Rolling updates for Neo4j (if clustered) and Postgres (if needed) should be
    planned. For MVP, downtime during maintenance might be acceptable if short
    (since users can re-ask questions later), but ideally we minimize downtime
    by using highly available DB setups.
  - Logging retention: The logs and audit tables may grow. We might implement a
    retention policy (e.g., keep audit logs for X days or archive old ones) to
    prevent unbounded growth in Postgres.

In summary, the deployment in Kubernetes will leverage the platform’s strengths:
self-healing, scalability, and easy management of config/secrets. By separating
services and using proven images (Falcon app, Celery worker) we ensure each can
be scaled and managed independently. The target cloud (AKS/EKS) will influence
some details (like using Cloud-specific DB services or not), but the design
keeps it fairly cloud-agnostic except for how we manage secrets and ingress.

## Architecture & Data Flow Diagrams (Textual Description)

**High-Level Architecture:** The system is composed of the following main
components and external integrations:

- **User Interface (Client):** The user (from a web or mobile app) interacts
  with the chat system. They log in with Google and initiate chats. The client
  holds the Google ID token (for auth) and either the OpenRouter API key or
  initiates the OAuth flow for OpenRouter. The client sends chat requests to the
  chat-api and displays responses to the user.
- **Chat API Service (Falcon web service):** This is the entry point for all
  chat requests. It authenticates the user via the Google token, orchestrates
  retrieval of relevant knowledge, calls the LLM service (OpenRouter), and
  returns the answer. It also detects new knowledge and pushes tasks for
  background processing. Think of this as the online query processor that must
  respond quickly.
- **Knowledge Graph (Neo4j database):** A graph DB that stores facts as nodes
  and relationships. This is the external memory for the chatbot, enabling it to
  have up-to-date, structured knowledge per user. It supports Cypher queries and
  possibly vector similarity searches (either via plugin or by our own indexing
  approach). Neo4j holds data for all users but tagged by user, effectively
  partitioning the knowledge by user ownership.
- **Vector Index (possible component within Neo4j or standalone):** Not a
  separate service per se in MVP, but conceptually the system uses a vector
  similarity search mechanism to find relevant facts. This could be implemented
  by storing embeddings in Neo4j and using a procedure for similarity, or by a
  separate in-memory index. It’s invoked by chat-api during retrieval.
- **LLM Service (OpenRouter API):** An external service that front-ends various
  large language models. Our chat-api sends it requests with user prompts +
  context and receives generated responses. Each call is authorized with the
  user’s own OpenRouter token, so OpenRouter accounts usage per user. OpenRouter
  itself connects to model providers (like OpenAI, Anthropic, etc.) – abstracted
  away from our system. The communication is via HTTPS REST calls.
- **Task Queue (Redis + Celery):** The glue between chat-api and worker. When
  chat-api enqueues a job, it goes into the Redis broker. The Celery worker
  listens and pulls tasks from Redis in FIFO order (roughly).
- **Background Worker (Celery Worker Service):** The offline processor that
  handles knowledge updates. It receives tasks, extracts new info, and updates
  databases. It has connections to Neo4j and Postgres to perform these updates
  and logging. It does not interact with the user directly and can run for
  longer durations if needed without impacting user experience.
- **PostgreSQL Database:** Stores persistent data that doesn’t fit in the graph
  or that requires relational storage. Key uses: user account info (e.g.,
  mapping Google IDs to any application-specific settings or storing OpenRouter
  token), and audit logs (records of events). The worker mostly interacts with
  Postgres (inserting logs, reading/writing user tokens). The chat-api might
  query it on startup or per request to get the user’s OpenRouter token or to
  record an audit entry for the request.
- **Google OIDC Provider (accounts.google.com):** External identity provider for
  login. The user is redirected here (or uses Google’s SDK) to authenticate.
  Google returns an ID token which the client passes to chat-api. Chat-api may
  also use Google’s certs (fetched from a well-known URL) to verify the token’s
  signature. There is no direct call from our backend to Google in normal
  operations (token verification is done with local JWT libraries and Google’s
  public keys).
- **Security Context:** All communication channels are secured: HTTPS for client
  to chat-api and chat-api to OpenRouter; the internal connections (to DBs) are
  within a private network or cluster. Google tokens and OpenRouter keys are
  kept confidential throughout.

In a **diagrammatic view**, one could imagine the user at the top, the chat-api
in the middle handling requests, the knowledge graph and LLM on either side
(chat-api pulls data from KG on left, calls LLM on right), and the background
worker below the chat-api updating the KG. The Postgres and Redis would be
supporting components (Redis connecting chat-api and worker, Postgres storing
metadata). All of these are deployed on Kubernetes, with services connecting
them, and external calls going out to Google and OpenRouter.

**Sequence Flow of a Typical Interaction:** Below is a step-by-step walkthrough
of how the components interact when a user sends a message to the chatbot and a
new fact is learned:

01. **User Authentication (Preliminary):** The user opens the chat application
    and clicks "Sign in with Google". Google’s OIDC flow occurs (possibly
    entirely on the front-end): the user authenticates with Google and your app
    obtains a Google ID token for the user. The user is now authenticated in the
    app. Separately, the user also connects their OpenRouter account: either by
    providing an API key or via a one-time OAuth flow. Suppose the user went
    through OAuth PKCE with OpenRouter; our server exchanged the code and
    obtained their API key, storing it securely. Now the system has (a) the
    user’s identity token and (b) an LLM API key for that user.

02. **User Sends a Chat Message:** The user types a query or message in the chat
    UI (e.g., "My cat Fluffy just had surgery on her leg. How should I take care
    of her?"). The front-end sends this to the backend by making a **POST**
    request to `/chat`. It includes:

    - The message text (and perhaps the recent dialogue history for context).
    - The user’s Google ID token in the Authorization header to prove who they
      are.
    - (If we didn’t store the OpenRouter token server-side, it would also
      include the OpenRouter API key here, but in our design we assume it’s
      stored so it’s not sent every time.)

03. **Request Validation:** The chat-api service receives the request. It first
    verifies the Google ID token:

    - It checks signature and claims. On success, it knows the user’s ID (let’s
      say User123).
    - It looks up User123 in the Postgres user table to retrieve the OpenRouter
      API key (if one is on file). If not found, it may respond with an error
      telling the user to provide a token.
    - Assuming the key is found (say a token XYZ…), the chat-api is now ready to
      process the query.

04. **RAG Retrieval – Embedding:** The chat-api takes the user’s query "My cat
    Fluffy had surgery on her leg..." and passes it to an embedding model to
    obtain a vector representation. This could be done by calling an embedding
    endpoint (for instance, OpenRouter might proxy an embedding model, or use
    OpenAI embeddings if available) or using a local library. This step yields a
    vector (e.g., a 1536-d float array) capturing semantic meaning of the query.

05. **RAG Retrieval – Knowledge Graph Query:** Using the embedding vector, the
    chat-api finds relevant knowledge graph entries for User123:

    - It queries a vector index of the knowledge graph. For example, it finds
      the top 5 nodes whose embeddings are closest to the query vector (maybe
      the query is about pet care, so it might find a node representing "Fluffy"
      if it existed, or more general "Cat" care tips if any global knowledge
      were present).
    - Suppose "Fluffy" was not in the KG yet (this is the first mention), but
      the user had some generic pet info: the KG might have a node for "cat"
      with some relationships to care instructions, or nothing. Regardless, the
      vector search yields any semantically related info. Then, a Cypher query
      runs to fetch the actual properties and relationships of those nodes. If a
      relevant entity is found (like "Cat" concept), it might also traverse
      relationships (e.g., connect to a "PetCare" node).
    - In our scenario, since "Fluffy" is new, the KG might only return generic
      info. Let’s assume it finds a node "Cat (animal)" which has a relationship
      to "VeterinaryCare" with some text note. Those pieces of info are
      retrieved. The chat-api now has a set of facts (maybe none are directly
      about Fluffy since that’s new, but some related facts about cats or
      surgery after-care might be in a global knowledge base if we had one).
    - All queries ensure `user_id = User123` or `user_id is null for global` so
      that we don’t accidentally retrieve someone else’s data.

06. **Prompt Construction:** The chat-api now constructs the prompt for the LLM.
    It might do something like:

    - System message: "You are a helpful assistant. The user has a knowledge
      graph with the following facts: (1) Cats often need rest after surgery;
      (2) Fluffy is a cat (just mentioned by user). Use this information when
      appropriate."
    - User message: the actual user query. This packaging can vary, but the key
      is the retrieved knowledge is inserted into the conversation context for
      the LLM.

07. **LLM API Call:** The chat-api makes a POST request to OpenRouter’s chat
    completion API. It includes the model (e.g., `gpt-4`), the assembled
    messages (system + user messages, plus possibly any assistant messages if
    continuing a conversation), and sets the Authorization header with
    `Bearer XYZ...` where XYZ is the user’s OpenRouter API key. OpenRouter
    receives this, authenticates that the API key belongs to User123 (so the
    usage will be tracked to them), and forwards the request to the specified
    model. The network call happens over HTTPS.

    - This step might take a couple of seconds as the model generates an answer.
      OpenRouter then sends back the completion result to our chat-api.

08. **Receive LLM Response:** The chat-api receives the response, which might be
    something like: "*I’m sorry to hear about Fluffy. After her leg surgery,
    make sure she stays off her leg as much as possible. Keep the wound clean
    and dry...*" along with any usage tokens info. The chat-api extracts the
    assistant’s message text.

09. **Send Response to User:** The chat-api immediately responds to the original
    HTTP request with a JSON containing the answer. The user’s app receives this
    and displays the answer to the user. From the user’s perspective, they sent
    a question and got a helpful answer that possibly even incorporated the
    knowledge (if any) from the KG.

10. **Novelty Detection Trigger:** Meanwhile, in parallel or just after sending
    the response, the chat-api runs the novelty detection on the user’s input
    ("My cat Fluffy..."). It identifies "Fluffy" as a Named Entity (likely a pet
    name, which might be classified as a PERSON or simply a PROPER NOUN by NER).
    The system checks Neo4j and does not find any node named "Fluffy" for
    User123. This is flagged as new. It might also parse that Fluffy is the
    user’s cat (the text implies possession, but to keep it simple, we at least
    know Fluffy is a cat because the user says "my cat Fluffy"). We might deduce
    a relation: User123 (or a node representing the user) *owns* Fluffy, or
    Fluffy *is a cat*. For MVP, perhaps we just note "Fluffy – type: Cat –
    relation: owner is [User]" implicitly.

    - The chat-api creates a task payload:
      `user_id=User123, text="My cat Fluffy just had surgery on her leg."`. It
      might also include hints like `entities=["Fluffy"], relations=[...]` if it
      pre-processed those, but let’s assume it passes raw text.
    - It enqueues this as a Celery task `kg_update` into Redis.
    - This enqueue is quick (a network call to Redis which is typically < 10ms).
      The user’s response was already sent, so this happens fully in background.

11. **Celery Picks up the Task:** The Celery worker process (maybe running on a
    separate pod) is constantly polling Redis. It sees the new task for
    `kg_update` and pulls it. Now in the worker:

    - It reads the payload: user_id=User123, text="My cat Fluffy had surgery on
      her leg."

    - It logs "Processing knowledge update for User123: 'My cat Fluffy had
      surgery...'"

    - Runs NER on the text. Suppose NER finds two entities: "Fluffy" (with label
      PERSON or ANIMAL – if we have a custom model it might not label "Fluffy"
      as an animal by default since it's a name, but context "my cat" helps; we
      might custom-handle "my cat X" patterns), and possibly "leg" (which might
      not be a named entity, likely not). It might identify "surgery" as a noun
      but not a named entity. So key new entity is "Fluffy".

    - RE step: We might not have a sophisticated relation extraction here.
      However, from "my cat Fluffy", we can infer a relation "Fluffy is a cat
      owned by [User]." If we model the user in the KG, we could create a node
      for the user (User123) and relate it: (User123)-[:OWNS]->(Fluffy). If we
      haven’t been storing users in the KG, we might skip that. Alternatively,
      we classify Fluffy’s type as Cat (based on the word "cat" right before the
      name). So we might create (Fluffy)-[:IS_A]->(CatSpecies) if we had a
      taxonomy. But maybe too complex for MVP. We at least know Fluffy is an
      entity of interest.

      - The worker constructs Cypher queries to add Fluffy. It might do:

        ```cypher
        MERGE (f:Pet {name:"Fluffy", user_id:"User123"})
          ON CREATE SET
            f.species = "cat",
            f.created_at = ...,
            f.source = "chat message 123";
        ```

      If we have a node for the user or a concept "cat", it might also MERGE
      those relationships. It also logs to Postgres: Insert into AuditLog:
      (user_id=User123, action="KG_UPDATE", detail="Added entity Fluffy (Pet)")
      with timestamp.

    - The worker commits these changes to Neo4j and Postgres. Now the knowledge
      graph has a new node "Fluffy" belonging to User123.

    - It then marks the Celery task as completed (acknowledges it).

12. **Subsequent Query Usage:** Later, if the user asks a related question,
    e.g., "Is it safe to let Fluffy climb stairs?", the chat-api will again
    embed the query and search the KG. This time, because "Fluffy" is now in the
    KG (added from the previous interaction), the vector similarity search or
    even a direct entity lookup will find Fluffy’s node. The chat-api might
    retrieve that and see properties like `species=cat`. It might also retrieve
    any connected info (if we had stored that she had surgery, we might have a
    relation or property indicating an injury). The prompt for the LLM can now
    include: "Fluffy is the user’s cat who recently had leg surgery." This
    additional context will make the answer more personalized (the LLM could say
    "Given that Fluffy is recovering from leg surgery, it’s best to limit stair
    climbing initially..."). This demonstrates the system’s
    *surprise-awareness*: it learned a new fact (Fluffy, and her condition) and
    used it in future answers.

13. **Maintenance and Iteration:** Over time, the user might introduce many new
    entities and facts. The background worker continues to accumulate these into
    the KG. If a piece of info changes (the user corrects something), the worker
    updates versions as described. The chat-api always uses the latest graph
    state to answer queries.

This sequence shows the interplay: the chat-api is the synchronous orchestrator
for answering questions, while the worker is the asynchronous updater of the
knowledge source. The user experiences a smart chatbot that gets to know their
world (knowledge graph) without slowdowns, and the system in the background
curates that knowledge graph as the conversation progresses.

In summary, the architecture combines real-time retrieval-augmented AI (for
quality answers) with a persistent evolving memory (the knowledge graph) that is
updated in the background whenever surprises (new information) are detected. The
use of Kubernetes ensures this can run reliably at scale, with each component
(API, worker, databases) in appropriate pods or services. Security is enforced
at the boundaries (Google auth at entry, token-based LLM calls, data isolation
in storage), making the system multi-tenant and user-trustworthy.
