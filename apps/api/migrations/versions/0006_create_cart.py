"""Create carts and cart_items tables.

Revision ID: 0006_create_cart
Revises: 0005_create_delivery
Create Date: 2026-10-07 17:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006_create_cart"
down_revision: str | None = "0005_create_delivery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create carts and cart_items tables with composite integrity constraints."""
    # 1. Create carts table
    op.create_table(
        "carts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("restaurant_id", sa.Uuid(), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name="pk_carts"),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["users.id"],
            name="fk_carts_customer_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["restaurant_id"],
            ["restaurants.id"],
            name="fk_carts_restaurant_id_restaurants",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("customer_id", name="uq_carts_customer_id"),
        sa.UniqueConstraint(
            "id",
            "restaurant_id",
            name="uq_carts_id_restaurant_id",
        ),
    )
    op.create_index("ix_carts_customer_id", "carts", ["customer_id"])
    op.create_index("ix_carts_restaurant_id", "carts", ["restaurant_id"])

    # 2. Create cart_items table
    op.create_table(
        "cart_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("cart_id", sa.Uuid(), nullable=False),
        sa.Column("restaurant_id", sa.Uuid(), nullable=False),
        sa.Column("menu_item_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name="pk_cart_items"),
        sa.ForeignKeyConstraint(
            ["cart_id", "restaurant_id"],
            ["carts.id", "carts.restaurant_id"],
            name="fk_cart_items_cart_id_restaurant_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["menu_item_id", "restaurant_id"],
            ["menu_items.id", "menu_items.restaurant_id"],
            name="fk_cart_items_menu_item_id_restaurant_id",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "cart_id",
            "menu_item_id",
            name="uq_cart_items_cart_id_menu_item_id",
        ),
        sa.CheckConstraint(
            "quantity > 0",
            name="ck_cart_items_quantity_positive",
        ),
    )
    op.create_index("ix_cart_items_cart_id", "cart_items", ["cart_id"])
    op.create_index("ix_cart_items_menu_item_id", "cart_items", ["menu_item_id"])


def downgrade() -> None:
    """Drop cart_items and carts tables."""
    op.drop_index("ix_cart_items_menu_item_id", table_name="cart_items")
    op.drop_index("ix_cart_items_cart_id", table_name="cart_items")
    op.drop_table("cart_items")

    op.drop_index("ix_carts_restaurant_id", table_name="carts")
    op.drop_index("ix_carts_customer_id", table_name="carts")
    op.drop_table("carts")
