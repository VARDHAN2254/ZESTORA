"""Domain exceptions for the restaurant module."""


class RestaurantError(Exception):
    """Base exception for all restaurant domain errors."""


class RestaurantNotFoundError(RestaurantError):
    """Raised when a requested restaurant entity is not found."""


class RestaurantSlugAlreadyExistsError(RestaurantError):
    """Raised when a restaurant slug is already taken."""


class UnauthorizedRestaurantAccessError(RestaurantError):
    """Raised when an authenticated user attempts to access or modify a restaurant they do not own."""


class InvalidRestaurantStatusError(RestaurantError):
    """Raised when an invalid status transition is attempted."""
