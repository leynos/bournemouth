# bournemouth

Bournemouth is an experimental chat application that combines
retrieval-augmented generation with a novelty-aware knowledge graph. The goal is
to store new facts discovered in conversation and recall them with sub-second
latency.

## Architecture

The system comprises a few lightweight services:

1. **chat-api** – A Falcon ASGI app written for Python 3.13. It exposes `/chat`,
   `/auth/openrouter-token`, and `/health` endpoints. It embeds queries,
   retrieves context from Neo4j and proxies prompts to an LLM via OpenRouter.
2. **worker** – Processes background tasks such as entity extraction and graph
   updates using asynchronous SQLAlchemy.
3. **neo4j** – Hosts the knowledge graph and vector indexes for similarity search.
4. **postgres** – Stores user accounts, OpenRouter tokens, and audit logs. It can
   also serve as a fallback vector store via `pgvector`.
5. **traefik** – Handles TLS termination and rate limiting when deployed.

A detailed discussion of this architecture and the scaling path is available in
[`docs/mvp-architecture.md`](docs/mvp-architecture.md) and
[`docs/mid-level-design.md`](docs/mid-level-design.md).

## Development

Dependencies are managed with [uv](https://github.com/astral-sh/uv). After
installing `uv`, set up the environment with:

```bash
uv sync
```

Run the API locally with:

```bash
uv run python -m bournemouth.app
```

The server exposes a `/login` endpoint that accepts HTTP Basic Auth credentials.
On success it returns a signed `session` cookie used by the middleware to guard
all other routes except `/health`. The credentials, session secret and timeout
can be configured via environment variables:

```bash
export LOGIN_USER=admin
export LOGIN_PASSWORD=adminpass
export SESSION_SECRET="$(openssl rand -base64 32)"
export SESSION_TIMEOUT=3600
```

Testing strategies and additional guides live in the `docs/` directory, including:

- [`docs/testing-async-falcon-endpoints.md`](docs/testing-async-falcon-endpoints.md)
  for pytest usage.
- [`docs/async-sqlalchemy-with-pg-and-falcon.md`](docs/async-sqlalchemy-with-pg-and-falcon.md)
  for asynchronous database access.
- [`docs/embedding-with-hf-tei.md`](docs/embedding-with-hf-tei.md)
  for generating embeddings with Hugging Face TEI.
