"""Falcon resource classes for the chat API."""

from __future__ import annotations

import dataclasses
import typing

import falcon


@dataclasses.dataclass(slots=True)
class ChatRequest:
    """Request body for the chat endpoint."""

    message: str
    history: list[dict[str, typing.Any]] | None = None


class ChatResource:
    """Handle chat requests."""

    async def on_post(self, req: falcon.Request, resp: falcon.Response) -> None:
        data = await req.get_media()
        if not data or "message" not in data:
            raise falcon.HTTPBadRequest(description="`message` field required")

        # TODO: plug in RAG and LLM call
        resp.media = {"answer": "This is a placeholder response."}


class OpenRouterTokenResource:
    """Store user's OpenRouter API token."""

    async def on_post(self, req: falcon.Request, resp: falcon.Response) -> None:
        data = await req.get_media()
        if not data or "api_key" not in data:
            raise falcon.HTTPBadRequest(description="`api_key` field required")

        # TODO: persist the token for the authenticated user
        resp.media = {"status": "stored"}


class HealthResource:
    """Basic health check."""

    async def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        resp.media = {"status": "ok"}
