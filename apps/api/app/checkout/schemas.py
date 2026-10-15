"""Value objects and schemas for the checkout domain."""

from dataclasses import dataclass
from decimal import Decimal

from app.checkout.exceptions import InvalidDeliveryAddressError


@dataclass(frozen=True)
class DeliveryAddressSnapshot:
    """Historical delivery address snapshot required for order placement."""

    delivery_address_line1: str
    delivery_city: str
    delivery_state: str
    delivery_postal_code: str
    delivery_address_line2: str | None = None
    delivery_latitude: Decimal | float | None = None
    delivery_longitude: Decimal | float | None = None
    notes: str | None = None

    def validate(self) -> None:
        """Validate that all mandatory address fields are non-empty strings."""
        if not self.delivery_address_line1 or not self.delivery_address_line1.strip():
            raise InvalidDeliveryAddressError(
                "delivery_address_line1 must be a non-empty string."
            )
        if not self.delivery_city or not self.delivery_city.strip():
            raise InvalidDeliveryAddressError(
                "delivery_city must be a non-empty string."
            )
        if not self.delivery_state or not self.delivery_state.strip():
            raise InvalidDeliveryAddressError(
                "delivery_state must be a non-empty string."
            )
        if not self.delivery_postal_code or not self.delivery_postal_code.strip():
            raise InvalidDeliveryAddressError(
                "delivery_postal_code must be a non-empty string."
            )
