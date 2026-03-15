"""Async database session management."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from copypoly.config import settings

# QueuePool manages persistent connections to PgBouncer.
# PgBouncer then multiplexes into a smaller set of real PG connections.
# statement_cache_size=0 is REQUIRED for PgBouncer transaction mode
# (asyncpg prepared statements break when server connection changes).
engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_size=500,
    max_overflow=1000,
    pool_pre_ping=True,
    connect_args={"statement_cache_size": 0},
)

# Session factory
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session.

    Usage:
        async with get_session() as session:
            result = await session.execute(...)
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def dispose_engine() -> None:
    """Cleanly dispose the database engine (for shutdown)."""
    await engine.dispose()
