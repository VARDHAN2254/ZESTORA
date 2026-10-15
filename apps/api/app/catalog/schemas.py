"""Pydantic schemas for the catalog and menu API."""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class MenuCategoryCreateRequest(BaseModel):
    """Payload to create a new menu category for a restaurant."""

    name: str = Field(..., min_length=1, max_length=100, description="Category name")
    description: str | None = Field(None, description="Category description")
    display_order: int = Field(0, description="Sorting priority order")
    is_active: bool = Field(True, description="Whether category is active")


class MenuCategoryUpdateRequest(BaseModel):
    """Payload to update an existing menu category."""

    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None
    display_order: int | None = None
    is_active: bool | None = None


class MenuCategoryResponse(BaseModel):
    """Representation of a menu category."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    restaurant_id: uuid.UUID
    name: str
    description: str | None = None
    display_order: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class MenuItemCreateRequest(BaseModel):
    """Payload to create a new menu item for a restaurant."""

    category_id: uuid.UUID = Field(..., description="Parent menu category UUID")
    name: str = Field(..., min_length=1, max_length=255, description="Item name")
    description: str | None = Field(None, description="Item description")
    price: Decimal = Field(..., ge=0, description="Price in INR (must be non-negative)")
    is_available: bool = Field(
        True, description="Whether item is available for ordering"
    )


class MenuItemUpdateRequest(BaseModel):
    """Payload to update an existing menu item."""

    category_id: uuid.UUID | None = None
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    price: Decimal | None = Field(None, ge=0)
    is_available: bool | None = None


class MenuItemResponse(BaseModel):
    """Representation of a menu item."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    restaurant_id: uuid.UUID
    category_id: uuid.UUID
    name: str
    description: str | None = None
    price: Decimal
    is_available: bool
    created_at: datetime
    updated_at: datetime


class MenuCategoryWithItemsResponse(BaseModel):
    """Menu category with its associated menu items."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    restaurant_id: uuid.UUID
    name: str
    description: str | None = None
    display_order: int
    is_active: bool
    items: list[MenuItemResponse] = []


class RestaurantMenuResponse(BaseModel):
    """Full restaurant menu response for public discovery."""

    restaurant_id: uuid.UUID
    restaurant_name: str
    restaurant_slug: str
    categories: list[MenuCategoryWithItemsResponse]
