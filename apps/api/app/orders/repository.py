"""Order repository providing async database operations for orders and items."""

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.orders.enums import OrderStatus
from app.orders.models import Order
from app.orders.state_machine import InvalidOrderStateTransitionError, transition


class OrderRepository:
    """Async repository for querying and persisting Order entities."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(
        self,
        order_id: uuid.UUID,
        include_items: bool = False,
    ) -> Order | None:
        """Retrieve an order by primary key UUID."""
        query = select(Order).where(Order.id == order_id)
        if include_items:
            query = query.options(selectinload(Order.items))
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_id_and_customer(
        self,
        order_id: uuid.UUID,
        customer_id: uuid.UUID,
        include_items: bool = True,
    ) -> Order | None:
        """Retrieve an order ensuring it belongs to the given customer."""
        query = select(Order).where(
            Order.id == order_id,
            Order.customer_id == customer_id,
        )
        if include_items:
            query = query.options(selectinload(Order.items))
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_by_customer(
        self,
        customer_id: uuid.UUID,
        skip: int = 0,
        limit: int | None = None,
        include_items: bool = True,
    ) -> Sequence[Order]:
        """List orders for a customer ordered by created_at descending."""
        query = (
            select(Order)
            .where(Order.customer_id == customer_id)
            .order_by(Order.created_at.desc())
        )
        if include_items:
            query = query.options(selectinload(Order.items))
        if skip > 0:
            query = query.offset(skip)
        if limit is not None:
            query = query.limit(limit)
        result = await self.session.execute(query)
        return result.scalars().all()

    async def count_by_customer(self, customer_id: uuid.UUID) -> int:
        """Count total orders placed by a customer."""
        result = await self.session.execute(
            select(func.count(Order.id)).where(Order.customer_id == customer_id)
        )
        return int(result.scalar_one() or 0)

    async def list_by_restaurant(self, restaurant_id: uuid.UUID) -> Sequence[Order]:
        """List all orders for a restaurant ordered by created_at descending."""
        result = await self.session.execute(
            select(Order)
            .where(Order.restaurant_id == restaurant_id)
            .order_by(Order.created_at.desc())
        )
        return result.scalars().all()

    async def list_by_restaurant_paginated(
        self,
        restaurant_id: uuid.UUID,
        skip: int = 0,
        limit: int | None = None,
        status: OrderStatus | None = None,
        include_items: bool = True,
    ) -> Sequence[Order]:
        """List orders for a restaurant with pagination, optional status filter, and item eager-loading."""
        query = (
            select(Order)
            .where(Order.restaurant_id == restaurant_id)
            .order_by(Order.created_at.desc())
        )
        if status is not None:
            query = query.where(Order.status == status)
        if include_items:
            query = query.options(selectinload(Order.items))
        if skip > 0:
            query = query.offset(skip)
        if limit is not None:
            query = query.limit(limit)
        result = await self.session.execute(query)
        return result.scalars().all()

    async def count_by_restaurant(
        self,
        restaurant_id: uuid.UUID,
        status: OrderStatus | None = None,
    ) -> int:
        """Count total orders for a restaurant, optionally filtered by status."""
        query = select(func.count(Order.id)).where(Order.restaurant_id == restaurant_id)
        if status is not None:
            query = query.where(Order.status == status)
        result = await self.session.execute(query)
        return int(result.scalar_one() or 0)

    async def get_by_id_and_restaurant(
        self,
        order_id: uuid.UUID,
        restaurant_id: uuid.UUID,
        include_items: bool = True,
        for_update: bool = False,
    ) -> Order | None:
        """Retrieve an order scoped to both order ID and restaurant ID.

        Args:
            order_id: Unique order identifier.
            restaurant_id: Unique restaurant identifier.
            include_items: Whether to eagerly load order items.
            for_update: If True, acquire an exclusive row-level lock (FOR UPDATE).
        """
        query = select(Order).where(
            Order.id == order_id,
            Order.restaurant_id == restaurant_id,
        )
        if for_update:
            query = query.with_for_update()
        if include_items:
            query = query.options(selectinload(Order.items))
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def create(self, order: Order) -> Order:
        """Add and flush a new order entity with its items."""
        self.session.add(order)
        await self.session.flush()
        return order

    async def update_status(
        self,
        order: Order,
        new_status: OrderStatus,
        expected_status: OrderStatus | None = None,
    ) -> Order:
        """Transition order status via state machine and flush update.

        Args:
            order: The Order entity to transition.
            new_status: The target OrderStatus.
            expected_status: Optional expected current status. If provided,
                verifies that order.status matches expected_status before transitioning.

        Raises:
            InvalidOrderStateTransitionError: If the transition is invalid
                or current status does not match expected_status.
        """
        if expected_status is not None and order.status != expected_status:
            raise InvalidOrderStateTransitionError(order.status, new_status)
        order.status = transition(order.status, new_status)
        await self.session.flush()
        return order
