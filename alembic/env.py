from __future__ import annotations

import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from sqlalchemy.types import BIGINT, BigInteger

from alembic import context
from app.infrastructure.database.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# CI에서 SQLite 사용: ALEMBIC_DATABASE_URL 우선, 없으면 .env 기반 PG URL
db_url = os.getenv("ALEMBIC_DATABASE_URL")
if not db_url:
    from app.config import get_database_settings

    db_url = get_database_settings().url
config.set_main_option("sqlalchemy.url", db_url)

target_metadata = Base.metadata

# SQLite reflects BigInteger as BIGINT — ignore this false positive
_BIGINT_TYPES = (BIGINT, BigInteger)


def _compare_type(
    context, inspected_column, metadata_column, inspected_type, metadata_type
):
    if isinstance(inspected_type, _BIGINT_TYPES) and isinstance(
        metadata_type, _BIGINT_TYPES
    ):
        return False
    return None


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=_compare_type,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=_compare_type,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
