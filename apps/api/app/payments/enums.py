"""Payment domain enumerations for ZESTORA API."""

from enum import StrEnum


class PaymentStatus(StrEnum):
    """Lifecycle statuses for financial payment tracking."""

    PENDING = "PENDING"
    AUTHORIZED = "AUTHORIZED"
    CAPTURED = "CAPTURED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    REFUNDED = "REFUNDED"


class PaymentMethod(StrEnum):
    """Provider-agnostic payment methods supported by the platform."""

    CARD = "CARD"
    UPI = "UPI"
    NET_BANKING = "NET_BANKING"
    WALLET = "WALLET"
    CASH_ON_DELIVERY = "CASH_ON_DELIVERY"
