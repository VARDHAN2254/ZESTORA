"""FastAPI router for customer shopping cart endpoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.cart.exceptions import (
    CartItemNotFoundError,
    CartNotFoundError,
    CartRestaurantConflictError,
    InvalidQuantityError,
    MenuItemUnavailableError,
    RestaurantNotEligibleError,
    UnauthorizedCartAccessError,
)
from app.cart.schemas import (
    CartItemAddRequest,
    CartItemUpdateRequest,
    CartResponse,
)
from app.cart.service import CartService
from app.core.database import get_db
from app.identity.dependencies import require_customer
from app.identity.models import User

router = APIRouter(prefix="/api/v1/cart", tags=["Cart"])


@router.get(
    "",
    response_model=CartResponse,
    status_code=status.HTTP_200_OK,
    summary="Get customer cart",
)
async def get_cart(
    current_user: User = Depends(require_customer),
    session: AsyncSession = Depends(get_db),
) -> CartResponse:
    """Retrieve the authenticated customer's cart with authoritative server pricing."""
    service = CartService(session)
    try:
        priced_cart = await service.get_priced_cart(
            current_user, validate_eligibility=False
        )
        return CartResponse.from_priced_cart(priced_cart)
    except UnauthorizedCartAccessError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc


@router.post(
    "/items",
    response_model=CartResponse,
    status_code=status.HTTP_200_OK,
    summary="Add item to cart",
)
async def add_item_to_cart(
    payload: CartItemAddRequest,
    current_user: User = Depends(require_customer),
    session: AsyncSession = Depends(get_db),
) -> CartResponse:
    """Add a menu item to the customer's cart or increment quantity if already present."""
    service = CartService(session)
    try:
        await service.add_item(
            user=current_user,
            menu_item_id=payload.menu_item_id,
            quantity=payload.quantity,
        )
        priced_cart = await service.get_priced_cart(
            current_user, validate_eligibility=False
        )
        return CartResponse.from_priced_cart(priced_cart)
    except UnauthorizedCartAccessError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except CartRestaurantConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except (MenuItemUnavailableError, RestaurantNotEligibleError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except InvalidQuantityError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.patch(
    "/items/{menu_item_id}",
    response_model=CartResponse,
    status_code=status.HTTP_200_OK,
    summary="Update cart item quantity",
)
async def update_cart_item_quantity(
    menu_item_id: uuid.UUID,
    payload: CartItemUpdateRequest,
    current_user: User = Depends(require_customer),
    session: AsyncSession = Depends(get_db),
) -> CartResponse:
    """Update the quantity of a specific menu item in the customer's cart."""
    service = CartService(session)
    try:
        await service.update_item_quantity(
            user=current_user,
            menu_item_id=menu_item_id,
            quantity=payload.quantity,
        )
        priced_cart = await service.get_priced_cart(
            current_user, validate_eligibility=False
        )
        return CartResponse.from_priced_cart(priced_cart)
    except UnauthorizedCartAccessError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except (CartItemNotFoundError, CartNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except InvalidQuantityError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.delete(
    "/items/{menu_item_id}",
    response_model=CartResponse,
    status_code=status.HTTP_200_OK,
    summary="Remove item from cart",
)
async def remove_item_from_cart(
    menu_item_id: uuid.UUID,
    current_user: User = Depends(require_customer),
    session: AsyncSession = Depends(get_db),
) -> CartResponse:
    """Remove a specific menu item from the customer's cart."""
    service = CartService(session)
    try:
        await service.remove_item(
            user=current_user,
            menu_item_id=menu_item_id,
        )
        priced_cart = await service.get_priced_cart(
            current_user, validate_eligibility=False
        )
        return CartResponse.from_priced_cart(priced_cart)
    except UnauthorizedCartAccessError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except (CartItemNotFoundError, CartNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.delete(
    "",
    response_model=CartResponse,
    status_code=status.HTTP_200_OK,
    summary="Clear customer cart",
)
async def clear_cart(
    current_user: User = Depends(require_customer),
    session: AsyncSession = Depends(get_db),
) -> CartResponse:
    """Clear all items from the authenticated customer's cart."""
    service = CartService(session)
    try:
        await service.clear_cart(current_user)
        priced_cart = await service.get_priced_cart(
            current_user, validate_eligibility=False
        )
        return CartResponse.from_priced_cart(priced_cart)
    except UnauthorizedCartAccessError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
