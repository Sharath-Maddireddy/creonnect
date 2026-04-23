"""Database engine and session helpers."""

from __future__ import annotations

import asyncio
import os
import threading
from collections.abc import AsyncGenerator, Generator
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.utils.logger import logger


DEFAULT_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/creonnect"
_ASYNC_DRIVERS = {"asyncpg", "aiosqlite", "aiomysql", "asyncmy", "aiopg"}

_ASYNC_ENGINE = None
_ASYNC_SESSIONMAKER: async_sessionmaker[AsyncSession] | None = None
_SYNC_ENGINE = None
_SYNC_SESSIONMAKER: sessionmaker[Session] | None = None
_ENGINE_LOCK = threading.RLock()


load_dotenv(override=False)


def get_database_url() -> str:
    """Return the configured database URL."""
    return os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL).strip() or DEFAULT_DATABASE_URL


def get_sync_database_url() -> str:
    """Return a sync SQLAlchemy URL derived from DATABASE_URL."""
    database_url = get_database_url()
    driver_replacements = {
        "postgresql+asyncpg://": "postgresql+psycopg2://",
        "sqlite+aiosqlite://": "sqlite+pysqlite://",
        "mysql+aiomysql://": "mysql+pymysql://",
        "mysql+asyncmy://": "mysql+pymysql://",
    }
    for async_prefix, sync_prefix in driver_replacements.items():
        if database_url.startswith(async_prefix):
            return database_url.replace(async_prefix, sync_prefix, 1)
    return database_url


def _has_async_driver(database_url: str) -> bool:
    """Check whether DATABASE_URL is configured with a known async driver."""
    url = make_url(database_url)
    parts = url.drivername.split("+")
    driver = parts[1] if len(parts) > 1 else None
    return driver in _ASYNC_DRIVERS


def _get_int_env(name: str, default: int) -> int:
    """Return an integer environment variable with a safe fallback."""
    raw_value = (os.getenv(name) or "").strip()
    if not raw_value:
        return default
    try:
        return int(raw_value)
    except ValueError:
        logger.warning("Invalid %s=%r; falling back to %s", name, raw_value, default)
        return default


def _get_engine_kwargs(database_url: str, *, is_async: bool) -> dict[str, Any]:
    """Build engine kwargs with production-friendly pooling for network databases."""
    url = make_url(database_url)
    kwargs: dict[str, Any] = {
        "future": True,
        "pool_pre_ping": True,
    }

    if url.get_backend_name() == "sqlite":
        return kwargs

    kwargs.update(
        pool_size=_get_int_env("DB_POOL_SIZE", 10),
        max_overflow=_get_int_env("DB_MAX_OVERFLOW", 20),
        pool_timeout=_get_int_env("DB_POOL_TIMEOUT", 30),
        pool_recycle=_get_int_env("DB_POOL_RECYCLE", 1800),
    )
    if is_async and url.drivername == "postgresql+asyncpg":
        kwargs["connect_args"] = {"command_timeout": _get_int_env("DB_COMMAND_TIMEOUT", 10)}
    return kwargs


def get_async_engine():
    """Return the shared async engine."""
    global _ASYNC_ENGINE
    if _ASYNC_ENGINE is None:
        with _ENGINE_LOCK:
            if _ASYNC_ENGINE is None:
                database_url = get_database_url()
                if not _has_async_driver(database_url):
                    raise RuntimeError(f"DATABASE_URL must include an async driver for async engine use: {database_url}")
                _ASYNC_ENGINE = create_async_engine(
                    database_url,
                    **_get_engine_kwargs(database_url, is_async=True),
                )
    return _ASYNC_ENGINE


def get_async_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Return the shared async sessionmaker."""
    global _ASYNC_SESSIONMAKER
    if _ASYNC_SESSIONMAKER is None:
        with _ENGINE_LOCK:
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
        with _ENGINE_LOCK:
            if _SYNC_ENGINE is None:
                database_url = get_sync_database_url()
                _SYNC_ENGINE = create_engine(
                    database_url,
                    **_get_engine_kwargs(database_url, is_async=False),
                )
    return _SYNC_ENGINE


def get_sync_sessionmaker() -> sessionmaker[Session]:
    """Return the shared sync sessionmaker."""
    global _SYNC_SESSIONMAKER
    if _SYNC_SESSIONMAKER is None:
        with _ENGINE_LOCK:
            if _SYNC_SESSIONMAKER is None:
                _SYNC_SESSIONMAKER = sessionmaker(
                    bind=get_sync_engine(),
                    autoflush=False,
                    autocommit=False,
                    expire_on_commit=False,
                )
    return _SYNC_SESSIONMAKER


def initialize_database_engines() -> None:
    """Warm up cached engines/sessionmakers during application startup."""
    get_async_sessionmaker()
    get_sync_sessionmaker()


def get_sync_db() -> Generator[Session, None, None]:
    """Yield a sync SQLAlchemy session."""
    session = get_sync_sessionmaker()()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
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
    async_engine: AsyncEngine | None = None
    sync_engine: Engine | None = None
    with _ENGINE_LOCK:
        async_engine = _ASYNC_ENGINE
        sync_engine = _SYNC_ENGINE
        _ASYNC_ENGINE = None
        _ASYNC_SESSIONMAKER = None
        _SYNC_ENGINE = None
        _SYNC_SESSIONMAKER = None
    if async_engine is not None:
        try:
            asyncio.run(async_engine.dispose())
        except RuntimeError as exc:
            raise RuntimeError(
                "reset_database_engines() cannot dispose the async engine while an event loop is running; "
                "use reset_database_engines_async() instead."
            ) from exc
    if sync_engine is not None:
        sync_engine.dispose()


async def reset_database_engines_async() -> None:
    """Reset cached engines/sessionmakers and await async engine disposal."""
    global _ASYNC_ENGINE, _ASYNC_SESSIONMAKER, _SYNC_ENGINE, _SYNC_SESSIONMAKER
    async_engine: AsyncEngine | None = None
    sync_engine: Engine | None = None
    with _ENGINE_LOCK:
        async_engine = _ASYNC_ENGINE
        sync_engine = _SYNC_ENGINE
        _ASYNC_ENGINE = None
        _ASYNC_SESSIONMAKER = None
        _SYNC_ENGINE = None
        _SYNC_SESSIONMAKER = None
    if async_engine is not None:
        await async_engine.dispose()
    if sync_engine is not None:
        sync_engine.dispose()
