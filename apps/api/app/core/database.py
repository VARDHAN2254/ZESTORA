"""Database foundation module for ZESTORA API.

Configures asynchronous SQLAlchemy engine, sessionmaker, declarative base,
and FastAPI session dependencies.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


class Base(DeclarativeBase):
    """Declarative base class for all SQLAlchemy domain models."""


def create_engine_and_sessionmaker(
    database_url: str = settings.DATABASE_URL,
    echo: bool = settings.DB_ECHO,
    pool_size: int = settings.DB_POOL_SIZE,
    max_overflow: int = settings.DB_MAX_OVERFLOW,
    pool_timeout: int = settings.DB_POOL_TIMEOUT,
    pool_recycle: int = settings.DB_POOL_RECYCLE,
) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    """Factory creating an AsyncEngine and async_sessionmaker."""
    engine = create_async_engine(
        database_url,
        echo=echo,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout=pool_timeout,
        pool_recycle=pool_recycle,
        pool_pre_ping=True,
    )
    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
    return engine, session_factory


# Module-level engine and sessionmaker
engine, AsyncSessionLocal = create_engine_and_sessionmaker()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding an async database session per request."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def close_db_engine() -> None:
    """Safely dispose of the database connection pool on application shutdown."""
    if engine is not None:
        await engine.dispose()


async def check_db_connection() -> bool:
    """Helper to verify database connectivity when explicitly requested.

    Must NOT be invoked automatically on application startup or basic health checks.
    """
    from sqlalchemy import text

    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    return True
