"""Create restaurant, menu_categories, and menu_items tables.

Revision ID: 0002_create_restaurant_catalog
Revises: 0001_create_users_table
Create Date: 2026-10-07 13:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0002_create_restaurant_catalog"
down_revision: str | None = "0001_create_users_table"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

restaurant_status_enum = postgresql.ENUM(
    "ACTIVE",
    "INACTIVE",
    "SUSPENDED",
    name="restaurant_status",
)


def upgrade() -> None:
    """Create restaurant status enum, restaurants, menu_categories, and menu_items."""
    # 1. Create restaurant_status ENUM
    restaurant_status_enum.create(op.get_bind())

    # 2. Create restaurants table
    op.create_table(
        "restaurants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("phone", sa.String(length=30), nullable=False),
        sa.Column("address_line1", sa.String(length=255), nullable=False),
        sa.Column("address_line2", sa.String(length=255), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=False),
        sa.Column("state", sa.String(length=100), nullable=False),
        sa.Column("postal_code", sa.String(length=20), nullable=False),
        sa.Column("latitude", sa.Numeric(precision=9, scale=6), nullable=True),
        sa.Column("longitude", sa.Numeric(precision=9, scale=6), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "ACTIVE",
                "INACTIVE",
                "SUSPENDED",
                name="restaurant_status",
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
        sa.PrimaryKeyConstraint("id", name="pk_restaurants"),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name="fk_restaurants_owner_id_users",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("slug", name="uq_restaurants_slug"),
    )
    op.create_index("ix_restaurants_owner_id", "restaurants", ["owner_id"])
    op.create_index("ix_restaurants_status", "restaurants", ["status"])

    # 3. Create menu_categories table
    op.create_table(
        "menu_categories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("restaurant_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "display_order",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
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
        sa.PrimaryKeyConstraint("id", name="pk_menu_categories"),
        sa.ForeignKeyConstraint(
            ["restaurant_id"],
            ["restaurants.id"],
            name="fk_menu_categories_restaurant_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "restaurant_id",
            "name",
            name="uq_menu_categories_restaurant_id_name",
        ),
        sa.UniqueConstraint(
            "id",
            "restaurant_id",
            name="uq_menu_categories_id_restaurant_id",
        ),
    )
    op.create_index(
        "ix_menu_categories_restaurant_id",
        "menu_categories",
        ["restaurant_id"],
    )

    # 4. Create menu_items table
    op.create_table(
        "menu_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("restaurant_id", sa.Uuid(), nullable=False),
        sa.Column("category_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("price", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column(
            "is_available",
            sa.Boolean(),
            server_default=sa.text("true"),
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
        sa.PrimaryKeyConstraint("id", name="pk_menu_items"),
        sa.ForeignKeyConstraint(
            ["restaurant_id"],
            ["restaurants.id"],
            name="fk_menu_items_restaurant_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["category_id", "restaurant_id"],
            ["menu_categories.id", "menu_categories.restaurant_id"],
            name="fk_menu_items_category_id_restaurant_id",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "price >= 0",
            name="ck_menu_items_price_non_negative",
        ),
    )
    op.create_index("ix_menu_items_restaurant_id", "menu_items", ["restaurant_id"])
    op.create_index("ix_menu_items_category_id", "menu_items", ["category_id"])


def downgrade() -> None:
    """Drop menu_items, menu_categories, restaurants, and restaurant_status enum."""
    op.drop_index("ix_menu_items_category_id", table_name="menu_items")
    op.drop_index("ix_menu_items_restaurant_id", table_name="menu_items")
    op.drop_table("menu_items")

    op.drop_index("ix_menu_categories_restaurant_id", table_name="menu_categories")
    op.drop_table("menu_categories")

    op.drop_index("ix_restaurants_status", table_name="restaurants")
    op.drop_index("ix_restaurants_owner_id", table_name="restaurants")
    op.drop_table("restaurants")

    restaurant_status_enum.drop(op.get_bind())
