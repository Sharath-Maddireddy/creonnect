"""Database engine and session helpers."""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator, Generator

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.utils.logger import logger


DEFAULT_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/creonnect"
_ASYNC_DRIVERS = {"asyncpg", "aiosqlite", "aiomysql", "asyncmy", "aiopg"}

_ASYNC_ENGINE = None
_ASYNC_SESSIONMAKER: async_sessionmaker[AsyncSession] | None = None
_SYNC_ENGINE = None
_SYNC_SESSIONMAKER: sessionmaker[Session] | None = None


load_dotenv(override=False)


def get_database_url() -> str:
    """Return the configured database URL."""
    return os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL).strip() or DEFAULT_DATABASE_URL


def get_sync_database_url() -> str:
    """Return a sync SQLAlchemy URL derived from DATABASE_URL."""
    database_url = get_database_url()
    if database_url.startswith("postgresql+asyncpg://"):
        return database_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
    return database_url


def _has_async_driver(database_url: str) -> bool:
    """Check whether DATABASE_URL is configured with a known async driver."""
    url = make_url(database_url)
    parts = url.drivername.split("+")
    driver = parts[1] if len(parts) > 1 else None
    return driver in _ASYNC_DRIVERS


def get_async_engine():
    """Return the shared async engine."""
    global _ASYNC_ENGINE
    if _ASYNC_ENGINE is None:
        database_url = get_database_url()
        if not _has_async_driver(database_url):
            raise RuntimeError(f"DATABASE_URL must include an async driver for async engine use: {database_url}")
        _ASYNC_ENGINE = create_async_engine(database_url, future=True, pool_pre_ping=True)
    return _ASYNC_ENGINE


def get_async_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Return the shared async sessionmaker."""
    global _ASYNC_SESSIONMAKER
    if _ASYNC_SESSIONMAKER is None:
        _ASYNC_SESSIONMAKER = async_sessionmaker(
            bind=get_async_engine(),
            autoflush=False,
            expire_on_commit=False,
        )
    return _ASYNC_SESSIONMAKER


def get_sync_engine():
    """Return the shared sync engine."""
    global _SYNC_ENGINE
    if _SYNC_ENGINE is None:
        _SYNC_ENGINE = create_engine(get_sync_database_url(), future=True, pool_pre_ping=True)
    return _SYNC_ENGINE


def get_sync_sessionmaker() -> sessionmaker[Session]:
    """Return the shared sync sessionmaker."""
    global _SYNC_SESSIONMAKER
    if _SYNC_SESSIONMAKER is None:
        _SYNC_SESSIONMAKER = sessionmaker(
            bind=get_sync_engine(),
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
        )
    return _SYNC_SESSIONMAKER


def get_sync_db() -> Generator[Session, None, None]:
    """Yield a sync SQLAlchemy session."""
    session = get_sync_sessionmaker()()
    try:
        yield session
    finally:
        session.close()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async SQLAlchemy session for FastAPI dependencies."""
    async_session = get_async_sessionmaker()
    async with async_session() as session:
        yield session


async def init_db(*, strict: bool = False) -> None:
    """Create database tables if the database is reachable.

    When ``strict`` is True, initialization errors are re-raised so callers can
    fail fast on database misconfiguration. The default remains non-fatal to
    preserve the existing degraded-startup behavior.
    """
    from backend.app.infra.models import Base

    try:
        engine = get_async_engine()
        async with engine.begin() as connection:
            if connection.dialect.name == "postgresql":
                await connection.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
            await connection.run_sync(Base.metadata.create_all)
    except (RuntimeError, SQLAlchemyError, OSError) as exc:
        logger.warning("[Database] Skipping init_db because database setup failed: %s", exc)
        if strict:
            raise


def reset_database_engines() -> None:
    """Reset cached engines/sessionmakers. Primarily used by tests."""
    global _ASYNC_ENGINE, _ASYNC_SESSIONMAKER, _SYNC_ENGINE, _SYNC_SESSIONMAKER
    if _ASYNC_ENGINE is not None:
        _ASYNC_ENGINE.sync_engine.dispose()
    if _SYNC_ENGINE is not None:
        _SYNC_ENGINE.dispose()
    _ASYNC_ENGINE = None
    _ASYNC_SESSIONMAKER = None
    _SYNC_ENGINE = None
    _SYNC_SESSIONMAKER = None


async def reset_database_engines_async() -> None:
    """Reset cached engines/sessionmakers and await async engine disposal."""
    global _ASYNC_ENGINE, _ASYNC_SESSIONMAKER, _SYNC_ENGINE, _SYNC_SESSIONMAKER
    if _ASYNC_ENGINE is not None:
        await _ASYNC_ENGINE.dispose()
    if _SYNC_ENGINE is not None:
        _SYNC_ENGINE.dispose()
    _ASYNC_ENGINE = None
    _ASYNC_SESSIONMAKER = None
    _SYNC_ENGINE = None
    _SYNC_SESSIONMAKER = None
