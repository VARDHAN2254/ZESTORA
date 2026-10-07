import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.core.config import settings
from app.core.database import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = getattr(context, "config", None)

# Interpret the config file for Python logging if config is available.
if config is not None and config.config_file_name is not None:
    fileConfig(config.config_file_name)

# target metadata for 'autogenerate' support
target_metadata = Base.metadata

if config is not None and not config.get_main_option("sqlalchemy.url"):
    config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)


def _load_models() -> None:
    """Import domain models so target_metadata includes them for migrations."""
    import app.catalog.models
    import app.identity.models
    import app.restaurants.models  # noqa: F401


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well. By skipping the Engine creation
    we don't even need a DBAPI to be available.
    """
    _load_models()
    url = config.get_main_option("sqlalchemy.url") if config else settings.DATABASE_URL
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    _load_models()
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode with async engine."""
    configuration = (
        config.get_section(config.config_ini_section, {}) if config is not None else {}
    )
    if "sqlalchemy.url" not in configuration:
        configuration["sqlalchemy.url"] = settings.DATABASE_URL

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if config is not None and hasattr(context, "is_offline_mode"):
    if context.is_offline_mode():
        run_migrations_offline()
    else:
        run_migrations_online()
