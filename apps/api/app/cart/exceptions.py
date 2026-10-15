"""Cart and pricing domain exceptions."""


class CartError(Exception):
    """Base exception for all cart domain errors."""


class CartNotFoundError(CartError):
    """Raised when a cart is not found."""


class CartItemNotFoundError(CartError):
    """Raised when a specific item is not found in the cart."""


class CartRestaurantConflictError(CartError):
    """Raised when adding an item from a different restaurant to a non-empty cart."""


class InvalidQuantityError(CartError, ValueError):
    """Raised when an item quantity is not a positive integer."""


class EmptyCartError(CartError):
    """Raised when an operation requires items in the cart but the cart is empty."""


class UnauthorizedCartAccessError(CartError, PermissionError):
    """Raised when a user who is not a CUSTOMER attempts cart operations."""


class MenuItemUnavailableError(CartError):
    """Raised when a menu item is not available or does not exist."""


class RestaurantNotEligibleError(CartError):
    """Raised when a restaurant is not active or eligible to accept orders."""
