"""Business logic coordinator for restaurant order management operations."""

import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.delivery.enums import DeliveryStatus
from app.delivery.models import Delivery
from app.delivery.repository import DeliveryRepository
from app.identity.enums import UserRole
from app.identity.models import User
from app.orders.enums import OrderStatus
from app.orders.exceptions import (
    InvalidOrderTransitionError,
    OrderNotEligibleError,
    OrderNotFoundError,
)
from app.orders.models import Order
from app.orders.repository import OrderRepository
from app.orders.state_machine import (
    InvalidOrderStateTransitionError,
    can_transition,
)
from app.restaurants.exceptions import (
    RestaurantNotFoundError,
    UnauthorizedRestaurantAccessError,
)
from app.restaurants.repository import RestaurantRepository

# Restaurant-controlled transitions per the existing state machine:
#   CONFIRMED -> ACCEPTED   (restaurant accepts a paid order)
#   ACCEPTED  -> PREPARING  (restaurant starts preparation)
#   PREPARING -> READY_FOR_PICKUP (restaurant marks ready)
#
# Restaurant can also cancel from CONFIRMED, ACCEPTED, PREPARING.
#
# PICKED_UP, OUT_FOR_DELIVERY, DELIVERED are delivery-partner responsibilities.
# PENDING_PAYMENT -> CONFIRMED is payment-system responsibility.

# Statuses from which a restaurant may accept an order
_ACCEPTABLE_STATUSES = frozenset({OrderStatus.CONFIRMED})

# Status transitions the restaurant is permitted to initiate
_RESTAURANT_TRANSITIONS: dict[str, tuple[OrderStatus, OrderStatus]] = {
    "accept": (OrderStatus.CONFIRMED, OrderStatus.ACCEPTED),
    "start_preparing": (OrderStatus.ACCEPTED, OrderStatus.PREPARING),
    "mark_ready": (OrderStatus.PREPARING, OrderStatus.READY_FOR_PICKUP),
}

# Statuses from which a restaurant may cancel an order
_CANCELLABLE_BY_RESTAURANT = frozenset(
    {
        OrderStatus.CONFIRMED,
        OrderStatus.ACCEPTED,
        OrderStatus.PREPARING,
    }
)


