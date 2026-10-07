"""Tests for the identity foundation domain, models, constraints, and migrations."""

import uuid
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import sqlalchemy as sa
from alembic.command import downgrade, upgrade
from alembic.config import Config

from app.core.database import Base
from app.identity import User, UserRepository, UserRole, UserStatus


def test_user_model_metadata_registration():
    """1. Verify User model registers correctly in Base.metadata with table name 'users'."""
    assert "users" in Base.metadata.tables
    table = Base.metadata.tables["users"]
    assert table.name == "users"
    assert User.__tablename__ == "users"


def test_user_columns_and_nullability():
    """2. Verify all required columns exist with correct types and nullability."""
    table = Base.metadata.tables["users"]
    columns = table.columns

    expected_columns = {
        "id": (False, sa.Uuid),
        "email": (False, sa.String),
        "phone": (True, sa.String),
        "password_hash": (False, sa.String),
        "first_name": (False, sa.String),
        "last_name": (False, sa.String),
        "role": (False, sa.Enum),
        "status": (False, sa.Enum),
        "created_at": (False, sa.DateTime),
        "updated_at": (False, sa.DateTime),
    }

    for col_name, (nullable, expected_type) in expected_columns.items():
        assert col_name in columns, f"Column {col_name} missing from users table"
        col = columns[col_name]
        assert col.nullable is nullable, (
            f"Column {col_name} nullable expected {nullable}, got {col.nullable}"
        )
        assert isinstance(col.type, expected_type), (
            f"Column {col_name} type expected {expected_type}, got {type(col.type)}"
        )


def test_role_enumeration_values():
    """3. Verify UserRole enumeration contains all architectural roles."""
    expected_roles = {"CUSTOMER", "RESTAURANT", "DELIVERY_PARTNER", "ADMIN"}
    defined_roles = {role.value for role in UserRole}
    assert defined_roles == expected_roles

    # Verify string compatibility
    assert UserRole.CUSTOMER == "CUSTOMER"
    assert UserRole.RESTAURANT == "RESTAURANT"
    assert UserRole.DELIVERY_PARTNER == "DELIVERY_PARTNER"
    assert UserRole.ADMIN == "ADMIN"


def test_status_enumeration_values():
    """4. Verify UserStatus enumeration contains all lifecycle states."""
    expected_statuses = {"ACTIVE", "INACTIVE", "SUSPENDED"}
    defined_statuses = {status.value for status in UserStatus}
    assert defined_statuses == expected_statuses

    # Verify string compatibility
    assert UserStatus.ACTIVE == "ACTIVE"
    assert UserStatus.INACTIVE == "INACTIVE"
    assert UserStatus.SUSPENDED == "SUSPENDED"


def test_email_uniqueness_and_indexes():
    """5. Verify email uniqueness constraint definition and role/status indexes."""
    table = Base.metadata.tables["users"]

    # Check unique constraint on email
    unique_constraints = [
        c for c in table.constraints if isinstance(c, sa.UniqueConstraint)
    ]
    email_uq_constraint = next(
        (c for c in unique_constraints if "email" in [col.name for col in c.columns]),
        None,
    )
    assert email_uq_constraint is not None, "Unique constraint on email is missing"
    assert email_uq_constraint.name == "uq_users_email"

    # Check indexes on role and status, verify redundant ix_users_email is removed
    index_names = {idx.name: [c.name for c in idx.columns] for idx in table.indexes}
    assert "ix_users_email" not in index_names, (
        "Redundant ix_users_email must be removed"
    )
    assert "ix_users_role" in index_names
    assert index_names["ix_users_role"] == ["role"]
    assert "ix_users_status" in index_names
    assert index_names["ix_users_status"] == ["status"]


def test_primary_key_definition():
    """6. Verify primary key definition on id column."""
    table = Base.metadata.tables["users"]
    pk_cols = [col.name for col in table.primary_key.columns]
    assert pk_cols == ["id"]
    assert isinstance(table.c.id.type, sa.Uuid)


def test_timestamp_columns():
    """7. Verify timezone-aware timestamp columns with server defaults."""
    table = Base.metadata.tables["users"]
    for col_name in ("created_at", "updated_at"):
        col = table.c[col_name]
        assert isinstance(col.type, sa.DateTime)
        assert col.type.timezone is True
        assert col.server_default is not None


