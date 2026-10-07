"""Order state machine defining deterministic lifecycle transitions."""

from app.orders.enums import OrderStatus


class InvalidOrderStateTransitionError(ValueError):
    """Raised when an invalid order lifecycle transition is attempted."""

    def __init__(self, current: OrderStatus, target: OrderStatus) -> None:
        self.current = current
        self.target = target
        super().__init__(
            f"Invalid order transition from '{current.value}' to '{target.value}'."
        )


TERMINAL_STATES: frozenset[OrderStatus] = frozenset(
    {
        OrderStatus.DELIVERED,
        OrderStatus.CANCELLED,
        OrderStatus.FAILED,
    }
)

VALID_TRANSITIONS: dict[OrderStatus, frozenset[OrderStatus]] = {
    OrderStatus.PENDING_PAYMENT: frozenset(
        {
            OrderStatus.CONFIRMED,
            OrderStatus.CANCELLED,
            OrderStatus.FAILED,
        }
    ),
    OrderStatus.CONFIRMED: frozenset(
        {
            OrderStatus.ACCEPTED,
            OrderStatus.CANCELLED,
        }
    ),
    OrderStatus.ACCEPTED: frozenset(
        {
            OrderStatus.PREPARING,
            OrderStatus.CANCELLED,
        }
    ),
    OrderStatus.PREPARING: frozenset(
        {
            OrderStatus.READY_FOR_PICKUP,
            OrderStatus.CANCELLED,
        }
    ),
    OrderStatus.READY_FOR_PICKUP: frozenset(
        {
            OrderStatus.PICKED_UP,
            OrderStatus.CANCELLED,
        }
    ),
    OrderStatus.PICKED_UP: frozenset(
        {
            OrderStatus.OUT_FOR_DELIVERY,
        }
    ),
    OrderStatus.OUT_FOR_DELIVERY: frozenset(
        {
            OrderStatus.DELIVERED,
        }
    ),
    OrderStatus.DELIVERED: frozenset(),
    OrderStatus.CANCELLED: frozenset(),
    OrderStatus.FAILED: frozenset(),
}


def can_transition(current: OrderStatus, target: OrderStatus) -> bool:
    """Return True if transitioning from current to target is allowed."""
    return target in VALID_TRANSITIONS.get(current, frozenset())


def transition(current: OrderStatus, target: OrderStatus) -> OrderStatus:
    """Validate and transition to target status or raise InvalidOrderStateTransitionError."""
    if not can_transition(current, target):
        raise InvalidOrderStateTransitionError(current, target)
    return target
