"""Delivery repository providing async database operations for deliveries and delivery partners."""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.delivery.enums import (
    DeliveryPartnerAvailability,
    DeliveryPartnerStatus,
    DeliveryStatus,
)
from app.delivery.models import Delivery, DeliveryPartner
from app.delivery.state_machine import transition


class DeliveryRepository:
    """Async repository for Delivery and DeliveryPartner persistence."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, delivery_id: uuid.UUID) -> Delivery | None:
        """Retrieve a delivery by its primary key UUID."""
        result = await self.session.execute(
            select(Delivery).where(Delivery.id == delivery_id)
        )
        return result.scalar_one_or_none()

    async def get_by_order_id(self, order_id: uuid.UUID) -> Delivery | None:
        """Retrieve the delivery for an order."""
        result = await self.session.execute(
            select(Delivery).where(Delivery.order_id == order_id)
        )
        return result.scalar_one_or_none()

    async def get_by_partner_id(
        self, delivery_partner_id: uuid.UUID
    ) -> Sequence[Delivery]:
        """List all deliveries assigned to a partner, ordered by created_at descending."""
        result = await self.session.execute(
            select(Delivery)
            .where(Delivery.delivery_partner_id == delivery_partner_id)
            .order_by(Delivery.created_at.desc())
        )
        return result.scalars().all()

    async def get_partner_by_id(self, partner_id: uuid.UUID) -> DeliveryPartner | None:
        """Retrieve a delivery partner by their primary key UUID."""
        result = await self.session.execute(
            select(DeliveryPartner).where(DeliveryPartner.id == partner_id)
        )
        return result.scalar_one_or_none()

    async def get_partner_by_user_id(
        self, user_id: uuid.UUID
    ) -> DeliveryPartner | None:
        """Retrieve a delivery partner by their associated user ID."""
        result = await self.session.execute(
            select(DeliveryPartner).where(DeliveryPartner.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def list_available_partners(self) -> Sequence[DeliveryPartner]:
        """List all active and available delivery partners."""
        result = await self.session.execute(
            select(DeliveryPartner).where(
                DeliveryPartner.status == DeliveryPartnerStatus.ACTIVE,
                DeliveryPartner.availability == DeliveryPartnerAvailability.AVAILABLE,
            )
        )
        return result.scalars().all()

    async def create_partner(self, partner: DeliveryPartner) -> DeliveryPartner:
        """Persist a new delivery partner profile."""
        self.session.add(partner)
        await self.session.flush()
        return partner

    async def create(self, delivery: Delivery) -> Delivery:
        """Persist a new delivery record."""
        self.session.add(delivery)
        await self.session.flush()
        return delivery

    async def assign_partner(
        self,
        delivery: Delivery,
        delivery_partner_id: uuid.UUID,
        *,
        assigned_at: datetime | None = None,
    ) -> Delivery:
        """Assign a delivery partner to the delivery, transition to ASSIGNED, and flush."""
        validated_status = transition(delivery.status, DeliveryStatus.ASSIGNED)
        delivery.status = validated_status
        delivery.delivery_partner_id = delivery_partner_id
        delivery.assigned_at = assigned_at or datetime.now(UTC)
        await self.session.flush()
        return delivery

    async def update_status(
        self,
        delivery: Delivery,
        new_status: DeliveryStatus,
        *,
        timestamp: datetime | None = None,
    ) -> Delivery:
        """Transition delivery status via state machine, update lifecycle timestamps, and flush."""
        validated_status = transition(delivery.status, new_status)
        delivery.status = validated_status

        ts = timestamp or datetime.now(UTC)
        if new_status == DeliveryStatus.PICKED_UP:
            delivery.picked_up_at = ts
        elif new_status == DeliveryStatus.DELIVERED:
            delivery.delivered_at = ts
        elif new_status == DeliveryStatus.CANCELLED:
            delivery.cancelled_at = ts

        await self.session.flush()
        return delivery
