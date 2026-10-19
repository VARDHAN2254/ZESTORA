"""Pydantic schemas for the customer orders API."""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.orders.enums import OrderStatus
from app.orders.models import Order


class OrderItemResponse(BaseModel):
    """Historical snapshot representation of an ordered menu item."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    menu_item_id: uuid.UUID
    item_name: str
    item_description: str | None = None
    quantity: int
    unit_price: Decimal
    line_total: Decimal


class DeliveryAddressResponse(BaseModel):
    """Delivery address snapshot for an order."""

    delivery_address_line1: str
    delivery_address_line2: str | None = None
    delivery_city: str
    delivery_state: str
    delivery_postal_code: str
    delivery_latitude: Decimal | None = None
    delivery_longitude: Decimal | None = None
    notes: str | None = None


class OrderResponse(BaseModel):
    """Customer-facing order response schema."""

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
    delivery_address_line1: str
    delivery_address_line2: str | None = None
    delivery_city: str
    delivery_state: str
    delivery_postal_code: str
    delivery_latitude: Decimal | None = None
    delivery_longitude: Decimal | None = None
    notes: str | None = None
    delivery_address: DeliveryAddressResponse
    items: list[OrderItemResponse] = []
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_orm_order(cls, order: Order) -> "OrderResponse":
        """Convert SQLAlchemy Order model to typed OrderResponse."""
        addr = DeliveryAddressResponse(
            delivery_address_line1=order.delivery_address_line1,
            delivery_address_line2=order.delivery_address_line2,
            delivery_city=order.delivery_city,
            delivery_state=order.delivery_state,
            delivery_postal_code=order.delivery_postal_code,
            delivery_latitude=order.delivery_latitude,
            delivery_longitude=order.delivery_longitude,
            notes=order.notes,
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
            delivery_address_line1=order.delivery_address_line1,
            delivery_address_line2=order.delivery_address_line2,
            delivery_city=order.delivery_city,
            delivery_state=order.delivery_state,
            delivery_postal_code=order.delivery_postal_code,
            delivery_latitude=order.delivery_latitude,
            delivery_longitude=order.delivery_longitude,
            notes=order.notes,
            delivery_address=addr,
            items=[
                OrderItemResponse(
                    id=item.id,
                    menu_item_id=item.menu_item_id,
                    item_name=item.item_name,
                    item_description=item.item_description,
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                    line_total=item.line_total,
                )
                for item in order.items
            ],
            created_at=order.created_at,
            updated_at=order.updated_at,
        )


class OrderListResponse(BaseModel):
    """Paginated list of customer orders."""

    items: list[OrderResponse]
    total: int
    skip: int
    limit: int
