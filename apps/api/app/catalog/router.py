"""FastAPI router for menu browsing and catalog management endpoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.exceptions import (
    InvalidCategoryAssignmentError,
    InvalidPriceError,
    MenuCategoryAlreadyExistsError,
    MenuCategoryNotFoundError,
    MenuItemInUseError,
    MenuItemNotFoundError,
)
from app.catalog.schemas import (
    MenuCategoryCreateRequest,
    MenuCategoryResponse,
    MenuCategoryUpdateRequest,
    MenuItemCreateRequest,
    MenuItemResponse,
    MenuItemUpdateRequest,
    RestaurantMenuResponse,
)
from app.catalog.service import CatalogService
from app.core.database import get_db
from app.identity.dependencies import require_restaurant
from app.identity.models import User
from app.restaurants.exceptions import (
    RestaurantNotFoundError,
    UnauthorizedRestaurantAccessError,
)

router = APIRouter(prefix="/api/v1/restaurants", tags=["Menu & Catalog"])


# ==============================================================================
# 1. PUBLIC MENU BROWSING
# ==============================================================================


@router.get(
    "/{slug}/menu",
    response_model=RestaurantMenuResponse,
    status_code=status.HTTP_200_OK,
    summary="Get complete active restaurant menu (Public Browsing)",
)
async def get_restaurant_menu(
    slug: str,
    session: AsyncSession = Depends(get_db),
) -> RestaurantMenuResponse:
    """Retrieve full menu for an active restaurant, grouped by category without N+1 queries."""
    service = CatalogService(session)
    try:
        restaurant, categories = await service.get_public_menu(slug)
        return RestaurantMenuResponse(
            restaurant_id=restaurant.id,
            restaurant_name=restaurant.name,
            restaurant_slug=restaurant.slug,
            categories=categories,
        )
    except RestaurantNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.get(
    "/{slug}/categories",
    response_model=list[MenuCategoryResponse],
    status_code=status.HTTP_200_OK,
    summary="List active menu categories for a restaurant (Public Browsing)",
)
async def list_restaurant_categories(
    slug: str,
    session: AsyncSession = Depends(get_db),
) -> list[MenuCategoryResponse]:
    """List all active menu categories for an active restaurant."""
    service = CatalogService(session)
    try:
        _, categories = await service.list_public_categories(slug)
        return [MenuCategoryResponse.model_validate(c) for c in categories]
    except RestaurantNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.get(
    "/{slug}/items",
    response_model=list[MenuItemResponse],
    status_code=status.HTTP_200_OK,
    summary="List available menu items for a restaurant (Public Browsing)",
)
async def list_restaurant_items(
    slug: str,
    category_id: uuid.UUID | None = Query(None, description="Optional category filter"),
    session: AsyncSession = Depends(get_db),
) -> list[MenuItemResponse]:
    """List available items for an active restaurant, optionally filtered by category."""
    service = CatalogService(session)
    try:
        _, items = await service.list_public_items(slug, category_id=category_id)
        return [MenuItemResponse.model_validate(i) for i in items]
    except (RestaurantNotFoundError, MenuCategoryNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.get(
    "/{slug}/items/{item_id}",
    response_model=MenuItemResponse,
    status_code=status.HTTP_200_OK,
    summary="Get single available menu item details (Public Browsing)",
)
async def get_restaurant_item(
    slug: str,
    item_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
) -> MenuItemResponse:
    """Retrieve details for a single available menu item from an active restaurant."""
    service = CatalogService(session)
    try:
        _, item = await service.get_public_item(slug, item_id=item_id)
        return MenuItemResponse.model_validate(item)
    except (RestaurantNotFoundError, MenuItemNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


# ==============================================================================
# 2. OWNER MENU MANAGEMENT
# ==============================================================================


@router.post(
    "/{restaurant_id}/categories",
    response_model=MenuCategoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a menu category (Menu Management)",
)
async def create_category(
    restaurant_id: uuid.UUID,
    payload: MenuCategoryCreateRequest,
    current_user: User = Depends(require_restaurant),
    session: AsyncSession = Depends(get_db),
) -> MenuCategoryResponse:
    """Create a new menu category for the caller's restaurant."""
    service = CatalogService(session)
    try:
        category = await service.create_category(
            owner=current_user,
            restaurant_id=restaurant_id,
            payload=payload,
        )
        return MenuCategoryResponse.model_validate(category)
    except RestaurantNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except UnauthorizedRestaurantAccessError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except MenuCategoryAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.patch(
    "/{restaurant_id}/categories/{category_id}",
    response_model=MenuCategoryResponse,
    status_code=status.HTTP_200_OK,
    summary="Update a menu category (Menu Management)",
)
async def update_category(
    restaurant_id: uuid.UUID,
    category_id: uuid.UUID,
    payload: MenuCategoryUpdateRequest,
    current_user: User = Depends(require_restaurant),
    session: AsyncSession = Depends(get_db),
) -> MenuCategoryResponse:
    """Update permitted fields on a menu category."""
    service = CatalogService(session)
    try:
        category = await service.update_category(
            owner=current_user,
            restaurant_id=restaurant_id,
            category_id=category_id,
            payload=payload,
        )
        return MenuCategoryResponse.model_validate(category)
    except (RestaurantNotFoundError, MenuCategoryNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except UnauthorizedRestaurantAccessError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except MenuCategoryAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.delete(
    "/{restaurant_id}/categories/{category_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a menu category (Menu Management)",
)
async def delete_category(
    restaurant_id: uuid.UUID,
    category_id: uuid.UUID,
    current_user: User = Depends(require_restaurant),
    session: AsyncSession = Depends(get_db),
) -> None:
    """Delete a menu category if no historical order items depend on its items."""
    service = CatalogService(session)
    try:
        await service.delete_category(
            owner=current_user,
            restaurant_id=restaurant_id,
            category_id=category_id,
        )
    except (RestaurantNotFoundError, MenuCategoryNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except UnauthorizedRestaurantAccessError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except MenuItemInUseError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.post(
    "/{restaurant_id}/items",
    response_model=MenuItemResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a menu item (Menu Management)",
)
async def create_item(
    restaurant_id: uuid.UUID,
    payload: MenuItemCreateRequest,
    current_user: User = Depends(require_restaurant),
    session: AsyncSession = Depends(get_db),
) -> MenuItemResponse:
    """Create a new menu item for the caller's restaurant."""
    service = CatalogService(session)
    try:
        item = await service.create_item(
            owner=current_user,
            restaurant_id=restaurant_id,
            payload=payload,
        )
        return MenuItemResponse.model_validate(item)
    except RestaurantNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except UnauthorizedRestaurantAccessError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except InvalidCategoryAssignmentError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except InvalidPriceError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.patch(
    "/{restaurant_id}/items/{item_id}",
    response_model=MenuItemResponse,
    status_code=status.HTTP_200_OK,
    summary="Update a menu item (Menu Management)",
)
async def update_item(
    restaurant_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: MenuItemUpdateRequest,
    current_user: User = Depends(require_restaurant),
    session: AsyncSession = Depends(get_db),
) -> MenuItemResponse:
    """Update permitted fields on a menu item."""
    service = CatalogService(session)
    try:
        item = await service.update_item(
            owner=current_user,
            restaurant_id=restaurant_id,
            item_id=item_id,
            payload=payload,
        )
        return MenuItemResponse.model_validate(item)
    except (RestaurantNotFoundError, MenuItemNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except UnauthorizedRestaurantAccessError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except InvalidCategoryAssignmentError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except InvalidPriceError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.delete(
    "/{restaurant_id}/items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a menu item (Menu Management)",
)
async def delete_item(
    restaurant_id: uuid.UUID,
    item_id: uuid.UUID,
    current_user: User = Depends(require_restaurant),
    session: AsyncSession = Depends(get_db),
) -> None:
    """Delete a menu item, rejecting deletion if historical orders reference it."""
    service = CatalogService(session)
    try:
        await service.delete_or_deactivate_item(
            owner=current_user,
            restaurant_id=restaurant_id,
            item_id=item_id,
        )
    except (RestaurantNotFoundError, MenuItemNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except UnauthorizedRestaurantAccessError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except MenuItemInUseError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
