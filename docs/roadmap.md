# Implementation Roadmap

This roadmap captures the major features planned for Bournemouth.
Features already implemented are checked off.

## Core API

- [x] Stateless `/chat` endpoint using Falcon
- [ ] Stateful `/chat` endpoint retaining conversation context
- [ ] Stateless WebSocket chat endpoint
- [ ] Stateful WebSocket chat endpoint
- [x] `/auth/openrouter-token` endpoint to store user API keys
- [x] `/login` endpoint issuing signed session cookies
- [x] `/health` endpoint for liveness checks

## Authentication & Authorization

- [x] Basic Auth login with session cookie
- [ ] Google OIDC login flow
- [ ] Per-user rate limiting

## Data Storage

- [x] PostgreSQL models for users, audit events, conversations, and messages
- [ ] Knowledge graph schemas in Neo4j
- [ ] Vector index population and queries

## Background Processing

- [ ] Celery worker for KG updates and embeddings
- [ ] Novelty detection pipeline

## External Integrations

- [x] OpenRouter completions API client
- [ ] Hugging Face TEI embedding client

## Deployment

- [ ] Docker images for API and worker
- [ ] Helm charts or Kubernetes manifests
