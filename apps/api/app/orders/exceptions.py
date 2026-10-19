"""Domain exceptions for the orders module."""


class OrderError(Exception):
    """Base exception for all order domain errors."""


class OrderNotFoundError(OrderError):
    """Raised when a requested order is not found or not accessible to the caller."""


class UnauthorizedOrderAccessError(OrderError):
    """Raised when an unauthorized user attempts to access an order."""


class InvalidOrderTransitionError(OrderError):
    """Raised when an invalid order state transition is attempted by an actor."""


class OrderNotEligibleError(OrderError):
    """Raised when an order is not eligible for the requested operation."""
