"""Create payments and payment_events tables.

Revision ID: 0004_create_payments
Revises: 0003_create_orders
Create Date: 2026-10-07 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0004_create_payments"
down_revision: str | None = "0003_create_orders"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

payment_status_enum = postgresql.ENUM(
    "PENDING",
    "AUTHORIZED",
    "CAPTURED",
    "FAILED",
    "CANCELLED",
    "REFUNDED",
    name="payment_status",
)

payment_method_enum = postgresql.ENUM(
    "CARD",
    "UPI",
    "NET_BANKING",
    "WALLET",
    "CASH_ON_DELIVERY",
    name="payment_method",
)


def upgrade() -> None:
    """Create payment enums, payments, and payment_events tables."""
    # 1. Create enums
    payment_status_enum.create(op.get_bind())
    payment_method_enum.create(op.get_bind())

    # 2. Create payments table
    op.create_table(
        "payments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column(
            "currency",
            sa.String(length=3),
            server_default=sa.text("'INR'"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING",
                "AUTHORIZED",
                "CAPTURED",
                "FAILED",
                "CANCELLED",
                "REFUNDED",
                name="payment_status",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "payment_method",
            sa.Enum(
                "CARD",
                "UPI",
                "NET_BANKING",
                "WALLET",
                "CASH_ON_DELIVERY",
                name="payment_method",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("provider", sa.String(length=50), nullable=True),
        sa.Column("provider_payment_id", sa.String(length=255), nullable=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("failure_code", sa.String(length=100), nullable=True),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name="pk_payments"),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            name="fk_payments_order_id_orders",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("amount >= 0", name="ck_payments_amount_non_negative"),
        sa.UniqueConstraint("idempotency_key", name="uq_payments_idempotency_key"),
        sa.UniqueConstraint(
            "provider",
            "provider_payment_id",
            name="uq_payments_provider_provider_payment_id",
        ),
    )

    op.create_index("ix_payments_order_id", "payments", ["order_id"], unique=False)
    op.create_index("ix_payments_status", "payments", ["status"], unique=False)
    op.create_index(
        "ix_payments_provider_payment_id",
        "payments",
        ["provider_payment_id"],
        unique=False,
    )
    op.create_index("ix_payments_created_at", "payments", ["created_at"], unique=False)

    # 3. Create payment_events table
    op.create_table(
        "payment_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("payment_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("provider_event_id", sa.String(length=255), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(),
            nullable=False,
        ),
        sa.Column(
            "processed",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_payment_events"),
        sa.ForeignKeyConstraint(
            ["payment_id"],
            ["payments.id"],
            name="fk_payment_events_payment_id_payments",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "provider",
            "provider_event_id",
            name="uq_payment_events_provider_provider_event_id",
        ),
    )

    op.create_index(
        "ix_payment_events_payment_id", "payment_events", ["payment_id"], unique=False
    )
    op.create_index(
        "ix_payment_events_provider_event_id",
        "payment_events",
        ["provider_event_id"],
        unique=False,
    )
    op.create_index(
        "ix_payment_events_created_at", "payment_events", ["created_at"], unique=False
    )


def downgrade() -> None:
    """Drop payment_events, payments, and enums."""
    op.drop_index("ix_payment_events_created_at", table_name="payment_events")
    op.drop_index("ix_payment_events_provider_event_id", table_name="payment_events")
    op.drop_index("ix_payment_events_payment_id", table_name="payment_events")
    op.drop_table("payment_events")

    op.drop_index("ix_payments_created_at", table_name="payments")
    op.drop_index("ix_payments_provider_payment_id", table_name="payments")
    op.drop_index("ix_payments_status", table_name="payments")
    op.drop_index("ix_payments_order_id", table_name="payments")
    op.drop_table("payments")

    payment_method_enum.drop(op.get_bind())
    payment_status_enum.drop(op.get_bind())
