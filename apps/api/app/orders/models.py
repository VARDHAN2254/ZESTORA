"""SQLAlchemy 2.x declarative domain models for the order domain."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.orders.enums import OrderStatus

if TYPE_CHECKING:
    from app.catalog.models import MenuItem
    from app.identity.models import User
    from app.payments.models import Payment
    from app.restaurants.models import Restaurant


def utc_now() -> datetime:
    """Return timezone-aware UTC datetime."""
    return datetime.now(UTC)


class Order(Base):
    """Order entity representing customer food orders placed with restaurants."""

    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid,
        sa.ForeignKey(
            "users.id",
            ondelete="RESTRICT",
            name="fk_orders_customer_id_users",
        ),
        nullable=False,
    )
    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid,
        sa.ForeignKey(
            "restaurants.id",
            ondelete="RESTRICT",
            name="fk_orders_restaurant_id_restaurants",
        ),
        nullable=False,
    )
    status: Mapped[OrderStatus] = mapped_column(
        sa.Enum(OrderStatus, name="order_status", native_enum=True),
        nullable=False,
        default=OrderStatus.PENDING_PAYMENT,
    )
    subtotal: Mapped[Decimal] = mapped_column(
        sa.Numeric(precision=12, scale=2),
        nullable=False,
    )
    delivery_fee: Mapped[Decimal] = mapped_column(
        sa.Numeric(precision=12, scale=2),
        nullable=False,
        default=Decimal("0.00"),
        server_default=sa.text("0.00"),
    )
    tax: Mapped[Decimal] = mapped_column(
        sa.Numeric(precision=12, scale=2),
        nullable=False,
        default=Decimal("0.00"),
        server_default=sa.text("0.00"),
    )
    discount: Mapped[Decimal] = mapped_column(
        sa.Numeric(precision=12, scale=2),
        nullable=False,
        default=Decimal("0.00"),
        server_default=sa.text("0.00"),
    )
    total: Mapped[Decimal] = mapped_column(
        sa.Numeric(precision=12, scale=2),
        nullable=False,
    )
    currency: Mapped[str] = mapped_column(
        sa.String(3),
        nullable=False,
        default="INR",
        server_default=sa.text("'INR'"),
    )

    # Historical delivery address snapshot
    delivery_address_line1: Mapped[str] = mapped_column(
        sa.String(255),
        nullable=False,
    )
    delivery_address_line2: Mapped[str | None] = mapped_column(
        sa.String(255),
        nullable=True,
    )
    delivery_city: Mapped[str] = mapped_column(
        sa.String(100),
        nullable=False,
    )
    delivery_state: Mapped[str] = mapped_column(
        sa.String(100),
        nullable=False,
    )
    delivery_postal_code: Mapped[str] = mapped_column(
        sa.String(20),
        nullable=False,
    )
    delivery_latitude: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(precision=9, scale=6),
        nullable=True,
    )
    delivery_longitude: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(precision=9, scale=6),
        nullable=True,
    )
    notes: Mapped[str | None] = mapped_column(
        sa.Text,
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
        sa.Index("ix_orders_customer_id", "customer_id"),
        sa.Index("ix_orders_restaurant_id", "restaurant_id"),
        sa.Index("ix_orders_status", "status"),
        sa.Index("ix_orders_created_at", "created_at"),
    )

    # Relationships
    customer: Mapped["User"] = relationship(
        "User",
        back_populates="orders",
    )
    restaurant: Mapped["Restaurant"] = relationship(
        "Restaurant",
        back_populates="orders",
    )
    items: Mapped[list["OrderItem"]] = relationship(
        "OrderItem",
        back_populates="order",
        cascade="all, delete-orphan",
        passive_deletes=True,
        foreign_keys="[OrderItem.order_id, OrderItem.restaurant_id]",
    )
    payments: Mapped[list["Payment"]] = relationship(
        "Payment",
        back_populates="order",
    )

    def __init__(
        self,
        *,
        customer_id: uuid.UUID,
        restaurant_id: uuid.UUID,
        subtotal: Decimal | float | str,
        total: Decimal | float | str,
        delivery_address_line1: str,
        delivery_city: str,
        delivery_state: str,
        delivery_postal_code: str,
        id: uuid.UUID | None = None,
        status: OrderStatus = OrderStatus.PENDING_PAYMENT,
        delivery_fee: Decimal | float | str = Decimal("0.00"),
        tax: Decimal | float | str = Decimal("0.00"),
        discount: Decimal | float | str = Decimal("0.00"),
        currency: str = "INR",
        delivery_address_line2: str | None = None,
        delivery_latitude: Decimal | float | None = None,
        delivery_longitude: Decimal | float | None = None,
        notes: str | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.id = id if id is not None else uuid.uuid4()
        self.customer_id = customer_id
        self.restaurant_id = restaurant_id
        self.status = status
        self.subtotal = Decimal(str(subtotal))
        self.delivery_fee = Decimal(str(delivery_fee))
        self.tax = Decimal(str(tax))
        self.discount = Decimal(str(discount))
        self.total = Decimal(str(total))
        self.currency = currency
        self.delivery_address_line1 = delivery_address_line1
        self.delivery_address_line2 = delivery_address_line2
        self.delivery_city = delivery_city
        self.delivery_state = delivery_state
        self.delivery_postal_code = delivery_postal_code
        self.delivery_latitude = (
            Decimal(str(delivery_latitude)) if delivery_latitude is not None else None
        )
        self.delivery_longitude = (
            Decimal(str(delivery_longitude)) if delivery_longitude is not None else None
        )
        self.notes = notes
        self.created_at = created_at if created_at is not None else utc_now()
        self.updated_at = updated_at if updated_at is not None else utc_now()

    def __repr__(self) -> str:
        status_val = (
            self.status.value if isinstance(self.status, OrderStatus) else self.status
        )
        return (
            f"<Order id={self.id} customer_id={self.customer_id} "
            f"restaurant_id={self.restaurant_id} status={status_val} "
            f"total={self.total} {self.currency}>"
        )


class OrderItem(Base):
    """OrderItem entity storing historical snapshot of purchased menu items."""

    __tablename__ = "order_items"

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
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
    unit_price: Mapped[Decimal] = mapped_column(
        sa.Numeric(precision=12, scale=2),
        nullable=False,
    )
    line_total: Mapped[Decimal] = mapped_column(
        sa.Numeric(precision=12, scale=2),
        nullable=False,
    )
    item_name: Mapped[str] = mapped_column(
        sa.String(255),
        nullable=False,
    )
    item_description: Mapped[str | None] = mapped_column(
        sa.Text,
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
        sa.Index("ix_order_items_order_id", "order_id"),
        sa.Index("ix_order_items_menu_item_id", "menu_item_id"),
    )

    # Relationships
    order: Mapped["Order"] = relationship(
        "Order",
        back_populates="items",
        foreign_keys=[order_id, restaurant_id],
    )
    menu_item: Mapped["MenuItem"] = relationship(
        "MenuItem",
        foreign_keys=[menu_item_id, restaurant_id],
        overlaps="items,order",
    )

    def __init__(
        self,
        *,
        order_id: uuid.UUID,
        restaurant_id: uuid.UUID,
        menu_item_id: uuid.UUID,
        quantity: int,
        unit_price: Decimal | float | str,
        line_total: Decimal | float | str,
        item_name: str,
        id: uuid.UUID | None = None,
        item_description: str | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.id = id if id is not None else uuid.uuid4()
        self.order_id = order_id
        self.restaurant_id = restaurant_id
        self.menu_item_id = menu_item_id
        self.quantity = quantity
        self.unit_price = Decimal(str(unit_price))
        self.line_total = Decimal(str(line_total))
        self.item_name = item_name
        self.item_description = item_description
        self.created_at = created_at if created_at is not None else utc_now()
        self.updated_at = updated_at if updated_at is not None else utc_now()

    def __repr__(self) -> str:
        return (
            f"<OrderItem id={self.id} order_id={self.order_id} "
            f"item_name={self.item_name!r} qty={self.quantity} "
            f"line_total={self.line_total}>"
        )
