"""SQLAlchemy ORM models for the chat service."""

from __future__ import annotations

import datetime as dt
import enum
import typing
import uuid  # noqa: TC003 - required at runtime for SQLAlchemy annotations

from sqlalchemy import (
    JSON,
    TIMESTAMP,
    CheckConstraint,
    Enum,
    ForeignKey,
    Index,
    LargeBinary,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from .mixins import CreatedAtMixin, TimestampMixin, UuidPKMixin


class Base(DeclarativeBase):
    """Base class for all ORM models."""


class AuditEventType(enum.StrEnum):
    """Categories of events captured for auditing."""

    CHAT_REQUEST = enum.auto()
    CHAT_RESPONSE = enum.auto()
    KG_UPDATE_ENQUEUED = enum.auto()
    KG_UPDATE_APPLIED = enum.auto()
    AUTH = enum.auto()
    ERROR = enum.auto()


class KgChangeType(enum.StrEnum):
    """Types of changes applied to the knowledge graph."""

    NODE_CREATED = enum.auto()
    NODE_UPDATED = enum.auto()
    REL_CREATED = enum.auto()
    REL_UPDATED = enum.auto()
    REL_DEACTIVATED = enum.auto()


class MessageRole(enum.StrEnum):
    """Roles associated with chat messages."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class UserAccount(Base, UuidPKMixin, TimestampMixin):
    """Persisted user profile and authentication data."""

    __tablename__ = "user_account"

    google_sub: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255))
    openrouter_token_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    last_login_at: Mapped[dt.datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    __table_args__ = (CheckConstraint("email LIKE '%@%'", name="chk_email"),)

    audit_events: Mapped[list[AuditEvent]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    kg_changes: Mapped[list[KgChange]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    conversations: Mapped[list[Conversation]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class AuditEvent(Base, CreatedAtMixin):
    """Record of user activity for auditing."""

    __tablename__ = "audit_event"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("user_account.id", ondelete="CASCADE")
    )
    event_type: Mapped[AuditEventType] = mapped_column(
        Enum(AuditEventType, name="audit_event_type"), nullable=False
    )
    http_request_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    detail: Mapped[str | None] = mapped_column(Text)
    meta_json: Mapped[typing.Any | None] = mapped_column(JSON)

    user: Mapped[UserAccount] = relationship(back_populates="audit_events")

    __table_args__ = (Index("idx_audit_user_time", "user_id", "created_at"),)


class KgChange(Base):
    """Change made to the knowledge graph."""

    __tablename__ = "kg_change"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("user_account.id", ondelete="CASCADE")
    )
    change_type: Mapped[KgChangeType] = mapped_column(
        Enum(KgChangeType, name="kg_change_type"), nullable=False
    )
    node_uid: Mapped[str | None] = mapped_column(Text)
    rel_uid: Mapped[str | None] = mapped_column(Text)
    cypher_fragment: Mapped[str | None] = mapped_column(Text)
    diff_json: Mapped[typing.Any | None] = mapped_column(JSON)
    created_at: Mapped[dt.datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: dt.datetime.now(dt.UTC),
    )

    user: Mapped[UserAccount] = relationship(back_populates="kg_changes")

    __table_args__ = (Index("idx_kgchange_user_time", "user_id", "created_at"),)


class EncKeyHistory(Base, CreatedAtMixin):
    """History of encryption keys used to store tokens."""

    __tablename__ = "enc_key_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    key_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    __table_args__ = (Index("idx_enckeyhistory_key_id", "key_id"),)
    retired_at: Mapped[dt.datetime | None] = mapped_column(TIMESTAMP(timezone=True))


class Conversation(Base, UuidPKMixin, TimestampMixin):
    """Thread of related chat messages for a user."""

    __tablename__ = "conversation"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("user_account.id", ondelete="CASCADE")
    )
    root_message_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("message.id", ondelete="SET NULL")
    )
    title: Mapped[str | None] = mapped_column(Text)
    forked_from_conv_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("conversation.id", ondelete="SET NULL")
    )
    forked_from_msg_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("message.id", ondelete="SET NULL")
    )

    user: Mapped[UserAccount] = relationship(back_populates="conversations")
    messages: Mapped[list[Message]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        foreign_keys=lambda: [Message.conversation_id],
    )


class Message(Base, UuidPKMixin, CreatedAtMixin):
    """Individual chat message within a conversation."""

    __tablename__ = "message"

    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("conversation.id", ondelete="CASCADE")
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("message.id", ondelete="SET NULL")
    )
    role: Mapped[MessageRole] = mapped_column(
        Enum(MessageRole, name="message_role"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    params: Mapped[typing.Any | None] = mapped_column(JSON)
    conversation: Mapped[Conversation] = relationship(
        back_populates="messages", foreign_keys=[conversation_id]
    )
    parent: Mapped[Message | None] = relationship(
        remote_side="Message.id", foreign_keys=[parent_id]
    )

    __table_args__ = (
        Index("idx_msg_parent", "parent_id"),
        Index("idx_msg_convtime", "conversation_id", "created_at"),
    )
