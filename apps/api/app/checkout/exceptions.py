"""Checkout domain exceptions."""


class CheckoutError(Exception):
    """Base exception for checkout failures."""


class EmptyCartCheckoutError(CheckoutError):
    """Raised when an empty cart is submitted for checkout."""


class InvalidDeliveryAddressError(CheckoutError, ValueError):
    """Raised when a delivery address snapshot is missing required fields."""


class CheckoutRestaurantConflictError(CheckoutError):
    """Raised when cart or order items violate single-restaurant consistency."""
