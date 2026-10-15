"""Domain exceptions for the catalog and menu module."""


class CatalogError(Exception):
    """Base exception for all catalog domain errors."""


class MenuCategoryNotFoundError(CatalogError):
    """Raised when a menu category is not found."""


class MenuCategoryAlreadyExistsError(CatalogError):
    """Raised when a menu category name is already in use for a restaurant."""


class MenuItemNotFoundError(CatalogError):
    """Raised when a menu item is not found."""


class InvalidCategoryAssignmentError(CatalogError):
    """Raised when assigning a menu item to a category belonging to another restaurant."""


class InvalidPriceError(CatalogError):
    """Raised when an invalid or negative menu item price is supplied."""


class MenuItemInUseError(CatalogError):
    """Raised when attempting to delete a menu item referenced in historical orders."""
