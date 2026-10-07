"""Order repository providing async database operations for orders and items."""

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.orders.enums import OrderStatus
from app.orders.models import Order
from app.orders.state_machine import transition


class OrderRepository:
    """Async repository for querying and persisting Order entities."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, order_id: uuid.UUID) -> Order | None:
        """Retrieve an order by primary key UUID."""
        result = await self.session.execute(select(Order).where(Order.id == order_id))
        return result.scalar_one_or_none()

    async def list_by_customer(self, customer_id: uuid.UUID) -> Sequence[Order]:
        """List all orders for a customer ordered by created_at descending."""
        result = await self.session.execute(
            select(Order)
            .where(Order.customer_id == customer_id)
            .order_by(Order.created_at.desc())
        )
        return result.scalars().all()

    async def list_by_restaurant(self, restaurant_id: uuid.UUID) -> Sequence[Order]:
        """List all orders for a restaurant ordered by created_at descending."""
        result = await self.session.execute(
            select(Order)
            .where(Order.restaurant_id == restaurant_id)
            .order_by(Order.created_at.desc())
        )
        return result.scalars().all()

    async def create(self, order: Order) -> Order:
        """Add and flush a new order entity with its items."""
        self.session.add(order)
        await self.session.flush()
        return order

    async def update_status(self, order: Order, new_status: OrderStatus) -> Order:
        """Transition order status via state machine and flush update."""
        order.status = transition(order.status, new_status)
        await self.session.flush()
        return order
