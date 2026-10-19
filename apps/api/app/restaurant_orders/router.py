"""FastAPI router for restaurant order management endpoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.identity.dependencies import require_restaurant
from app.identity.models import User
from app.orders.enums import OrderStatus
from app.orders.exceptions import (
    InvalidOrderTransitionError,
    OrderNotEligibleError,
    OrderNotFoundError,
)
from app.restaurant_orders.schemas import (
    RestaurantOrderListResponse,
    RestaurantOrderResponse,
)
from app.restaurant_orders.service import RestaurantOrderService
from app.restaurants.exceptions import (
    RestaurantNotFoundError,
    UnauthorizedRestaurantAccessError,
)

router = APIRouter(
    prefix="/api/v1/restaurants/{restaurant_id}/orders",
    tags=["Restaurant Orders"],
)


@router.get(
    "",
    response_model=RestaurantOrderListResponse,
    status_code=status.HTTP_200_OK,
    summary="List restaurant orders",
)
async def list_restaurant_orders(
    restaurant_id: uuid.UUID,
    skip: int = Query(0, ge=0, description="Offset for pagination"),
    limit: int = Query(20, ge=1, le=100, description="Page size limit"),
    status_filter: OrderStatus | None = Query(
        None, alias="status", description="Filter by order status"
    ),
    current_user: User = Depends(require_restaurant),
    session: AsyncSession = Depends(get_db),
) -> RestaurantOrderListResponse:
    """List orders for a restaurant owned by the authenticated RESTAURANT user."""
    service = RestaurantOrderService(session)
    try:
        orders, total = await service.list_restaurant_orders(
            user=current_user,
            restaurant_id=restaurant_id,
            skip=skip,
            limit=limit,
            status=status_filter,
        )
        return RestaurantOrderListResponse(
            items=[RestaurantOrderResponse.from_orm_order(o) for o in orders],
            total=total,
            skip=skip,
            limit=limit,
        )
    except UnauthorizedRestaurantAccessError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except RestaurantNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.get(
    "/{order_id}",
    response_model=RestaurantOrderResponse,
    status_code=status.HTTP_200_OK,
    summary="Get restaurant order by ID",
)
async def get_restaurant_order(
    restaurant_id: uuid.UUID,
    order_id: uuid.UUID,
    current_user: User = Depends(require_restaurant),
    session: AsyncSession = Depends(get_db),
) -> RestaurantOrderResponse:
    """Retrieve a specific order belonging to the authenticated user's restaurant."""
    service = RestaurantOrderService(session)
    try:
        order = await service.get_restaurant_order(
            user=current_user,
            restaurant_id=restaurant_id,
            order_id=order_id,
        )
        return RestaurantOrderResponse.from_orm_order(order)
    except UnauthorizedRestaurantAccessError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except (RestaurantNotFoundError, OrderNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.post(
    "/{order_id}/accept",
    response_model=RestaurantOrderResponse,
    status_code=status.HTTP_200_OK,
    summary="Accept a confirmed order",
)
async def accept_order(
    restaurant_id: uuid.UUID,
    order_id: uuid.UUID,
    current_user: User = Depends(require_restaurant),
    session: AsyncSession = Depends(get_db),
) -> RestaurantOrderResponse:
    """Accept an order that has been confirmed (payment completed).

    Only orders in CONFIRMED status can be accepted.
    Orders still in PENDING_PAYMENT cannot be accepted.
    """
    service = RestaurantOrderService(session)
    try:
        order = await service.accept_order(
            user=current_user,
            restaurant_id=restaurant_id,
            order_id=order_id,
        )
        return RestaurantOrderResponse.from_orm_order(order)
    except UnauthorizedRestaurantAccessError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except RestaurantNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except OrderNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except OrderNotEligibleError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except InvalidOrderTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.post(
    "/{order_id}/prepare",
    response_model=RestaurantOrderResponse,
    status_code=status.HTTP_200_OK,
    summary="Start preparing an accepted order",
)
async def start_preparing(
    restaurant_id: uuid.UUID,
    order_id: uuid.UUID,
    current_user: User = Depends(require_restaurant),
    session: AsyncSession = Depends(get_db),
) -> RestaurantOrderResponse:
    """Transition an ACCEPTED order to PREPARING status."""
    service = RestaurantOrderService(session)
    try:
        order = await service.start_preparing(
            user=current_user,
            restaurant_id=restaurant_id,
            order_id=order_id,
        )
        return RestaurantOrderResponse.from_orm_order(order)
    except UnauthorizedRestaurantAccessError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except (RestaurantNotFoundError, OrderNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except InvalidOrderTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.post(
    "/{order_id}/ready",
    response_model=RestaurantOrderResponse,
    status_code=status.HTTP_200_OK,
    summary="Mark order as ready for pickup",
)
async def mark_ready_for_pickup(
    restaurant_id: uuid.UUID,
    order_id: uuid.UUID,
    current_user: User = Depends(require_restaurant),
    session: AsyncSession = Depends(get_db),
) -> RestaurantOrderResponse:
    """Transition a PREPARING order to READY_FOR_PICKUP status."""
    service = RestaurantOrderService(session)
    try:
        order = await service.mark_ready_for_pickup(
            user=current_user,
            restaurant_id=restaurant_id,
            order_id=order_id,
        )
        return RestaurantOrderResponse.from_orm_order(order)
    except UnauthorizedRestaurantAccessError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except (RestaurantNotFoundError, OrderNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except InvalidOrderTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.post(
    "/{order_id}/cancel",
    response_model=RestaurantOrderResponse,
    status_code=status.HTTP_200_OK,
    summary="Cancel an order",
)
async def cancel_order(
    restaurant_id: uuid.UUID,
    order_id: uuid.UUID,
    current_user: User = Depends(require_restaurant),
    session: AsyncSession = Depends(get_db),
) -> RestaurantOrderResponse:
    """Cancel an order from CONFIRMED, ACCEPTED, or PREPARING status.

    Orders in terminal statuses or delivery-phase statuses cannot be cancelled
    by the restaurant.
    """
    service = RestaurantOrderService(session)
    try:
        order = await service.cancel_order(
            user=current_user,
            restaurant_id=restaurant_id,
            order_id=order_id,
        )
        return RestaurantOrderResponse.from_orm_order(order)
    except UnauthorizedRestaurantAccessError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except (RestaurantNotFoundError, OrderNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except InvalidOrderTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
