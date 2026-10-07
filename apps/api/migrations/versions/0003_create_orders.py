"""Create orders and order_items tables.

Revision ID: 0003_create_orders
Revises: 0002_create_restaurant_catalog
Create Date: 2026-10-07 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0003_create_orders"
down_revision: str | None = "0002_create_restaurant_catalog"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

order_status_enum = postgresql.ENUM(
    "PENDING_PAYMENT",
    "CONFIRMED",
    "ACCEPTED",
    "PREPARING",
    "READY_FOR_PICKUP",
    "PICKED_UP",
    "OUT_FOR_DELIVERY",
    "DELIVERED",
    "CANCELLED",
    "FAILED",
    name="order_status",
)


def upgrade() -> None:
    """Create order status enum, orders, and order_items tables."""
    # 1. Add unique constraint on menu_items(id, restaurant_id) for cross-table integrity
    op.create_unique_constraint(
        "uq_menu_items_id_restaurant_id",
        "menu_items",
        ["id", "restaurant_id"],
    )

    # 2. Create order_status ENUM
    order_status_enum.create(op.get_bind())

    # 3. Create orders table
    op.create_table(
        "orders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("restaurant_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING_PAYMENT",
                "CONFIRMED",
                "ACCEPTED",
                "PREPARING",
                "READY_FOR_PICKUP",
                "PICKED_UP",
                "OUT_FOR_DELIVERY",
                "DELIVERED",
                "CANCELLED",
                "FAILED",
                name="order_status",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("subtotal", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column(
            "delivery_fee",
            sa.Numeric(precision=12, scale=2),
            server_default=sa.text("0.00"),
            nullable=False,
        ),
        sa.Column(
            "tax",
            sa.Numeric(precision=12, scale=2),
            server_default=sa.text("0.00"),
            nullable=False,
        ),
        sa.Column(
            "discount",
            sa.Numeric(precision=12, scale=2),
            server_default=sa.text("0.00"),
            nullable=False,
        ),
        sa.Column("total", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column(
            "currency",
            sa.String(length=3),
            server_default=sa.text("'INR'"),
            nullable=False,
        ),
        sa.Column("delivery_address_line1", sa.String(length=255), nullable=False),
        sa.Column("delivery_address_line2", sa.String(length=255), nullable=True),
        sa.Column("delivery_city", sa.String(length=100), nullable=False),
        sa.Column("delivery_state", sa.String(length=100), nullable=False),
        sa.Column("delivery_postal_code", sa.String(length=20), nullable=False),
        sa.Column("delivery_latitude", sa.Numeric(precision=9, scale=6), nullable=True),
        sa.Column(
            "delivery_longitude", sa.Numeric(precision=9, scale=6), nullable=True
        ),
        sa.Column("notes", sa.Text(), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name="pk_orders"),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["users.id"],
            name="fk_orders_customer_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["restaurant_id"],
            ["restaurants.id"],
            name="fk_orders_restaurant_id_restaurants",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "id",
            "restaurant_id",
            name="uq_orders_id_restaurant_id",
        ),
        sa.CheckConstraint(
            "subtotal >= 0",
            name="ck_orders_subtotal_non_negative",
        ),
        sa.CheckConstraint(
            "delivery_fee >= 0",
            name="ck_orders_delivery_fee_non_negative",
        ),
        sa.CheckConstraint(
            "tax >= 0",
            name="ck_orders_tax_non_negative",
        ),
        sa.CheckConstraint(
            "discount >= 0",
            name="ck_orders_discount_non_negative",
        ),
        sa.CheckConstraint(
            "total >= 0",
            name="ck_orders_total_non_negative",
        ),
    )
    op.create_index("ix_orders_customer_id", "orders", ["customer_id"])
    op.create_index("ix_orders_restaurant_id", "orders", ["restaurant_id"])
    op.create_index("ix_orders_status", "orders", ["status"])
    op.create_index("ix_orders_created_at", "orders", ["created_at"])

    # 4. Create order_items table
    op.create_table(
        "order_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("restaurant_id", sa.Uuid(), nullable=False),
        sa.Column("menu_item_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("line_total", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("item_name", sa.String(length=255), nullable=False),
        sa.Column("item_description", sa.Text(), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name="pk_order_items"),
        sa.ForeignKeyConstraint(
            ["order_id", "restaurant_id"],
            ["orders.id", "orders.restaurant_id"],
            name="fk_order_items_order_id_restaurant_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["menu_item_id", "restaurant_id"],
            ["menu_items.id", "menu_items.restaurant_id"],
            name="fk_order_items_menu_item_id_restaurant_id",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "quantity > 0",
            name="ck_order_items_quantity_positive",
        ),
        sa.CheckConstraint(
            "unit_price >= 0",
            name="ck_order_items_unit_price_non_negative",
        ),
        sa.CheckConstraint(
            "line_total >= 0",
            name="ck_order_items_line_total_non_negative",
        ),
    )
    op.create_index("ix_order_items_order_id", "order_items", ["order_id"])
    op.create_index("ix_order_items_menu_item_id", "order_items", ["menu_item_id"])


def downgrade() -> None:
    """Drop order_items, orders, order_status enum, and menu_items constraint."""
    op.drop_index("ix_order_items_menu_item_id", table_name="order_items")
    op.drop_index("ix_order_items_order_id", table_name="order_items")
    op.drop_table("order_items")

    op.drop_index("ix_orders_created_at", table_name="orders")
    op.drop_index("ix_orders_status", table_name="orders")
    op.drop_index("ix_orders_restaurant_id", table_name="orders")
    op.drop_index("ix_orders_customer_id", table_name="orders")
    op.drop_table("orders")

    order_status_enum.drop(op.get_bind())

    op.drop_constraint(
        "uq_menu_items_id_restaurant_id",
        "menu_items",
        type_="unique",
    )
