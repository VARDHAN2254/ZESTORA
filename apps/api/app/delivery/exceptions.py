"""Delivery domain exceptions."""


class DeliveryError(Exception):
    """Base exception for delivery domain errors."""


class DeliveryNotFoundError(DeliveryError):
    """Raised when a requested delivery record is not found."""


class DeliveryPartnerNotFoundError(DeliveryError):
    """Raised when a delivery partner profile does not exist."""


class DeliveryPartnerNotEligibleError(DeliveryError):
    """Raised when a delivery partner is not eligible for the requested operation."""


class UnauthorizedDeliveryAccessError(DeliveryError):
    """Raised when a delivery partner attempts unauthorized access to a delivery."""


class DeliveryAlreadyAssignedError(DeliveryError):
    """Raised when an available delivery has already been assigned or claimed."""


class InvalidDeliveryTransitionError(DeliveryError):
    """Raised when an invalid delivery state transition is attempted."""


class OrderNotReadyForPickupError(DeliveryError):
    """Raised when an order is not yet ready for pickup."""


class DeliveryOrderConflictError(DeliveryError):
    """Raised when delivery status and order status conflict or cannot be coordinated."""
