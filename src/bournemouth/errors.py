"""Error-handling helpers for Falcon-based APIs."""

from __future__ import annotations

import logging
import typing
from http import HTTPStatus

if typing.TYPE_CHECKING:  # pragma: no cover
    from falcon import HTTPError, Request, Response

__all__ = ["handle_http_error", "handle_unexpected_error"]


async def handle_http_error(
    req: Request,
    resp: Response,
    exc: HTTPError,
    params: dict[str, typing.Any],
) -> None:
    """Serialize :class:`falcon.HTTPError` exceptions as JSON."""
    resp.status = exc.status
    resp.media = {"title": exc.title, "description": exc.description}


async def handle_unexpected_error(
    req: Request,
    resp: Response,
    exc: BaseException,
    params: dict[str, typing.Any],
) -> None:
    """Handle uncaught exceptions with a generic JSON payload."""
    logging.exception("unhandled error", exc_info=exc)
    resp.status = HTTPStatus.INTERNAL_SERVER_ERROR
    resp.media = {
        "title": (
            f"{HTTPStatus.INTERNAL_SERVER_ERROR.value} "
            f"{HTTPStatus.INTERNAL_SERVER_ERROR.phrase}"
        ),
        "description": "An unexpected error occurred.",
    }