class RestaurantOrderService:
    """Service layer for restaurant-side order management.

    Enforces restaurant ownership, role authorization, payment boundaries,
    and state machine transitions.
    """

    def __init__(
        self,
        session: AsyncSession,
        order_repo: OrderRepository | None = None,
        restaurant_repo: RestaurantRepository | None = None,
        delivery_repo: DeliveryRepository | None = None,
    ) -> None:
        self.session = session
        self.order_repo = order_repo or OrderRepository(session)
        self.restaurant_repo = restaurant_repo or RestaurantRepository(session)
        self.delivery_repo = delivery_repo or DeliveryRepository(session)

    async def _verify_restaurant_ownership(
        self,
        user: User,
        restaurant_id: uuid.UUID,
    ) -> None:
        """Verify the user has RESTAURANT role and owns the specified restaurant.

        Raises:
            UnauthorizedRestaurantAccessError: If user lacks RESTAURANT role.
            RestaurantNotFoundError: If restaurant does not exist.
            UnauthorizedRestaurantAccessError: If user does not own the restaurant.
        """
        if user.role != UserRole.RESTAURANT:
            raise UnauthorizedRestaurantAccessError(
                "Only users with RESTAURANT role can manage restaurant orders."
            )
        restaurant = await self.restaurant_repo.get_by_id(restaurant_id)
        if restaurant is None:
            raise RestaurantNotFoundError(
                f"Restaurant with ID '{restaurant_id}' not found."
            )
        if restaurant.owner_id != user.id:
            raise UnauthorizedRestaurantAccessError(
                "You do not have permission to access this restaurant's orders."
            )

    async def list_restaurant_orders(
        self,
        user: User,
        restaurant_id: uuid.UUID,
        skip: int = 0,
        limit: int = 20,
        status: OrderStatus | None = None,
    ) -> tuple[Sequence[Order], int]:
        """List orders for a restaurant owned by the authenticated user.

        Raises:
            UnauthorizedRestaurantAccessError: If ownership check fails.
            RestaurantNotFoundError: If restaurant does not exist.
        """
        await self._verify_restaurant_ownership(user, restaurant_id)
        orders = await self.order_repo.list_by_restaurant_paginated(
            restaurant_id=restaurant_id,
            skip=skip,
            limit=limit,
            status=status,
            include_items=True,
        )
        total = await self.order_repo.count_by_restaurant(
            restaurant_id=restaurant_id,
            status=status,
        )
        return orders, total

    async def get_restaurant_order(
        self,
        user: User,
        restaurant_id: uuid.UUID,
        order_id: uuid.UUID,
    ) -> Order:
        """Retrieve a specific order belonging to the authenticated user's restaurant.

        Raises:
            UnauthorizedRestaurantAccessError: If ownership check fails.
            RestaurantNotFoundError: If restaurant does not exist.
            OrderNotFoundError: If order does not exist or does not belong to the restaurant.
        """
        await self._verify_restaurant_ownership(user, restaurant_id)
        order = await self.order_repo.get_by_id_and_restaurant(
            order_id=order_id,
            restaurant_id=restaurant_id,
            include_items=True,
        )
        if order is None:
            raise OrderNotFoundError(f"Order '{order_id}' not found.")
        return order

    async def accept_order(
        self,
        user: User,
        restaurant_id: uuid.UUID,
        order_id: uuid.UUID,
    ) -> Order:
        """Accept an order that is in CONFIRMED status.

        The order must have been paid (transitioned from PENDING_PAYMENT to CONFIRMED
        by the payment system) before a restaurant can accept it.

        Row-level lock (FOR UPDATE) is acquired to prevent concurrent transition races.

        Raises:
            UnauthorizedRestaurantAccessError: If ownership check fails.
            RestaurantNotFoundError: If restaurant does not exist.
            OrderNotFoundError: If order does not exist or does not belong to the restaurant.
            OrderNotEligibleError: If order is still PENDING_PAYMENT.
            InvalidOrderTransitionError: If transition is not allowed.
        """
        await self._verify_restaurant_ownership(user, restaurant_id)
        order = await self.order_repo.get_by_id_and_restaurant(
            order_id=order_id,
            restaurant_id=restaurant_id,
            include_items=True,
            for_update=True,
        )
        if order is None:
            raise OrderNotFoundError(f"Order '{order_id}' not found.")

        if order.status == OrderStatus.PENDING_PAYMENT:
            raise OrderNotEligibleError(
                "Cannot accept order: payment has not been completed."
            )

        if order.status not in _ACCEPTABLE_STATUSES:
            raise InvalidOrderTransitionError(
                f"Cannot accept order in '{order.status.value}' status. "
                "Only CONFIRMED orders can be accepted."
            )

        try:
            order = await self.order_repo.update_status(
                order, OrderStatus.ACCEPTED, expected_status=OrderStatus.CONFIRMED
            )
        except InvalidOrderStateTransitionError as exc:
            raise InvalidOrderTransitionError(str(exc)) from exc

        return order

    async def start_preparing(
        self,
        user: User,
        restaurant_id: uuid.UUID,
        order_id: uuid.UUID,
    ) -> Order:
        """Transition an ACCEPTED order to PREPARING.

        Raises:
            UnauthorizedRestaurantAccessError: If ownership check fails.
            RestaurantNotFoundError: If restaurant does not exist.
            OrderNotFoundError: If order does not exist or does not belong to the restaurant.
            InvalidOrderTransitionError: If transition is not allowed.
        """
        return await self._perform_restaurant_transition(
            user=user,
            restaurant_id=restaurant_id,
            order_id=order_id,
            action="start_preparing",
        )

    async def mark_ready_for_pickup(
        self,
        user: User,
        restaurant_id: uuid.UUID,
        order_id: uuid.UUID,
    ) -> Order:
        """Transition a PREPARING order to READY_FOR_PICKUP.

        Raises:
            UnauthorizedRestaurantAccessError: If ownership check fails.
            RestaurantNotFoundError: If restaurant does not exist.
            OrderNotFoundError: If order does not exist or does not belong to the restaurant.
            InvalidOrderTransitionError: If transition is not allowed.
        """
        return await self._perform_restaurant_transition(
            user=user,
            restaurant_id=restaurant_id,
            order_id=order_id,
            action="mark_ready",
        )

    async def cancel_order(
        self,
        user: User,
        restaurant_id: uuid.UUID,
        order_id: uuid.UUID,
    ) -> Order:
        """Cancel an order from a restaurant-controlled status.

        Restaurants may cancel orders in CONFIRMED, ACCEPTED, or PREPARING status.
        Terminal statuses and delivery-phase statuses cannot be cancelled by the restaurant.
        Row-level lock (FOR UPDATE) is acquired to prevent concurrent transition races.

        Raises:
            UnauthorizedRestaurantAccessError: If ownership check fails.
            RestaurantNotFoundError: If restaurant does not exist.
            OrderNotFoundError: If order does not exist or does not belong to the restaurant.
            InvalidOrderTransitionError: If cancellation is not allowed from current status.
        """
        await self._verify_restaurant_ownership(user, restaurant_id)
        order = await self.order_repo.get_by_id_and_restaurant(
            order_id=order_id,
            restaurant_id=restaurant_id,
            include_items=True,
            for_update=True,
        )
        if order is None:
            raise OrderNotFoundError(f"Order '{order_id}' not found.")

        if order.status not in _CANCELLABLE_BY_RESTAURANT:
            raise InvalidOrderTransitionError(
                f"Cannot cancel order in '{order.status.value}' status."
            )

        if not can_transition(order.status, OrderStatus.CANCELLED):
            raise InvalidOrderTransitionError(
                f"Cannot cancel order in '{order.status.value}' status."
            )

        current_status = order.status
        try:
            order = await self.order_repo.update_status(
                order, OrderStatus.CANCELLED, expected_status=current_status
            )
        except InvalidOrderStateTransitionError as exc:
            raise InvalidOrderTransitionError(str(exc)) from exc

        return order

    async def _perform_restaurant_transition(
        self,
        user: User,
        restaurant_id: uuid.UUID,
        order_id: uuid.UUID,
        action: str,
    ) -> Order:
        """Execute a named restaurant transition on an order under a row-level lock.

        Raises:
            UnauthorizedRestaurantAccessError: If ownership check fails.
            RestaurantNotFoundError: If restaurant does not exist.
            OrderNotFoundError: If order does not exist or does not belong to the restaurant.
            InvalidOrderTransitionError: If transition is not allowed.
        """
        await self._verify_restaurant_ownership(user, restaurant_id)
        order = await self.order_repo.get_by_id_and_restaurant(
            order_id=order_id,
            restaurant_id=restaurant_id,
            include_items=True,
            for_update=True,
        )
        if order is None:
            raise OrderNotFoundError(f"Order '{order_id}' not found.")

        expected_from, target = _RESTAURANT_TRANSITIONS[action]
        if order.status != expected_from:
            raise InvalidOrderTransitionError(
                f"Cannot perform '{action}' on order in '{order.status.value}' status. "
                f"Expected status: '{expected_from.value}'."
            )

        try:
            order = await self.order_repo.update_status(
                order, target, expected_status=expected_from
            )
        except InvalidOrderStateTransitionError as exc:
            raise InvalidOrderTransitionError(str(exc)) from exc

        # When an order becomes READY_FOR_PICKUP, ensure an unassigned Delivery job is created
        if target == OrderStatus.READY_FOR_PICKUP:
            existing_delivery = await self.delivery_repo.get_by_order_id(order.id)
            if existing_delivery is None:
                new_delivery = Delivery(
                    order_id=order.id,
                    status=DeliveryStatus.UNASSIGNED,
                )
                await self.delivery_repo.create(new_delivery)

        return order
