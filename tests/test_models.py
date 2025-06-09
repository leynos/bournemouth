from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy import exc as sa_exc
from sqlalchemy.orm import Session

from bournemouth.models import (
    AuditEvent,
    Base,
    Conversation,
    EncKeyHistory,
    KgChange,
    Message,
    UserAccount,
)


def test_metadata_creates_tables() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    inspector = sa.inspect(engine)
    tables = set(inspector.get_table_names())
    assert {
        "user_account",
        "audit_event",
        "kg_change",
        "enc_key_history",
        "conversation",
        "message",
    }.issubset(tables)


def test_insert_user_and_message() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        user = UserAccount(google_sub="123", email="u@example.com")
        session.add(user)
        session.flush()
        conv = Conversation(user=user, title="chat")
        session.add(conv)
        session.flush()
        msg = Message(conversation=conv, role="user", content="hi")
        session.add(msg)
        session.commit()
        assert session.get(UserAccount, user.id) is not None
        assert session.get(Conversation, conv.id) is not None
        assert session.get(Message, msg.id) is not None


def test_unique_constraints() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        user1 = UserAccount(google_sub="1", email="a@example.com")
        session.add(user1)
        session.commit()
        user2 = UserAccount(google_sub="1", email="b@example.com")
        session.add(user2)
        with pytest.raises(sa_exc.IntegrityError):  # pyright: ignore[reportUnknownArgumentType]
            session.commit()
        session.rollback()
        user3 = UserAccount(google_sub="2", email="a@example.com")
        session.add(user3)
        with pytest.raises(sa_exc.IntegrityError):  # pyright: ignore[reportUnknownArgumentType]
            session.commit()


def test_persistence_other_models() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        user = UserAccount(google_sub="1", email="a@example.com")
        session.add(user)
        session.flush()
        audit = AuditEvent(user=user, event_type="AUTH")
        change = KgChange(user=user, change_type="NODE_CREATED")
        key_hist = EncKeyHistory(key_id=uuid.uuid4())
        session.add_all([audit, change, key_hist])
        session.commit()
        assert session.get(AuditEvent, audit.id) is not None
        assert session.get(KgChange, change.id) is not None
        assert session.get(EncKeyHistory, key_hist.id) is not None
