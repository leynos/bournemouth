"""Application factory for the chat API."""

from __future__ import annotations

import falcon

from .resources import ChatResource, HealthResource, OpenRouterTokenResource


def create_app() -> falcon.asgi.App:
    """Configure and return the Falcon ASGI app."""

    app = falcon.asgi.App()
    app.add_route("/chat", ChatResource())
    app.add_route("/auth/openrouter-token", OpenRouterTokenResource())
    app.add_route("/health", HealthResource())
    return app
