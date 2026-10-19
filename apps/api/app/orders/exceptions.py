"""Domain exceptions for the orders module."""


class OrderError(Exception):
    """Base exception for all order domain errors."""


class OrderNotFoundError(OrderError):
    """Raised when a requested order is not found or not accessible to the caller."""


class UnauthorizedOrderAccessError(OrderError):
    """Raised when an unauthorized user attempts to access an order."""
