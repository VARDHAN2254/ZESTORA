"""SQLAlchemy 2.x declarative domain models for the cart domain."""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.catalog.models import MenuItem
    from app.identity.models import User
    from app.restaurants.models import Restaurant


def utc_now() -> datetime:
    """Return timezone-aware UTC datetime."""
    return datetime.now(UTC)


class Cart(Base):
    """Cart entity representing a customer's persistent shopping cart."""

    __tablename__ = "carts"

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid,
        sa.ForeignKey(
            "users.id",
            ondelete="CASCADE",
            name="fk_carts_customer_id_users",
        ),
        nullable=False,
    )
    restaurant_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid,
        sa.ForeignKey(
            "restaurants.id",
            ondelete="SET NULL",
            name="fk_carts_restaurant_id_restaurants",
        ),
        nullable=True,
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
        sa.UniqueConstraint("customer_id", name="uq_carts_customer_id"),
        sa.UniqueConstraint(
            "id",
            "restaurant_id",
            name="uq_carts_id_restaurant_id",
        ),
        sa.Index("ix_carts_customer_id", "customer_id"),
        sa.Index("ix_carts_restaurant_id", "restaurant_id"),
    )

    # Relationships
    customer: Mapped["User"] = relationship(
        "User",
        back_populates="cart",
    )
    restaurant: Mapped["Restaurant | None"] = relationship(
        "Restaurant",
        foreign_keys=[restaurant_id],
    )
    items: Mapped[list["CartItem"]] = relationship(
        "CartItem",
        back_populates="cart",
        cascade="all, delete-orphan",
        passive_deletes=True,
        foreign_keys="[CartItem.cart_id, CartItem.restaurant_id]",
    )

    def __init__(
        self,
        *,
        customer_id: uuid.UUID,
        id: uuid.UUID | None = None,
        restaurant_id: uuid.UUID | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.id = id if id is not None else uuid.uuid4()
        self.customer_id = customer_id
        self.restaurant_id = restaurant_id
        self.created_at = created_at if created_at is not None else utc_now()
        self.updated_at = updated_at if updated_at is not None else utc_now()

    def __repr__(self) -> str:
        return (
            f"<Cart id={self.id} customer_id={self.customer_id} "
            f"restaurant_id={self.restaurant_id}>"
        )


class CartItem(Base):
    """CartItem entity representing a single menu item line and quantity in a cart."""

    __tablename__ = "cart_items"

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    cart_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid,
        nullable=False,
    )
    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid,
        nullable=False,
    )
    menu_item_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid,
        nullable=False,
    )
    quantity: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
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
        sa.Index("ix_cart_items_cart_id", "cart_id"),
        sa.Index("ix_cart_items_menu_item_id", "menu_item_id"),
    )

    # Relationships
    cart: Mapped["Cart"] = relationship(
        "Cart",
        back_populates="items",
        foreign_keys=[cart_id, restaurant_id],
    )
    menu_item: Mapped["MenuItem"] = relationship(
        "MenuItem",
        foreign_keys=[menu_item_id, restaurant_id],
        overlaps="cart,items",
    )

    def __init__(
        self,
        *,
        cart_id: uuid.UUID,
        restaurant_id: uuid.UUID,
        menu_item_id: uuid.UUID,
        quantity: int,
        id: uuid.UUID | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        if quantity <= 0:
            raise ValueError("Quantity must be a positive integer.")
        self.id = id if id is not None else uuid.uuid4()
        self.cart_id = cart_id
        self.restaurant_id = restaurant_id
        self.menu_item_id = menu_item_id
        self.quantity = quantity
        self.created_at = created_at if created_at is not None else utc_now()
        self.updated_at = updated_at if updated_at is not None else utc_now()

    def __repr__(self) -> str:
        return (
            f"<CartItem id={self.id} cart_id={self.cart_id} "
            f"menu_item_id={self.menu_item_id} quantity={self.quantity}>"
        )
