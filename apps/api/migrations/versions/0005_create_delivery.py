"""Create delivery_partners and deliveries tables.

Revision ID: 0005_create_delivery
Revises: 0004_create_payments
Create Date: 2026-10-07 16:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0005_create_delivery"
down_revision: str | None = "0004_create_payments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

delivery_partner_status_enum = postgresql.ENUM(
    "ACTIVE",
    "INACTIVE",
    "SUSPENDED",
    name="delivery_partner_status",
)

delivery_partner_availability_enum = postgresql.ENUM(
    "AVAILABLE",
    "UNAVAILABLE",
    name="delivery_partner_availability",
)

vehicle_type_enum = postgresql.ENUM(
    "BIKE",
    "SCOOTER",
    "MOTORCYCLE",
    "BICYCLE",
    "CAR",
    "OTHER",
    name="vehicle_type",
)

delivery_status_enum = postgresql.ENUM(
    "UNASSIGNED",
    "ASSIGNED",
    "PICKED_UP",
    "OUT_FOR_DELIVERY",
    "DELIVERED",
    "CANCELLED",
    "FAILED",
    name="delivery_status",
)


def upgrade() -> None:
    """Create delivery enums, delivery_partners, and deliveries tables."""
    # 1. Create enums
    delivery_partner_status_enum.create(op.get_bind())
    delivery_partner_availability_enum.create(op.get_bind())
    vehicle_type_enum.create(op.get_bind())
    delivery_status_enum.create(op.get_bind())

    # 2. Create delivery_partners table
    op.create_table(
        "delivery_partners",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "ACTIVE",
                "INACTIVE",
                "SUSPENDED",
                name="delivery_partner_status",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "availability",
            sa.Enum(
                "AVAILABLE",
                "UNAVAILABLE",
                name="delivery_partner_availability",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "vehicle_type",
            sa.Enum(
                "BIKE",
                "SCOOTER",
                "MOTORCYCLE",
                "BICYCLE",
                "CAR",
                "OTHER",
                name="vehicle_type",
                create_type=False,
            ),
            nullable=True,
        ),
        sa.Column("vehicle_identifier", sa.String(length=100), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name="pk_delivery_partners"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_delivery_partners_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("user_id", name="uq_delivery_partners_user_id"),
    )

    op.create_index(
        "ix_delivery_partners_status",
        "delivery_partners",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_delivery_partners_availability",
        "delivery_partners",
        ["availability"],
        unique=False,
    )

    # 3. Create deliveries table
    op.create_table(
        "deliveries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("delivery_partner_id", sa.Uuid(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "UNASSIGNED",
                "ASSIGNED",
                "PICKED_UP",
                "OUT_FOR_DELIVERY",
                "DELIVERED",
                "CANCELLED",
                "FAILED",
                name="delivery_status",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("picked_up_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name="pk_deliveries"),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            name="fk_deliveries_order_id_orders",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["delivery_partner_id"],
            ["delivery_partners.id"],
            name="fk_deliveries_delivery_partner_id_delivery_partners",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("order_id", name="uq_deliveries_order_id"),
    )

    op.create_index(
        "ix_deliveries_delivery_partner_id",
        "deliveries",
        ["delivery_partner_id"],
        unique=False,
    )
    op.create_index("ix_deliveries_status", "deliveries", ["status"], unique=False)
    op.create_index(
        "ix_deliveries_created_at",
        "deliveries",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Drop deliveries, delivery_partners, and enums."""
    op.drop_index("ix_deliveries_created_at", table_name="deliveries")
    op.drop_index("ix_deliveries_status", table_name="deliveries")
    op.drop_index("ix_deliveries_delivery_partner_id", table_name="deliveries")
    op.drop_table("deliveries")

    op.drop_index("ix_delivery_partners_availability", table_name="delivery_partners")
    op.drop_index("ix_delivery_partners_status", table_name="delivery_partners")
    op.drop_table("delivery_partners")

    delivery_status_enum.drop(op.get_bind())
    vehicle_type_enum.drop(op.get_bind())
    delivery_partner_availability_enum.drop(op.get_bind())
    delivery_partner_status_enum.drop(op.get_bind())
