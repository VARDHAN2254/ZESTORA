"""Identity domain enumerations for roles and account statuses."""

import enum


class UserRole(str, enum.Enum):
    """Core platform user roles."""

    CUSTOMER = "CUSTOMER"
    RESTAURANT = "RESTAURANT"
    DELIVERY_PARTNER = "DELIVERY_PARTNER"
    ADMIN = "ADMIN"


class UserStatus(str, enum.Enum):
    """Lifecycle states for a user account."""

    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    SUSPENDED = "SUSPENDED"
