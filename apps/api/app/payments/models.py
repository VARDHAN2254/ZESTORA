"""SQLAlchemy 2.x declarative domain models for the payment domain."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.payments.enums import PaymentMethod, PaymentStatus

if TYPE_CHECKING:
    from app.orders.models import Order


def utc_now() -> datetime:
    """Return timezone-aware UTC datetime."""
    return datetime.now(UTC)


class Payment(Base):
    """Payment record representing financial transactions associated with an order."""

    __tablename__ = "payments"

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
            name="fk_payments_order_id_orders",
        ),
        nullable=False,
    )
    amount: Mapped[Decimal] = mapped_column(
        sa.Numeric(precision=12, scale=2),
        nullable=False,
    )
    currency: Mapped[str] = mapped_column(
        sa.String(3),
        nullable=False,
        default="INR",
        server_default=sa.text("'INR'"),
    )
    status: Mapped[PaymentStatus] = mapped_column(
        sa.Enum(PaymentStatus, name="payment_status", native_enum=True),
        nullable=False,
        default=PaymentStatus.PENDING,
    )
    payment_method: Mapped[PaymentMethod] = mapped_column(
        sa.Enum(PaymentMethod, name="payment_method", native_enum=True),
        nullable=False,
    )
    provider: Mapped[str | None] = mapped_column(
        sa.String(50),
        nullable=True,
    )
    provider_payment_id: Mapped[str | None] = mapped_column(
        sa.String(255),
        nullable=True,
    )
    idempotency_key: Mapped[str] = mapped_column(
        sa.String(255),
        nullable=False,
    )
    failure_code: Mapped[str | None] = mapped_column(
        sa.String(100),
        nullable=True,
    )
    failure_message: Mapped[str | None] = mapped_column(
        sa.Text,
        nullable=True,
    )
    paid_at: Mapped[datetime | None] = mapped_column(
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
        sa.CheckConstraint(
            "amount >= 0",
            name="ck_payments_amount_non_negative",
        ),
        sa.UniqueConstraint(
            "idempotency_key",
            name="uq_payments_idempotency_key",
        ),
        sa.UniqueConstraint(
            "provider",
            "provider_payment_id",
            name="uq_payments_provider_provider_payment_id",
        ),
        sa.Index("ix_payments_order_id", "order_id"),
        sa.Index("ix_payments_status", "status"),
        sa.Index("ix_payments_provider_payment_id", "provider_payment_id"),
        sa.Index("ix_payments_created_at", "created_at"),
    )

    # Relationships
    order: Mapped["Order"] = relationship(
        "Order",
        back_populates="payments",
    )
    events: Mapped[list["PaymentEvent"]] = relationship(
        "PaymentEvent",
        back_populates="payment",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __init__(
        self,
        *,
        order_id: uuid.UUID,
        amount: Decimal | float | str,
        payment_method: PaymentMethod,
        idempotency_key: str,
        id: uuid.UUID | None = None,
        currency: str = "INR",
        status: PaymentStatus = PaymentStatus.PENDING,
        provider: str | None = None,
        provider_payment_id: str | None = None,
        failure_code: str | None = None,
        failure_message: str | None = None,
        paid_at: datetime | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.id = id if id is not None else uuid.uuid4()
        self.order_id = order_id
        self.amount = Decimal(str(amount))
        self.currency = currency
        self.payment_method = payment_method
        self.status = status
        self.idempotency_key = idempotency_key
        self.provider = provider
        self.provider_payment_id = provider_payment_id
        self.failure_code = failure_code
        self.failure_message = failure_message
        self.paid_at = paid_at
        self.created_at = created_at if created_at is not None else utc_now()
        self.updated_at = updated_at if updated_at is not None else utc_now()

    def __repr__(self) -> str:
        status_val = (
            self.status.value if isinstance(self.status, PaymentStatus) else self.status
        )
        return (
            f"<Payment id={self.id} order_id={self.order_id} "
            f"amount={self.amount} {self.currency} status={status_val} "
            f"method={self.payment_method} provider={self.provider}>"
        )


class PaymentEvent(Base):
    """Immutable audit and webhook record for incoming provider payment events."""

    __tablename__ = "payment_events"

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    payment_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid,
        sa.ForeignKey(
            "payments.id",
            ondelete="RESTRICT",
            name="fk_payment_events_payment_id_payments",
        ),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(
        sa.String(50),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(
        sa.String(100),
        nullable=False,
    )
    provider_event_id: Mapped[str] = mapped_column(
        sa.String(255),
        nullable=False,
    )
    payload: Mapped[dict[str, Any]] = mapped_column(
        postgresql.JSONB,
        nullable=False,
    )
    processed: Mapped[bool] = mapped_column(
        sa.Boolean,
        default=False,
        server_default=sa.false(),
        nullable=False,
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        default=utc_now,
        server_default=sa.func.now(),
        nullable=False,
    )

    __table_args__ = (
        sa.UniqueConstraint(
            "provider",
            "provider_event_id",
            name="uq_payment_events_provider_provider_event_id",
        ),
        sa.Index("ix_payment_events_payment_id", "payment_id"),
        sa.Index("ix_payment_events_provider_event_id", "provider_event_id"),
        sa.Index("ix_payment_events_created_at", "created_at"),
    )

    # Relationship
    payment: Mapped["Payment"] = relationship(
        "Payment",
        back_populates="events",
    )

    def __init__(
        self,
        *,
        payment_id: uuid.UUID,
        provider: str,
        event_type: str,
        provider_event_id: str,
        payload: dict[str, Any],
        id: uuid.UUID | None = None,
        processed: bool = False,
        processed_at: datetime | None = None,
        created_at: datetime | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.id = id if id is not None else uuid.uuid4()
        self.payment_id = payment_id
        self.provider = provider
        self.event_type = event_type
        self.provider_event_id = provider_event_id
        self.payload = payload
        self.processed = processed
        self.processed_at = processed_at
        self.created_at = created_at if created_at is not None else utc_now()

    def __repr__(self) -> str:
        return (
            f"<PaymentEvent id={self.id} payment_id={self.payment_id} "
            f"provider={self.provider!r} event_type={self.event_type!r} "
            f"processed={self.processed}>"
        )
