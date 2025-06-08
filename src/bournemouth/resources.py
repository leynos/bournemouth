"""Falcon resource classes for the chat API."""

from __future__ import annotations

import dataclasses
import os
import typing

import falcon

from .openrouter import (
    ChatCompletionRequest,
    ChatMessage,
    OpenRouterAPIError,
    OpenRouterAsyncClient,
    OpenRouterNetworkError,
    OpenRouterServerError,
    OpenRouterTimeoutError,
)

DEFAULT_MODEL = "deepseek/deepseek-chat-v3-0324:free"


@dataclasses.dataclass(slots=True)
class ChatRequest:
    """Request body for the chat endpoint."""

    message: str
    history: list[dict[str, typing.Any]] | None = None
    model: str | None = None


class ChatResource:
    """Handle chat requests."""

    async def on_post(self, req: falcon.Request, resp: falcon.Response) -> None:
        data = await req.get_media()
        if not data or "message" not in data:
            raise falcon.HTTPBadRequest(description="`message` field required")

        msg = str(data["message"])
        history: list[ChatMessage] = []
        if isinstance(data.get("history"), list):
            for item in data["history"]:
                try:
                    role = typing.cast(
                        "typing.Literal['system', 'user', 'assistant', 'tool']",
                        item["role"],
                    )
                    content = str(item["content"])
                except (KeyError, TypeError):
                    raise falcon.HTTPBadRequest(
                        description="invalid history item"
                    ) from None
                history.append(ChatMessage(role=role, content=content))

        history.append(ChatMessage(role="user", content=msg))

        model = (
            typing.cast("str | None", data.get("model"))
            or os.getenv("OPENROUTER_MODEL")
            or DEFAULT_MODEL
        )
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise falcon.HTTPBadRequest(description="OpenRouter API key not configured")

        request_model = ChatCompletionRequest(model=model, messages=history)

        try:
            async with OpenRouterAsyncClient(api_key=api_key) as client:
                completion = await client.create_chat_completion(request_model)
        except OpenRouterTimeoutError:
            raise falcon.HTTPGatewayTimeout() from None
        except (
            OpenRouterNetworkError,
            OpenRouterServerError,
            OpenRouterAPIError,
        ) as exc:
            raise falcon.HTTPBadGateway(description=str(exc)) from None

        answer = completion.choices[0].message.content or ""
        resp.media = {"answer": answer}


class OpenRouterTokenResource:
    """Store user's OpenRouter API token."""

    async def on_post(self, req: falcon.Request, resp: falcon.Response) -> None:
        data = await req.get_media()
        if not data or "api_key" not in data:
            raise falcon.HTTPBadRequest(description="`api_key` field required")

        # TODO(pmcintosh): persist the token for the authenticated user
        # https://github.com/example/repo/issues/2
        raise falcon.HTTPNotImplemented(
            description="This endpoint is not yet implemented."
        )


class HealthResource:
    """Basic health check."""

    async def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        resp.media = {"status": "ok"}