def test_migration_metadata_integration():
    """8. Verify Alembic configuration can discover migration revisions."""
    alembic_ini_path = Path(__file__).resolve().parent.parent / "alembic.ini"
    assert alembic_ini_path.exists()

    alembic_cfg = Config(str(alembic_ini_path))
    from alembic.script import ScriptDirectory

    script_dir = ScriptDirectory.from_config(alembic_cfg)
    head_revision = script_dir.get_current_head()
    assert head_revision == "0001_create_users_table"

    script = script_dir.get_revision(head_revision)
    assert script is not None
    assert script.down_revision is None


def test_migration_upgrade_and_downgrade_sql_generation(capsys):
    """9. Verify offline SQL generation for upgrade and downgrade without live DB."""
    alembic_ini_path = Path(__file__).resolve().parent.parent / "alembic.ini"
    alembic_cfg = Config(str(alembic_ini_path))

    # Test upgrade --sql
    upgrade(alembic_cfg, "head", sql=True)
    out, _ = capsys.readouterr()

    assert "CREATE TYPE user_role AS ENUM" in out
    assert "CREATE TYPE user_status AS ENUM" in out
    assert "CREATE TABLE users" in out
    assert "CONSTRAINT uq_users_email UNIQUE (email)" in out
    assert "ix_users_email" not in out
    assert "CREATE INDEX ix_users_role ON users (role)" in out
    assert "CREATE INDEX ix_users_status ON users (status)" in out
    assert "0001_create_users_table" in out

    # Test downgrade --sql
    downgrade(alembic_cfg, "0001_create_users_table:base", sql=True)
    out_down, _ = capsys.readouterr()

    assert "DROP INDEX ix_users_status" in out_down
    assert "DROP INDEX ix_users_role" in out_down
    assert "DROP INDEX ix_users_email" not in out_down
    assert "DROP TABLE users" in out_down
    assert "DROP TYPE user_status" in out_down
    assert "DROP TYPE user_role" in out_down


def test_user_model_instantiation_and_defaults():
    """Verify in-memory model instantiation sets defaults correctly."""
    user = User(
        email="CUSTOMER@example.com",
        password_hash="$2b$12$securehashvalue1234567890",
        first_name="Jane",
        last_name="Doe",
    )
    assert isinstance(user.id, uuid.UUID)
    assert user.email == "customer@example.com"  # Normalized
    assert user.role == UserRole.CUSTOMER
    assert user.status == UserStatus.ACTIVE
    assert user.phone is None
    assert isinstance(user.created_at, datetime)
    assert user.created_at.tzinfo is not None
    assert isinstance(user.updated_at, datetime)
    assert user.updated_at.tzinfo is not None


def test_email_normalization_and_validation():
    """Verify email is stripped and lowercased, and invalid blanks are rejected."""
    user = User(
        email="   Alice.Smith@Domain.ORG  ",
        password_hash="hashed_pw",
        first_name="Alice",
        last_name="Smith",
    )
    assert user.email == "alice.smith@domain.org"

    with pytest.raises(ValueError, match="non-empty string"):
        user.email = ""

    with pytest.raises(ValueError, match="cannot be blank"):
        user.email = "   "


def test_user_repr_security_does_not_leak_password():
    """Verify __repr__ includes identity metadata but excludes password_hash."""
    user = User(
        email="security@example.com",
        password_hash="super_secret_password_hash",
        first_name="Sec",
        last_name="User",
    )
    repr_str = repr(user)
    assert "security@example.com" in repr_str
    assert "super_secret_password_hash" not in repr_str
    assert "password_hash" not in repr_str


@pytest.mark.asyncio
async def test_user_repository_methods():
    """Verify UserRepository CRUD abstractions interact with AsyncSession correctly."""
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    repo = UserRepository(mock_session)

    # get_by_id
    mock_result_id = MagicMock()
    mock_user = MagicMock(spec=User)
    mock_result_id.scalar_one_or_none.return_value = mock_user
    mock_session.execute.return_value = mock_result_id

    user_id = uuid.uuid4()
    found = await repo.get_by_id(user_id)
    assert found == mock_user
    mock_session.execute.assert_awaited()

    # get_by_email
    mock_result_email = MagicMock()
    mock_result_email.scalar_one_or_none.return_value = mock_user
    mock_session.execute.return_value = mock_result_email

    found_email = await repo.get_by_email("  Test@Example.COM  ")
    assert found_email == mock_user

    # create
    new_user = User(
        email="new@example.com",
        password_hash="hash",
        first_name="New",
        last_name="User",
    )
    created = await repo.create(new_user)
    mock_session.add.assert_called_once_with(new_user)
    mock_session.flush.assert_awaited_once()
    assert created == new_user
