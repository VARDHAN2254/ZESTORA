"""Catalog domain module for ZESTORA API."""

from app.catalog.exceptions import (
    CatalogError,
    InvalidCategoryAssignmentError,
    InvalidPriceError,
    MenuCategoryAlreadyExistsError,
    MenuCategoryNotFoundError,
    MenuItemInUseError,
    MenuItemNotFoundError,
)
from app.catalog.models import MenuCategory, MenuItem
from app.catalog.repository import CatalogRepository
from app.catalog.router import router as catalog_router
from app.catalog.schemas import (
    MenuCategoryCreateRequest,
    MenuCategoryResponse,
    MenuCategoryUpdateRequest,
    MenuCategoryWithItemsResponse,
    MenuItemCreateRequest,
    MenuItemResponse,
    MenuItemUpdateRequest,
    RestaurantMenuResponse,
)
from app.catalog.service import CatalogService

__all__ = [
    "CatalogError",
    "CatalogRepository",
    "CatalogService",
    "InvalidCategoryAssignmentError",
    "InvalidPriceError",
    "MenuCategory",
    "MenuCategoryAlreadyExistsError",
    "MenuCategoryCreateRequest",
    "MenuCategoryNotFoundError",
    "MenuCategoryResponse",
    "MenuCategoryUpdateRequest",
    "MenuCategoryWithItemsResponse",
    "MenuItem",
    "MenuItemCreateRequest",
    "MenuItemInUseError",
    "MenuItemNotFoundError",
    "MenuItemResponse",
    "MenuItemUpdateRequest",
    "RestaurantMenuResponse",
    "catalog_router",
]
