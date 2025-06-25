"""Utility helpers for Falcon resources."""

from __future__ import annotations

import typing

import falcon

from .chat_service import load_user_and_api_key

if typing.TYPE_CHECKING:  # pragma: no cover
    from sqlalchemy.ext.asyncio import AsyncSession


async def get_api_key(
    session_factory: typing.Callable[[], AsyncSession], user: str
) -> str | None:
    """Return the stored OpenRouter API key for *user* or ``None`` if missing."""
    try:
        _, api_key = await load_user_and_api_key(session_factory, user)
    except falcon.HTTPUnauthorized:
        return None
    return api_key
