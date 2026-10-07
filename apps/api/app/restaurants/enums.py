"""Restaurant domain enumerations."""

import enum


class RestaurantStatus(str, enum.Enum):
    """Lifecycle states for a restaurant entity."""

    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    SUSPENDED = "SUSPENDED"
