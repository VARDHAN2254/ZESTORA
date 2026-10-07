"""Payment lifecycle state machine and deterministic transition logic."""

from app.payments.enums import PaymentStatus


class InvalidPaymentStateTransitionError(ValueError):
    """Raised when an illegal payment state transition is attempted."""

    def __init__(self, current: PaymentStatus, target: PaymentStatus) -> None:
        self.current = current
        self.target = target
        super().__init__(
            f"Cannot transition payment from {current.value} to {target.value}"
        )


TERMINAL_STATES: frozenset[PaymentStatus] = frozenset(
    {
        PaymentStatus.FAILED,
        PaymentStatus.CANCELLED,
        PaymentStatus.REFUNDED,
    }
)

VALID_TRANSITIONS: dict[PaymentStatus, frozenset[PaymentStatus]] = {
    PaymentStatus.PENDING: frozenset(
        {
            PaymentStatus.AUTHORIZED,
            PaymentStatus.CAPTURED,
            PaymentStatus.FAILED,
            PaymentStatus.CANCELLED,
        }
    ),
    PaymentStatus.AUTHORIZED: frozenset(
        {
            PaymentStatus.CAPTURED,
            PaymentStatus.CANCELLED,
            PaymentStatus.FAILED,
        }
    ),
    PaymentStatus.CAPTURED: frozenset(
        {
            PaymentStatus.REFUNDED,
        }
    ),
    PaymentStatus.FAILED: frozenset(),
    PaymentStatus.CANCELLED: frozenset(),
    PaymentStatus.REFUNDED: frozenset(),
}


def can_transition(current: PaymentStatus, target: PaymentStatus) -> bool:
    """Return True if transition from current to target status is valid."""
    if current in TERMINAL_STATES:
        return False
    return target in VALID_TRANSITIONS.get(current, frozenset())


def transition(current: PaymentStatus, target: PaymentStatus) -> PaymentStatus:
    """Validate and transition to target status, or raise InvalidPaymentStateTransitionError."""
    if not can_transition(current, target):
        raise InvalidPaymentStateTransitionError(current, target)
    return target
