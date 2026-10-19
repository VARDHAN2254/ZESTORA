"""Pydantic schemas for restaurant order management API."""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.orders.enums import OrderStatus
from app.orders.models import Order


class RestaurantOrderItemResponse(BaseModel):
    """Historical snapshot of an ordered menu item for restaurant view."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    menu_item_id: uuid.UUID
    item_name: str
    item_description: str | None = None
    quantity: int
    unit_price: Decimal
    line_total: Decimal


class RestaurantOrderDeliveryAddress(BaseModel):
    """Delivery address snapshot shown to restaurant."""

    delivery_address_line1: str
    delivery_address_line2: str | None = None
    delivery_city: str
    delivery_state: str
    delivery_postal_code: str


class RestaurantOrderResponse(BaseModel):
    """Restaurant-facing order response schema.

    Excludes sensitive fields like exact customer coordinates, payment secrets,
    and password hashes. Includes only information needed for order management.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    customer_id: uuid.UUID
    restaurant_id: uuid.UUID
    status: OrderStatus
    subtotal: Decimal
    delivery_fee: Decimal
    tax: Decimal
    discount: Decimal
    total: Decimal
    currency: str
    delivery_address: RestaurantOrderDeliveryAddress
    notes: str | None = None
    items: list[RestaurantOrderItemResponse] = []
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_orm_order(cls, order: Order) -> "RestaurantOrderResponse":
        """Convert SQLAlchemy Order model to restaurant-facing response."""
        addr = RestaurantOrderDeliveryAddress(
            delivery_address_line1=order.delivery_address_line1,
            delivery_address_line2=order.delivery_address_line2,
            delivery_city=order.delivery_city,
            delivery_state=order.delivery_state,
            delivery_postal_code=order.delivery_postal_code,
        )
        return cls(
            id=order.id,
            customer_id=order.customer_id,
            restaurant_id=order.restaurant_id,
            status=order.status,
            subtotal=order.subtotal,
            delivery_fee=order.delivery_fee,
            tax=order.tax,
            discount=order.discount,
            total=order.total,
            currency=order.currency,
            delivery_address=addr,
            notes=order.notes,
            items=[
                RestaurantOrderItemResponse(
                    id=item.id,
                    menu_item_id=item.menu_item_id,
                    item_name=item.item_name,
                    item_description=item.item_description,
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                    line_total=item.line_total,
                )
                for item in (order.items or [])
            ],
            created_at=order.created_at,
            updated_at=order.updated_at,
        )


class RestaurantOrderListResponse(BaseModel):
    """Paginated list of restaurant orders."""

    items: list[RestaurantOrderResponse]
    total: int
    skip: int
    limit: int
