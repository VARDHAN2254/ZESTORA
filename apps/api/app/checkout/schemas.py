"""Value objects and schemas for the checkout domain."""

from dataclasses import dataclass
from decimal import Decimal

from pydantic import BaseModel, Field

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


class CheckoutRequest(BaseModel):
    """Payload to checkout the authenticated customer's cart."""

    delivery_address_line1: str = Field(
        ..., min_length=1, max_length=255, description="Street address"
    )
    delivery_address_line2: str | None = Field(
        None, max_length=255, description="Apartment, suite, etc."
    )
    delivery_city: str = Field(..., min_length=1, max_length=100, description="City")
    delivery_state: str = Field(
        ..., min_length=1, max_length=100, description="State / Province"
    )
    delivery_postal_code: str = Field(
        ..., min_length=1, max_length=20, description="Postal code"
    )
    delivery_latitude: Decimal | float | None = Field(
        None, description="Geographic latitude"
    )
    delivery_longitude: Decimal | float | None = Field(
        None, description="Geographic longitude"
    )
    notes: str | None = Field(None, description="Optional delivery notes")

    def to_snapshot(self) -> DeliveryAddressSnapshot:
        """Convert validated request payload into domain DeliveryAddressSnapshot."""
        return DeliveryAddressSnapshot(
            delivery_address_line1=self.delivery_address_line1.strip(),
            delivery_address_line2=(
                self.delivery_address_line2.strip()
                if self.delivery_address_line2
                else None
            ),
            delivery_city=self.delivery_city.strip(),
            delivery_state=self.delivery_state.strip(),
            delivery_postal_code=self.delivery_postal_code.strip(),
            delivery_latitude=self.delivery_latitude,
            delivery_longitude=self.delivery_longitude,
            notes=self.notes.strip() if self.notes else None,
        )
