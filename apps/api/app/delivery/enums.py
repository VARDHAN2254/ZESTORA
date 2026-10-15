"""Delivery domain enumerations for ZESTORA API."""

from enum import StrEnum


class DeliveryPartnerStatus(StrEnum):
    """Account status for delivery partners."""

    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    SUSPENDED = "SUSPENDED"


class DeliveryPartnerAvailability(StrEnum):
    """Availability state for receiving delivery assignments."""

    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


class VehicleType(StrEnum):
    """Vehicle types used by delivery partners."""

    BIKE = "BIKE"
    SCOOTER = "SCOOTER"
    MOTORCYCLE = "MOTORCYCLE"
    BICYCLE = "BICYCLE"
    CAR = "CAR"
    OTHER = "OTHER"


class DeliveryStatus(StrEnum):
    """Lifecycle statuses for order deliveries."""

    UNASSIGNED = "UNASSIGNED"
    ASSIGNED = "ASSIGNED"
    PICKED_UP = "PICKED_UP"
    OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"
