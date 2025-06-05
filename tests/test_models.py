from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Session

from bournemouth.models import Base, Conversation, Message, UserAccount


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
