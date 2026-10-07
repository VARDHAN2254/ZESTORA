"""SQLAlchemy 2.x declarative domain models for the restaurant domain."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.restaurants.enums import RestaurantStatus

if TYPE_CHECKING:
    from app.catalog.models import MenuCategory, MenuItem
    from app.identity.models import User


def utc_now() -> datetime:
    """Return timezone-aware UTC datetime."""
    return datetime.now(UTC)


class Restaurant(Base):
    """Restaurant entity representing onboarded restaurant profiles."""

    __tablename__ = "restaurants"

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid,
        sa.ForeignKey(
            "users.id",
            ondelete="RESTRICT",
            name="fk_restaurants_owner_id_users",
        ),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(
        sa.String(255),
        nullable=False,
    )
    slug: Mapped[str] = mapped_column(
        sa.String(255),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(
        sa.Text,
        nullable=True,
    )
    phone: Mapped[str] = mapped_column(
        sa.String(30),
        nullable=False,
    )
    address_line1: Mapped[str] = mapped_column(
        sa.String(255),
        nullable=False,
    )
    address_line2: Mapped[str | None] = mapped_column(
        sa.String(255),
        nullable=True,
    )
    city: Mapped[str] = mapped_column(
        sa.String(100),
        nullable=False,
    )
    state: Mapped[str] = mapped_column(
        sa.String(100),
        nullable=False,
    )
    postal_code: Mapped[str] = mapped_column(
        sa.String(20),
        nullable=False,
    )
    latitude: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(precision=9, scale=6),
        nullable=True,
    )
    longitude: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(precision=9, scale=6),
        nullable=True,
    )
    status: Mapped[RestaurantStatus] = mapped_column(
        sa.Enum(RestaurantStatus, name="restaurant_status", native_enum=True),
        nullable=False,
        default=RestaurantStatus.ACTIVE,
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
        sa.UniqueConstraint("slug", name="uq_restaurants_slug"),
        sa.Index("ix_restaurants_owner_id", "owner_id"),
        sa.Index("ix_restaurants_status", "status"),
    )

    # Relationships
    owner: Mapped["User"] = relationship(
        "User",
        back_populates="restaurants",
    )
    categories: Mapped[list["MenuCategory"]] = relationship(
        "MenuCategory",
        back_populates="restaurant",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    menu_items: Mapped[list["MenuItem"]] = relationship(
        "MenuItem",
        back_populates="restaurant",
        cascade="all, delete-orphan",
        passive_deletes=True,
        foreign_keys="MenuItem.restaurant_id",
    )

    def __init__(
        self,
        *,
        owner_id: uuid.UUID,
        name: str,
        slug: str,
        phone: str,
        address_line1: str,
        city: str,
        state: str,
        postal_code: str,
        id: uuid.UUID | None = None,
        description: str | None = None,
        address_line2: str | None = None,
        latitude: Decimal | float | None = None,
        longitude: Decimal | float | None = None,
        status: RestaurantStatus = RestaurantStatus.ACTIVE,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.id = id if id is not None else uuid.uuid4()
        self.owner_id = owner_id
        self.name = name
        self.slug = slug
        self.phone = phone
        self.address_line1 = address_line1
        self.city = city
        self.state = state
        self.postal_code = postal_code
        self.description = description
        self.address_line2 = address_line2
        self.latitude = Decimal(str(latitude)) if latitude is not None else None
        self.longitude = Decimal(str(longitude)) if longitude is not None else None
        self.status = status
        self.created_at = created_at if created_at is not None else utc_now()
        self.updated_at = updated_at if updated_at is not None else utc_now()

    def __repr__(self) -> str:
        """Safe string representation of Restaurant."""
        status_val = (
            self.status.value
            if isinstance(self.status, RestaurantStatus)
            else self.status
        )
        return (
            f"<Restaurant id={self.id} slug={self.slug!r} "
            f"name={self.name!r} status={status_val}>"
        )
