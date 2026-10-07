"""Payment repository providing async database operations for payments and payment events."""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.payments.enums import PaymentStatus
from app.payments.models import Payment, PaymentEvent
from app.payments.state_machine import transition


class PaymentRepository:
    """Async repository for Payment and PaymentEvent persistence."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, payment_id: uuid.UUID) -> Payment | None:
        """Retrieve a payment by its primary key UUID."""
        result = await self.session.execute(
            select(Payment).where(Payment.id == payment_id)
        )
        return result.scalar_one_or_none()

    async def get_by_order_id(self, order_id: uuid.UUID) -> Sequence[Payment]:
        """List all payments associated with an order, ordered by created_at descending."""
        result = await self.session.execute(
            select(Payment)
            .where(Payment.order_id == order_id)
            .order_by(Payment.created_at.desc())
        )
        return result.scalars().all()

    async def get_by_idempotency_key(self, idempotency_key: str) -> Payment | None:
        """Retrieve a payment by its idempotency key."""
        result = await self.session.execute(
            select(Payment).where(Payment.idempotency_key == idempotency_key)
        )
        return result.scalar_one_or_none()

    async def get_event_by_provider_event_id(
        self, provider: str, provider_event_id: str
    ) -> PaymentEvent | None:
        """Retrieve a webhook event record by provider and provider event ID."""
        result = await self.session.execute(
            select(PaymentEvent).where(
                PaymentEvent.provider == provider,
                PaymentEvent.provider_event_id == provider_event_id,
            )
        )
        return result.scalar_one_or_none()

    async def create(self, payment: Payment) -> Payment:
        """Persist a new payment record."""
        self.session.add(payment)
        await self.session.flush()
        return payment

    async def update_status(
        self,
        payment: Payment,
        new_status: PaymentStatus,
        *,
        failure_code: str | None = None,
        failure_message: str | None = None,
        paid_at: datetime | None = None,
    ) -> Payment:
        """Transition payment status via state machine, update failure/paid timestamps, and flush."""
        validated_status = transition(payment.status, new_status)
        payment.status = validated_status

        if failure_code is not None:
            payment.failure_code = failure_code
        if failure_message is not None:
            payment.failure_message = failure_message

        if new_status == PaymentStatus.CAPTURED:
            payment.paid_at = paid_at or datetime.now(UTC)

        await self.session.flush()
        return payment

    async def record_event(self, event: PaymentEvent) -> PaymentEvent:
        """Persist a new payment event audit record."""
        self.session.add(event)
        await self.session.flush()
        return event
