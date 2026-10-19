"""Order domain module for ZESTORA API."""

from app.orders.enums import OrderStatus
from app.orders.exceptions import (
    OrderError,
    OrderNotFoundError,
    UnauthorizedOrderAccessError,
)
from app.orders.models import Order, OrderItem
from app.orders.repository import OrderRepository
from app.orders.router import router as orders_router
from app.orders.schemas import (
    DeliveryAddressResponse,
    OrderItemResponse,
    OrderListResponse,
    OrderResponse,
)
from app.orders.service import OrderService
from app.orders.state_machine import (
    TERMINAL_STATES,
    VALID_TRANSITIONS,
    InvalidOrderStateTransitionError,
    can_transition,
    transition,
)

__all__ = [
    "TERMINAL_STATES",
    "VALID_TRANSITIONS",
    "DeliveryAddressResponse",
    "InvalidOrderStateTransitionError",
    "Order",
    "OrderError",
    "OrderItem",
    "OrderItemResponse",
    "OrderListResponse",
    "OrderNotFoundError",
    "OrderRepository",
    "OrderResponse",
    "OrderService",
    "OrderStatus",
    "UnauthorizedOrderAccessError",
    "can_transition",
    "orders_router",
    "transition",
]
