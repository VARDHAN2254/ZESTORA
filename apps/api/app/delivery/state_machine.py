"""Delivery lifecycle state machine and deterministic transition logic."""

from app.delivery.enums import DeliveryStatus


class InvalidDeliveryStateTransitionError(ValueError):
    """Raised when an illegal delivery state transition is attempted."""

    def __init__(self, current: DeliveryStatus, target: DeliveryStatus) -> None:
        self.current = current
        self.target = target
        super().__init__(
            f"Cannot transition delivery from {current.value} to {target.value}"
        )


TERMINAL_STATES: frozenset[DeliveryStatus] = frozenset(
    {
        DeliveryStatus.DELIVERED,
        DeliveryStatus.CANCELLED,
        DeliveryStatus.FAILED,
    }
)

VALID_TRANSITIONS: dict[DeliveryStatus, frozenset[DeliveryStatus]] = {
    DeliveryStatus.UNASSIGNED: frozenset(
        {
            DeliveryStatus.ASSIGNED,
            DeliveryStatus.CANCELLED,
            DeliveryStatus.FAILED,
        }
    ),
    DeliveryStatus.ASSIGNED: frozenset(
        {
            DeliveryStatus.PICKED_UP,
            DeliveryStatus.UNASSIGNED,
            DeliveryStatus.CANCELLED,
            DeliveryStatus.FAILED,
        }
    ),
    DeliveryStatus.PICKED_UP: frozenset(
        {
            DeliveryStatus.OUT_FOR_DELIVERY,
            DeliveryStatus.CANCELLED,
            DeliveryStatus.FAILED,
        }
    ),
    DeliveryStatus.OUT_FOR_DELIVERY: frozenset(
        {
            DeliveryStatus.DELIVERED,
            DeliveryStatus.CANCELLED,
            DeliveryStatus.FAILED,
        }
    ),
    DeliveryStatus.DELIVERED: frozenset(),
    DeliveryStatus.CANCELLED: frozenset(),
    DeliveryStatus.FAILED: frozenset(),
}


def can_transition(current: DeliveryStatus, target: DeliveryStatus) -> bool:
    """Return True if transition from current to target status is valid."""
    if current in TERMINAL_STATES:
        return False
    return target in VALID_TRANSITIONS.get(current, frozenset())


def transition(current: DeliveryStatus, target: DeliveryStatus) -> DeliveryStatus:
    """Validate and transition to target status, or raise InvalidDeliveryStateTransitionError."""
    if not can_transition(current, target):
        raise InvalidDeliveryStateTransitionError(current, target)
    return target
