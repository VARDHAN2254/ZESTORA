"""Pydantic schemas for the restaurant domain API."""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.restaurants.enums import RestaurantStatus


class RestaurantCreateRequest(BaseModel):
    """Payload to create a new restaurant by an authenticated restaurant owner."""

    name: str = Field(..., min_length=1, max_length=255, description="Restaurant name")
    slug: str | None = Field(
        None,
        min_length=1,
        max_length=255,
        description="Optional custom URL slug. Derived from name if omitted.",
    )
    description: str | None = Field(None, description="Detailed description")
    phone: str = Field(..., min_length=1, max_length=30, description="Contact phone")
    address_line1: str = Field(
        ..., min_length=1, max_length=255, description="Street address line 1"
    )
    address_line2: str | None = Field(
        None, max_length=255, description="Address line 2"
    )
    city: str = Field(..., min_length=1, max_length=100, description="City")
    state: str = Field(
        ..., min_length=1, max_length=100, description="State / Province"
    )
    postal_code: str = Field(
        ..., min_length=1, max_length=20, description="Postal code"
    )
    latitude: Decimal | float | None = Field(None, description="Geographic latitude")
    longitude: Decimal | float | None = Field(None, description="Geographic longitude")


class RestaurantUpdateRequest(BaseModel):
    """Payload to update permitted restaurant profile fields."""

    name: str | None = Field(None, min_length=1, max_length=255)
    slug: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    phone: str | None = Field(None, min_length=1, max_length=30)
    address_line1: str | None = Field(None, min_length=1, max_length=255)
    address_line2: str | None = Field(None, max_length=255)
    city: str | None = Field(None, min_length=1, max_length=100)
    state: str | None = Field(None, min_length=1, max_length=100)
    postal_code: str | None = Field(None, min_length=1, max_length=20)
    latitude: Decimal | float | None = None
    longitude: Decimal | float | None = None
    status: RestaurantStatus | None = None


class RestaurantResponse(BaseModel):
    """Public and management representation of a Restaurant."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_id: uuid.UUID
    name: str
    slug: str
    description: str | None = None
    phone: str
    address_line1: str
    address_line2: str | None = None
    city: str
    state: str
    postal_code: str
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    status: RestaurantStatus
    created_at: datetime
    updated_at: datetime


class RestaurantListResponse(BaseModel):
    """Paginated list of restaurants."""

    items: list[RestaurantResponse]
    total: int
    skip: int
    limit: int
