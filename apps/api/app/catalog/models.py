"""SQLAlchemy 2.x declarative domain models for the catalog domain."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.restaurants.models import Restaurant


def utc_now() -> datetime:
    """Return timezone-aware UTC datetime."""
    return datetime.now(UTC)


class MenuCategory(Base):
    """Menu category grouping menu items within a restaurant."""

    __tablename__ = "menu_categories"

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid,
        sa.ForeignKey(
            "restaurants.id",
            ondelete="CASCADE",
            name="fk_menu_categories_restaurant_id",
        ),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(
        sa.String(100),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(
        sa.Text,
        nullable=True,
    )
    display_order: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        default=0,
        server_default=sa.text("0"),
    )
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean,
        nullable=False,
        default=True,
        server_default=sa.text("true"),
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        default=utc_now,
        server_default=sa.func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        default=utc_now,
        server_default=sa.func.now(),
        onupdate=utc_now,
        nullable=False,
    )

    __table_args__ = (
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
        sa.Index("ix_menu_categories_restaurant_id", "restaurant_id"),
    )

    # Relationships
    restaurant: Mapped["Restaurant"] = relationship(
        "Restaurant",
        back_populates="categories",
    )
    menu_items: Mapped[list["MenuItem"]] = relationship(
        "MenuItem",
        back_populates="category",
        cascade="all, delete-orphan",
        passive_deletes=True,
        primaryjoin=(
            "and_("
            "MenuCategory.id == MenuItem.category_id, "
            "MenuCategory.restaurant_id == MenuItem.restaurant_id"
            ")"
        ),
        overlaps="menu_items,restaurant",
    )

    def __init__(
        self,
        *,
        restaurant_id: uuid.UUID,
        name: str,
        id: uuid.UUID | None = None,
        description: str | None = None,
        display_order: int = 0,
        is_active: bool = True,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.id = id if id is not None else uuid.uuid4()
        self.restaurant_id = restaurant_id
        self.name = name
        self.description = description
        self.display_order = display_order
        self.is_active = is_active
        self.created_at = created_at if created_at is not None else utc_now()
        self.updated_at = updated_at if updated_at is not None else utc_now()

    def __repr__(self) -> str:
        """Safe string representation of MenuCategory."""
        return (
            f"<MenuCategory id={self.id} restaurant_id={self.restaurant_id} "
            f"name={self.name!r} is_active={self.is_active}>"
        )


class MenuItem(Base):
    """Menu item offered by a restaurant under a menu category."""

    __tablename__ = "menu_items"

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid,
        nullable=False,
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(
        sa.String(255),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(
        sa.Text,
        nullable=True,
    )
    price: Mapped[Decimal] = mapped_column(
        sa.Numeric(precision=10, scale=2),
        nullable=False,
    )
    is_available: Mapped[bool] = mapped_column(
        sa.Boolean,
        nullable=False,
        default=True,
        server_default=sa.text("true"),
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        default=utc_now,
        server_default=sa.func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        default=utc_now,
        server_default=sa.func.now(),
        onupdate=utc_now,
        nullable=False,
    )

    __table_args__ = (
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
        sa.UniqueConstraint(
            "id",
            "restaurant_id",
            name="uq_menu_items_id_restaurant_id",
        ),
        sa.Index("ix_menu_items_restaurant_id", "restaurant_id"),
        sa.Index("ix_menu_items_category_id", "category_id"),
    )

    # Relationships
    restaurant: Mapped["Restaurant"] = relationship(
        "Restaurant",
        back_populates="menu_items",
        foreign_keys=[restaurant_id],
    )
    category: Mapped["MenuCategory"] = relationship(
        "MenuCategory",
        back_populates="menu_items",
        primaryjoin=(
            "and_("
            "MenuItem.category_id == MenuCategory.id, "
            "MenuItem.restaurant_id == MenuCategory.restaurant_id"
            ")"
        ),
        overlaps="menu_items,restaurant",
    )

    def __init__(
        self,
        *,
        restaurant_id: uuid.UUID,
        category_id: uuid.UUID,
        name: str,
        price: Decimal | float | str,
        id: uuid.UUID | None = None,
        description: str | None = None,
        is_available: bool = True,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.id = id if id is not None else uuid.uuid4()
        self.restaurant_id = restaurant_id
        self.category_id = category_id
        self.name = name
        self.description = description
        self.price = Decimal(str(price))
        self.is_available = is_available
        self.created_at = created_at if created_at is not None else utc_now()
        self.updated_at = updated_at if updated_at is not None else utc_now()

    def __repr__(self) -> str:
        """Safe string representation of MenuItem."""
        return (
            f"<MenuItem id={self.id} restaurant_id={self.restaurant_id} "
            f"category_id={self.category_id} name={self.name!r} "
            f"price={self.price} is_available={self.is_available}>"
        )
