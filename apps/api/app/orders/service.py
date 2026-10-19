"""Business logic coordinator for customer order operations."""

import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.enums import UserRole
from app.identity.models import User
from app.orders.exceptions import OrderNotFoundError, UnauthorizedOrderAccessError
from app.orders.models import Order
from app.orders.repository import OrderRepository


class OrderService:
    """Service layer enforcing customer order access policies."""

    def __init__(
        self,
        session: AsyncSession,
        repo: OrderRepository | None = None,
    ) -> None:
        self.session = session
        self.repo = repo or OrderRepository(session)

    @staticmethod
    def _validate_customer(user: User) -> None:
        """Enforce that only users with CUSTOMER role can access customer orders."""
        if user.role != UserRole.CUSTOMER:
            role_val = (
                user.role.value if isinstance(user.role, UserRole) else str(user.role)
            )
            raise UnauthorizedOrderAccessError(
                f"User with role '{role_val}' cannot access customer orders. "
                "Only CUSTOMER accounts are allowed."
            )

    async def list_customer_orders(
        self,
        customer: User,
        skip: int = 0,
        limit: int = 20,
    ) -> tuple[Sequence[Order], int]:
        """List orders belonging strictly to the authenticated customer."""
        self._validate_customer(customer)
        orders = await self.repo.list_by_customer(
            customer.id,
            skip=skip,
            limit=limit,
            include_items=True,
        )
        total = await self.repo.count_by_customer(customer.id)
        return orders, total

    async def get_customer_order(
        self,
        customer: User,
        order_id: uuid.UUID,
    ) -> Order:
        """Retrieve an order belonging strictly to the authenticated customer.

        Raises:
            OrderNotFoundError: If order does not exist or does not belong to the caller.
        """
        self._validate_customer(customer)
        order = await self.repo.get_by_id_and_customer(
            order_id=order_id,
            customer_id=customer.id,
            include_items=True,
        )
        if order is None:
            raise OrderNotFoundError(f"Order '{order_id}' not found.")
        return order
