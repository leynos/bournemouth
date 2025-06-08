import sys
import typing
from pathlib import Path

import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from bournemouth.models import Base, UserAccount

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


@pytest_asyncio.fixture()
async def db_session_factory() -> typing.AsyncIterator[typing.Callable[[], AsyncSession]]:
    """Create an in-memory SQLite ``AsyncSession`` factory."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn, session_factory() as session:
        await conn.run_sync(Base.metadata.create_all)
        async with session.begin():
            session.add(
                UserAccount(
                    google_sub="admin",
                    email="admin@example.com",
                    openrouter_token_enc=b"k",
                )
            )

    def factory() -> AsyncSession:
        return session_factory()

    yield factory
    await engine.dispose()
