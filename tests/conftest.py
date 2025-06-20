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

pytest_plugins = ["pytest_httpx"]


@pytest_asyncio.fixture()
async def db_session_factory() -> typing.AsyncIterator[
    typing.Callable[[], AsyncSession]
]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async_session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn, async_session_factory() as session:
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
        return async_session_factory()

    yield factory
    await engine.dispose()
