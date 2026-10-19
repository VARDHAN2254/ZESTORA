"""Delivery domain module for ZESTORA API."""

from app.delivery.enums import (
    DeliveryPartnerAvailability,
    DeliveryPartnerStatus,
    DeliveryStatus,
    VehicleType,
)
from app.delivery.exceptions import (
    DeliveryAlreadyAssignedError,
    DeliveryNotFoundError,
    DeliveryOrderConflictError,
    DeliveryPartnerNotEligibleError,
    DeliveryPartnerNotFoundError,
    InvalidDeliveryTransitionError,
    OrderNotReadyForPickupError,
    UnauthorizedDeliveryAccessError,
)
from app.delivery.models import Delivery, DeliveryPartner
from app.delivery.repository import DeliveryRepository
from app.delivery.router import router as delivery_partner_router
from app.delivery.schemas import (
    DeliveryAddressInfo,
    DeliveryListResponse,
    DeliveryOrderItemInfo,
    DeliveryPartnerAvailabilityUpdate,
    DeliveryPartnerProfileCreate,
    DeliveryPartnerProfileResponse,
    DeliveryResponse,
    DeliveryRestaurantInfo,
)
from app.delivery.service import DeliveryPartnerService
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
    "DeliveryAddressInfo",
    "DeliveryAlreadyAssignedError",
    "DeliveryListResponse",
    "DeliveryNotFoundError",
    "DeliveryOrderConflictError",
    "DeliveryOrderItemInfo",
    "DeliveryPartner",
    "DeliveryPartnerAvailability",
    "DeliveryPartnerAvailabilityUpdate",
    "DeliveryPartnerNotEligibleError",
    "DeliveryPartnerNotFoundError",
    "DeliveryPartnerProfileCreate",
    "DeliveryPartnerProfileResponse",
    "DeliveryPartnerService",
    "DeliveryPartnerStatus",
    "DeliveryRepository",
    "DeliveryResponse",
    "DeliveryRestaurantInfo",
    "DeliveryStatus",
    "InvalidDeliveryStateTransitionError",
    "InvalidDeliveryTransitionError",
    "OrderNotReadyForPickupError",
    "UnauthorizedDeliveryAccessError",
    "VehicleType",
    "can_transition",
    "delivery_partner_router",
    "transition",
]
