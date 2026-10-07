import inspect
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

import migrations.env as migration_env
from app.core.database import (
    Base,
    close_db_engine,
    create_engine_and_sessionmaker,
    engine,
    get_db,
)


def test_base_metadata_initialization():
    """Verify DeclarativeBase metadata initializes cleanly."""
    assert issubclass(Base, DeclarativeBase)
    assert hasattr(Base, "metadata")
    assert "users" in Base.metadata.tables or len(Base.metadata.tables) == 0


def test_engine_and_sessionmaker_construction():
    """Verify AsyncEngine and sessionmaker construction and configuration."""
    assert isinstance(engine, AsyncEngine)
    assert engine.dialect.name == "postgresql"
    assert engine.dialect.driver == "asyncpg"

    custom_engine, custom_sessionmaker = create_engine_and_sessionmaker(
        database_url="postgresql+asyncpg://user:pass@localhost:5432/test_db",
        pool_size=10,
        max_overflow=20,
    )
    assert isinstance(custom_engine, AsyncEngine)
    assert isinstance(custom_sessionmaker, async_sessionmaker)
    assert custom_engine.pool.size() == 10


def test_alembic_config_and_metadata_integration():
    """Verify Alembic configuration and migration target_metadata alignment."""
    alembic_ini_path = Path(__file__).resolve().parent.parent / "alembic.ini"
    assert alembic_ini_path.exists()

    alembic_cfg = Config(str(alembic_ini_path))
    assert alembic_cfg.get_main_option("script_location") == "migrations"
    assert migration_env.target_metadata is Base.metadata


@pytest.mark.asyncio
async def test_get_db_session_lifecycle():
    """Verify get_db async dependency yields session, closes, and rolls back on error."""
    assert inspect.isasyncgenfunction(get_db)

    # Test normal flow
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__.return_value = None
    mock_sessionmaker = MagicMock(return_value=mock_session)

    with patch("app.core.database.AsyncSessionLocal", mock_sessionmaker):
        generator = get_db()
        session = await anext(generator)
        assert session == mock_session
        with pytest.raises(StopAsyncIteration):
            await anext(generator)
        mock_session.__aexit__.assert_awaited_once()

    # Test error handling / rollback flow
    error_session = AsyncMock(spec=AsyncSession)
    error_session.__aenter__.return_value = error_session
    error_session.__aexit__.return_value = None
    error_sessionmaker = MagicMock(return_value=error_session)

    with patch("app.core.database.AsyncSessionLocal", error_sessionmaker):
        generator = get_db()
        await anext(generator)
        with pytest.raises(RuntimeError, match="Simulated DB error"):
            await generator.athrow(RuntimeError("Simulated DB error"))
        error_session.rollback.assert_awaited_once()
        error_session.__aexit__.assert_awaited_once()


@pytest.mark.asyncio
async def test_close_db_engine_disposal():
    """Verify close_db_engine calls engine.dispose()."""
    mock_engine = AsyncMock()
    with patch("app.core.database.engine", mock_engine):
        await close_db_engine()
        mock_engine.dispose.assert_awaited_once()
