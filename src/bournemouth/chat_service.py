"""Helper routines for chat resources."""

from __future__ import annotations

import typing

import falcon
from sqlalchemy import select
from uuid_extensions import uuid7

from .models import Conversation, Message, UserAccount
from .openrouter_service import (
    OpenRouterService,
    OpenRouterServiceBadGatewayError,
    OpenRouterServiceTimeoutError,
    chat_with_service,
)

if typing.TYPE_CHECKING:  # pragma: no cover
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from .openrouter import ChatMessage


async def load_user_and_api_key(
    session_factory: typing.Callable[[], AsyncSession],
    user_sub: str,
) -> tuple[uuid.UUID, str | None]:
    """Return the user's ID and decrypted OpenRouter API key."""

    async with session_factory() as session:
        stmt = select(UserAccount.id, UserAccount.openrouter_token_enc).where(
            UserAccount.google_sub == user_sub
        )
        result = await session.execute(stmt)
        row = result.one_or_none()

    if row is None:
        raise falcon.HTTPUnauthorized(description="invalid or missing user record")

    user_id, token = typing.cast("tuple[uuid.UUID, bytes | str | None]", row)
    api_key = token.decode() if isinstance(token, bytes) else token
    if api_key is not None and not api_key.strip():
        api_key = None
    return user_id, api_key


async def generate_answer(
    service: OpenRouterService,
    api_key: str,
    messages: list[ChatMessage],
    model: str | None,
) -> str:
    """Call the chat service and return the assistant's reply."""

    try:
        completion = await chat_with_service(service, api_key, messages, model=model)
    except OpenRouterServiceTimeoutError:
        raise falcon.HTTPGatewayTimeout() from None
    except OpenRouterServiceBadGatewayError as exc:
        raise falcon.HTTPBadGateway(description=str(exc)) from None

    if not completion.choices:
        raise falcon.HTTPBadGateway(description="no completion choices")
    return completion.choices[0].message.content or ""


async def get_or_create_conversation(
    session: AsyncSession,
    conv_id: uuid.UUID | None,
    user_id: uuid.UUID,
) -> Conversation:
    """Return an existing conversation or create a new one."""

    conv: Conversation | None = None
    if conv_id is not None:
        conv = await session.get(Conversation, conv_id)
        if conv is None or conv.user_id != user_id:
            raise falcon.HTTPNotFound()
    if conv is None:
        conv = Conversation(
            id=typing.cast("uuid.UUID", uuid7(as_type="uuid")),
            user_id=user_id,
        )
        session.add(conv)
        await session.flush()
    return conv


async def list_conversation_messages(
    session: AsyncSession,
    conv_id: uuid.UUID,
) -> list[Message]:
    """Return messages for ``conv_id`` ordered by creation time."""

    stmt = (
        select(Message)
        .where(Message.conversation_id == conv_id)
        .order_by(Message.created_at)
    )
    result = await session.execute(stmt)
    return typing.cast("list[Message]", result.scalars().all())
