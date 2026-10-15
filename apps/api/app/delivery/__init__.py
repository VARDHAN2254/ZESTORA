"""Delivery domain module for ZESTORA API."""

from app.delivery.enums import (
    DeliveryPartnerAvailability,
    DeliveryPartnerStatus,
    DeliveryStatus,
    VehicleType,
)
from app.delivery.models import Delivery, DeliveryPartner
from app.delivery.repository import DeliveryRepository
from app.delivery.state_machine import (
    TERMINAL_STATES,
    VALID_TRANSITIONS,
    InvalidDeliveryStateTransitionError,
    can_transition,
    transition,
)

__all__ = [
    "TERMINAL_STATES",
    "VALID_TRANSITIONS",
    "Delivery",
    "DeliveryPartner",
    "DeliveryPartnerAvailability",
    "DeliveryPartnerStatus",
    "DeliveryRepository",
    "DeliveryStatus",
    "InvalidDeliveryStateTransitionError",
    "VehicleType",
    "can_transition",
    "transition",
]
