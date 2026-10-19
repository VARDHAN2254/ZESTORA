"""Pydantic schemas for the customer cart API."""

import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.cart.pricing import PricedCart


class CartItemAddRequest(BaseModel):
    """Payload to add a menu item to the authenticated customer's cart."""

    menu_item_id: uuid.UUID = Field(..., description="UUID of the menu item to add")
    quantity: int = Field(1, ge=1, description="Quantity to add (must be at least 1)")


class CartItemUpdateRequest(BaseModel):
    """Payload to update the quantity of an existing cart item."""

    quantity: int = Field(..., ge=1, description="New quantity (must be at least 1)")


class CartItemResponse(BaseModel):
    """Representation of an individual line item in the customer's cart."""

    model_config = ConfigDict(from_attributes=True)

    menu_item_id: uuid.UUID
    name: str
    description: str | None = None
    quantity: int
    unit_price: Decimal
    line_total: Decimal
    is_available: bool


class CartResponse(BaseModel):
    """Authoritative representation of the customer's cart and calculated pricing."""

    model_config = ConfigDict(from_attributes=True)

    cart_id: uuid.UUID
    customer_id: uuid.UUID
    restaurant_id: uuid.UUID | None = None
    items: list[CartItemResponse] = []
    item_count: int = 0
    subtotal: Decimal = Decimal("0.00")
    currency: str = "INR"

    @classmethod
    def from_priced_cart(cls, priced: PricedCart) -> "CartResponse":
        """Convert an immutable PricedCart domain value object to CartResponse schema."""
        return cls(
            cart_id=priced.cart_id,
            customer_id=priced.customer_id,
            restaurant_id=priced.restaurant_id,
            items=[
                CartItemResponse(
                    menu_item_id=item.menu_item_id,
                    name=item.name,
                    description=item.description,
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                    line_total=item.line_total,
                    is_available=item.is_available,
                )
                for item in priced.items
            ],
            item_count=priced.item_count,
            subtotal=priced.subtotal,
            currency=priced.currency,
        )
