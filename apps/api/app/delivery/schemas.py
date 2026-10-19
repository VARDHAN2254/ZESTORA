"""Pydantic schemas for delivery partner API."""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.delivery.enums import (
    DeliveryPartnerAvailability,
    DeliveryPartnerStatus,
    DeliveryStatus,
    VehicleType,
)
from app.delivery.models import Delivery
from app.orders.enums import OrderStatus


class DeliveryPartnerProfileResponse(BaseModel):
    """Delivery partner profile response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    status: DeliveryPartnerStatus
    availability: DeliveryPartnerAvailability
    vehicle_type: VehicleType | None = None
    vehicle_identifier: str | None = None
    created_at: datetime
    updated_at: datetime


class DeliveryPartnerAvailabilityUpdate(BaseModel):
    """Payload to update delivery partner availability."""

    availability: DeliveryPartnerAvailability


class DeliveryPartnerProfileCreate(BaseModel):
    """Payload to create or onboard a delivery partner profile."""

    vehicle_type: VehicleType = Field(default=VehicleType.BIKE)
    vehicle_identifier: str | None = Field(default=None, max_length=100)
    availability: DeliveryPartnerAvailability = Field(
        default=DeliveryPartnerAvailability.AVAILABLE
    )


class DeliveryRestaurantInfo(BaseModel):
    """Restaurant location snapshot for delivery pickup."""

    id: uuid.UUID
    name: str
    phone: str
    address_line1: str
    address_line2: str | None = None
    city: str
    state: str
    postal_code: str


class DeliveryAddressInfo(BaseModel):
    """Customer delivery address snapshot."""

    delivery_address_line1: str
    delivery_address_line2: str | None = None
    delivery_city: str
    delivery_state: str
    delivery_postal_code: str
    delivery_latitude: Decimal | None = None
    delivery_longitude: Decimal | None = None
    notes: str | None = None


class DeliveryOrderItemInfo(BaseModel):
    """Order item summary for delivery pickup verification."""

    item_name: str
    quantity: int


class DeliveryResponse(BaseModel):
    """Detailed response schema for a delivery job."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    order_id: uuid.UUID
    delivery_partner_id: uuid.UUID | None = None
    status: DeliveryStatus
    order_status: OrderStatus
    restaurant: DeliveryRestaurantInfo
    delivery_address: DeliveryAddressInfo
    items: list[DeliveryOrderItemInfo] = []
    order_total: Decimal
    currency: str = "INR"
    assigned_at: datetime | None = None
    picked_up_at: datetime | None = None
    delivered_at: datetime | None = None
    cancelled_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_orm_delivery(cls, delivery: Delivery) -> "DeliveryResponse":
        """Convert a SQLAlchemy Delivery model to DeliveryResponse."""
        order = delivery.order
        restaurant = order.restaurant if order else None

        rest_info = DeliveryRestaurantInfo(
            id=restaurant.id
            if restaurant
            else (order.restaurant_id if order else uuid.uuid4()),
            name=restaurant.name if restaurant else "Restaurant",
            phone=restaurant.phone if restaurant else "",
            address_line1=restaurant.address_line1 if restaurant else "",
            address_line2=restaurant.address_line2 if restaurant else None,
            city=restaurant.city if restaurant else "",
            state=restaurant.state if restaurant else "",
            postal_code=restaurant.postal_code if restaurant else "",
        )

        addr_info = DeliveryAddressInfo(
            delivery_address_line1=order.delivery_address_line1 if order else "",
            delivery_address_line2=order.delivery_address_line2 if order else None,
            delivery_city=order.delivery_city if order else "",
            delivery_state=order.delivery_state if order else "",
            delivery_postal_code=order.delivery_postal_code if order else "",
            delivery_latitude=order.delivery_latitude if order else None,
            delivery_longitude=order.delivery_longitude if order else None,
            notes=order.notes if order else None,
        )

        items_info = [
            DeliveryOrderItemInfo(
                item_name=item.item_name,
                quantity=item.quantity,
            )
            for item in (order.items if order and order.items else [])
        ]

        return cls(
            id=delivery.id,
            order_id=delivery.order_id,
            delivery_partner_id=delivery.delivery_partner_id,
            status=delivery.status,
            order_status=order.status if order else OrderStatus.READY_FOR_PICKUP,
            restaurant=rest_info,
            delivery_address=addr_info,
            items=items_info,
            order_total=order.total if order else Decimal("0.00"),
            currency=order.currency if order else "INR",
            assigned_at=delivery.assigned_at,
            picked_up_at=delivery.picked_up_at,
            delivered_at=delivery.delivered_at,
            cancelled_at=delivery.cancelled_at,
            created_at=delivery.created_at,
            updated_at=delivery.updated_at,
        )


class DeliveryListResponse(BaseModel):
    """Paginated list of deliveries."""

    items: list[DeliveryResponse]
    total: int
    skip: int
    limit: int
