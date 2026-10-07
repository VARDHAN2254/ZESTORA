"""Order domain module for ZESTORA API."""

from app.orders.enums import OrderStatus
from app.orders.models import Order, OrderItem
from app.orders.repository import OrderRepository
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
    "InvalidOrderStateTransitionError",
    "Order",
    "OrderItem",
    "OrderRepository",
    "OrderStatus",
    "can_transition",
    "transition",
]
