"""SQLAlchemy 2.x declarative domain models for the delivery domain."""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.delivery.enums import (
    DeliveryPartnerAvailability,
    DeliveryPartnerStatus,
    DeliveryStatus,
    VehicleType,
)

if TYPE_CHECKING:
    from app.identity.models import User
    from app.orders.models import Order


def utc_now() -> datetime:
    """Return timezone-aware UTC datetime."""
    return datetime.now(UTC)


class DeliveryPartner(Base):
    """Delivery partner profile linked to a platform user account."""

    __tablename__ = "delivery_partners"

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid,
        sa.ForeignKey(
            "users.id",
            ondelete="RESTRICT",
            name="fk_delivery_partners_user_id_users",
        ),
        nullable=False,
    )
    status: Mapped[DeliveryPartnerStatus] = mapped_column(
        sa.Enum(
            DeliveryPartnerStatus,
            name="delivery_partner_status",
            native_enum=True,
        ),
        nullable=False,
        default=DeliveryPartnerStatus.ACTIVE,
    )
    availability: Mapped[DeliveryPartnerAvailability] = mapped_column(
        sa.Enum(
            DeliveryPartnerAvailability,
            name="delivery_partner_availability",
            native_enum=True,
        ),
        nullable=False,
        default=DeliveryPartnerAvailability.UNAVAILABLE,
    )
    vehicle_type: Mapped[VehicleType | None] = mapped_column(
        sa.Enum(
            VehicleType,
            name="vehicle_type",
            native_enum=True,
        ),
        nullable=True,
    )
    vehicle_identifier: Mapped[str | None] = mapped_column(
        sa.String(100),
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
            "user_id",
            name="uq_delivery_partners_user_id",
        ),
        sa.Index("ix_delivery_partners_status", "status"),
        sa.Index("ix_delivery_partners_availability", "availability"),
    )

    # Relationships
    user: Mapped["User"] = relationship(
        "User",
        back_populates="delivery_partner",
    )
    deliveries: Mapped[list["Delivery"]] = relationship(
        "Delivery",
        back_populates="delivery_partner",
    )

    def __init__(
        self,
        *,
        user_id: uuid.UUID,
        id: uuid.UUID | None = None,
        status: DeliveryPartnerStatus = DeliveryPartnerStatus.ACTIVE,
        availability: DeliveryPartnerAvailability = DeliveryPartnerAvailability.UNAVAILABLE,
        vehicle_type: VehicleType | None = None,
        vehicle_identifier: str | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.id = id if id is not None else uuid.uuid4()
        self.user_id = user_id
        self.status = status
        self.availability = availability
        self.vehicle_type = vehicle_type
        self.vehicle_identifier = vehicle_identifier
        self.created_at = created_at if created_at is not None else utc_now()
        self.updated_at = updated_at if updated_at is not None else utc_now()

    def __repr__(self) -> str:
        status_val = (
            self.status.value
            if isinstance(self.status, DeliveryPartnerStatus)
            else self.status
        )
        avail_val = (
            self.availability.value
            if isinstance(self.availability, DeliveryPartnerAvailability)
            else self.availability
        )
        return (
            f"<DeliveryPartner id={self.id} user_id={self.user_id} "
            f"status={status_val} availability={avail_val}>"
        )


class Delivery(Base):
    """Delivery record managing assignment and delivery lifecycle for an order."""

    __tablename__ = "deliveries"

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid,
        sa.ForeignKey(
            "orders.id",
            ondelete="RESTRICT",
            name="fk_deliveries_order_id_orders",
        ),
        nullable=False,
    )
    delivery_partner_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid,
        sa.ForeignKey(
            "delivery_partners.id",
            ondelete="RESTRICT",
            name="fk_deliveries_delivery_partner_id_delivery_partners",
        ),
        nullable=True,
    )
    status: Mapped[DeliveryStatus] = mapped_column(
        sa.Enum(
            DeliveryStatus,
            name="delivery_status",
            native_enum=True,
        ),
        nullable=False,
        default=DeliveryStatus.UNASSIGNED,
    )
    assigned_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
    )
    picked_up_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
    )
    delivered_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
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
            "order_id",
            name="uq_deliveries_order_id",
        ),
        sa.Index("ix_deliveries_delivery_partner_id", "delivery_partner_id"),
        sa.Index("ix_deliveries_status", "status"),
        sa.Index("ix_deliveries_created_at", "created_at"),
    )

    # Relationships
    order: Mapped["Order"] = relationship(
        "Order",
        back_populates="delivery",
    )
    delivery_partner: Mapped["DeliveryPartner | None"] = relationship(
        "DeliveryPartner",
        back_populates="deliveries",
    )

    def __init__(
        self,
        *,
        order_id: uuid.UUID,
        id: uuid.UUID | None = None,
        delivery_partner_id: uuid.UUID | None = None,
        status: DeliveryStatus = DeliveryStatus.UNASSIGNED,
        assigned_at: datetime | None = None,
        picked_up_at: datetime | None = None,
        delivered_at: datetime | None = None,
        cancelled_at: datetime | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.id = id if id is not None else uuid.uuid4()
        self.order_id = order_id
        self.delivery_partner_id = delivery_partner_id
        self.status = status
        self.assigned_at = assigned_at
        self.picked_up_at = picked_up_at
        self.delivered_at = delivered_at
        self.cancelled_at = cancelled_at
        self.created_at = created_at if created_at is not None else utc_now()
        self.updated_at = updated_at if updated_at is not None else utc_now()

    def __repr__(self) -> str:
        status_val = (
            self.status.value
            if isinstance(self.status, DeliveryStatus)
            else self.status
        )
        return (
            f"<Delivery id={self.id} order_id={self.order_id} "
            f"delivery_partner_id={self.delivery_partner_id} status={status_val}>"
        )
