"""Delivery repository providing async database operations for deliveries and delivery partners."""

import inspect
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.delivery.enums import (
    DeliveryPartnerAvailability,
    DeliveryPartnerStatus,
    DeliveryStatus,
)
from app.delivery.models import Delivery, DeliveryPartner
from app.delivery.state_machine import InvalidDeliveryStateTransitionError, transition
from app.orders.enums import OrderStatus
from app.orders.models import Order


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

    async def get_by_id_with_details(
        self, delivery_id: uuid.UUID, for_update: bool = False
    ) -> Delivery | None:
        """Retrieve a delivery with related order, items, and restaurant eagerly loaded.

        If for_update is True, applies SELECT ... FOR UPDATE row-level lock.
        """
        query = (
            select(Delivery)
            .where(Delivery.id == delivery_id)
            .options(
                selectinload(Delivery.order).selectinload(Order.items),
                selectinload(Delivery.order).selectinload(Order.restaurant),
            )
        )
        if for_update:
            query = query.with_for_update()
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_id_and_partner(
        self,
        delivery_id: uuid.UUID,
        partner_id: uuid.UUID,
        for_update: bool = False,
    ) -> Delivery | None:
        """Retrieve a delivery scoped to both delivery ID and partner ID.

        If for_update is True, applies SELECT ... FOR UPDATE row-level lock.
        """
        query = (
            select(Delivery)
            .where(
                Delivery.id == delivery_id,
                Delivery.delivery_partner_id == partner_id,
            )
            .options(
                selectinload(Delivery.order).selectinload(Order.items),
                selectinload(Delivery.order).selectinload(Order.restaurant),
            )
        )
        if for_update:
            query = query.with_for_update()
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_order_id(self, order_id: uuid.UUID) -> Delivery | None:
        """Retrieve the delivery for an order."""
        result = await self.session.execute(
            select(Delivery).where(Delivery.order_id == order_id)
        )
        res = result.scalar_one_or_none()
        if inspect.isawaitable(res):
            res = await res
        return res if isinstance(res, Delivery) or res is None else None

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

    async def list_available_deliveries(
        self, skip: int = 0, limit: int = 20
    ) -> Sequence[Delivery]:
        """List available, unassigned deliveries where the order is ready for pickup."""
        query = (
            select(Delivery)
            .join(Order, Delivery.order_id == Order.id)
            .where(
                Delivery.status == DeliveryStatus.UNASSIGNED,
                Delivery.delivery_partner_id.is_(None),
                Order.status == OrderStatus.READY_FOR_PICKUP,
            )
            .order_by(Delivery.created_at.asc())
            .options(
                selectinload(Delivery.order).selectinload(Order.items),
                selectinload(Delivery.order).selectinload(Order.restaurant),
            )
        )
        if skip > 0:
            query = query.offset(skip)
        if limit is not None:
            query = query.limit(limit)
        result = await self.session.execute(query)
        return result.scalars().all()

    async def count_available_deliveries(self) -> int:
        """Count total available, unassigned deliveries where the order is ready for pickup."""
        query = (
            select(func.count(Delivery.id))
            .join(Order, Delivery.order_id == Order.id)
            .where(
                Delivery.status == DeliveryStatus.UNASSIGNED,
                Delivery.delivery_partner_id.is_(None),
                Order.status == OrderStatus.READY_FOR_PICKUP,
            )
        )
        result = await self.session.execute(query)
        return int(result.scalar_one() or 0)

    async def list_by_partner_paginated(
        self,
        partner_id: uuid.UUID,
        skip: int = 0,
        limit: int = 20,
        status: DeliveryStatus | None = None,
    ) -> Sequence[Delivery]:
        """List deliveries assigned to a partner with pagination and optional status filter."""
        query = (
            select(Delivery)
            .where(Delivery.delivery_partner_id == partner_id)
            .order_by(Delivery.created_at.desc())
            .options(
                selectinload(Delivery.order).selectinload(Order.items),
                selectinload(Delivery.order).selectinload(Order.restaurant),
            )
        )
        if status is not None:
            query = query.where(Delivery.status == status)
        if skip > 0:
            query = query.offset(skip)
        if limit is not None:
            query = query.limit(limit)
        result = await self.session.execute(query)
        return result.scalars().all()

    async def count_by_partner(
        self,
        partner_id: uuid.UUID,
        status: DeliveryStatus | None = None,
    ) -> int:
        """Count total deliveries assigned to a partner, optionally filtered by status."""
        query = select(func.count(Delivery.id)).where(
            Delivery.delivery_partner_id == partner_id
        )
        if status is not None:
            query = query.where(Delivery.status == status)
        result = await self.session.execute(query)
        return int(result.scalar_one() or 0)

    async def get_active_delivery_for_partner(
        self, partner_id: uuid.UUID
    ) -> Delivery | None:
        """Retrieve the partner's currently active delivery, if one exists."""
        active_statuses = [
            DeliveryStatus.ASSIGNED,
            DeliveryStatus.PICKED_UP,
            DeliveryStatus.OUT_FOR_DELIVERY,
        ]
        query = (
            select(Delivery)
            .where(
                Delivery.delivery_partner_id == partner_id,
                Delivery.status.in_(active_statuses),
            )
            .options(
                selectinload(Delivery.order).selectinload(Order.items),
                selectinload(Delivery.order).selectinload(Order.restaurant),
            )
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

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
        res = self.session.add(partner)
        if inspect.isawaitable(res):
            await res
        await self.session.flush()
        return partner

    async def update_partner_availability(
        self,
        partner: DeliveryPartner,
        availability: DeliveryPartnerAvailability,
    ) -> DeliveryPartner:
        """Update a partner's availability status."""
        partner.availability = availability
        await self.session.flush()
        return partner

    async def create(self, delivery: Delivery) -> Delivery:
        """Persist a new delivery record."""
        res = self.session.add(delivery)
        if inspect.isawaitable(res):
            await res
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

    async def assign_partner_atomic(
        self,
        delivery: Delivery,
        delivery_partner_id: uuid.UUID,
        *,
        expected_status: DeliveryStatus | None = None,
        assigned_at: datetime | None = None,
    ) -> Delivery:
        """Atomically assign a delivery partner with expected status verification."""
        if expected_status is not None and delivery.status != expected_status:
            raise InvalidDeliveryStateTransitionError(
                delivery.status, DeliveryStatus.ASSIGNED
            )
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
        expected_status: DeliveryStatus | None = None,
        timestamp: datetime | None = None,
    ) -> Delivery:
        """Transition delivery status via state machine, update lifecycle timestamps, and flush.

        If expected_status is provided, verifies that delivery.status matches before transitioning.
        """
        if expected_status is not None and delivery.status != expected_status:
            raise InvalidDeliveryStateTransitionError(delivery.status, new_status)

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
