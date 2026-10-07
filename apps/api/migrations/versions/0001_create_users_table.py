"""Create users table and identity enums.

Revision ID: 0001_create_users_table
Revises:
Create Date: 2026-10-07 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001_create_users_table"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

user_role_enum = postgresql.ENUM(
    "CUSTOMER",
    "RESTAURANT",
    "DELIVERY_PARTNER",
    "ADMIN",
    name="user_role",
)

user_status_enum = postgresql.ENUM(
    "ACTIVE",
    "INACTIVE",
    "SUSPENDED",
    name="user_status",
)


def upgrade() -> None:
    """Create identity enums, users table, indexes, and constraints."""
    user_role_enum.create(op.get_bind())
    user_status_enum.create(op.get_bind())

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=30), nullable=True),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("last_name", sa.String(length=100), nullable=False),
        sa.Column(
            "role",
            sa.Enum(
                "CUSTOMER",
                "RESTAURANT",
                "DELIVERY_PARTNER",
                "ADMIN",
                name="user_role",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "ACTIVE",
                "INACTIVE",
                "SUSPENDED",
                name="user_status",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_role", "users", ["role"])
    op.create_index("ix_users_status", "users", ["status"])


def downgrade() -> None:
    """Drop users table, indexes, and identity enums."""
    op.drop_index("ix_users_status", table_name="users")
    op.drop_index("ix_users_role", table_name="users")
    op.drop_table("users")

    user_status_enum.drop(op.get_bind())
    user_role_enum.drop(op.get_bind())
