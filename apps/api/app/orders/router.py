"""FastAPI router for customer order endpoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.identity.dependencies import require_customer
from app.identity.models import User
from app.orders.exceptions import OrderNotFoundError, UnauthorizedOrderAccessError
from app.orders.schemas import OrderListResponse, OrderResponse
from app.orders.service import OrderService

router = APIRouter(prefix="/api/v1/orders", tags=["Orders"])


@router.get(
    "",
    response_model=OrderListResponse,
    status_code=status.HTTP_200_OK,
    summary="List customer order history",
)
async def list_customer_orders(
    skip: int = Query(0, ge=0, description="Offset for pagination"),
    limit: int = Query(20, ge=1, le=100, description="Page size limit"),
    current_user: User = Depends(require_customer),
    session: AsyncSession = Depends(get_db),
) -> OrderListResponse:
    """Retrieve paginated order history for the authenticated customer."""
    service = OrderService(session)
    try:
        orders, total = await service.list_customer_orders(
            customer=current_user,
            skip=skip,
            limit=limit,
        )
        return OrderListResponse(
            items=[OrderResponse.from_orm_order(o) for o in orders],
            total=total,
            skip=skip,
            limit=limit,
        )
    except UnauthorizedOrderAccessError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc


@router.get(
    "/{order_id}",
    response_model=OrderResponse,
    status_code=status.HTTP_200_OK,
    summary="Get customer order by ID",
)
async def get_customer_order(
    order_id: uuid.UUID,
    current_user: User = Depends(require_customer),
    session: AsyncSession = Depends(get_db),
) -> OrderResponse:
    """Retrieve a specific order owned by the authenticated customer."""
    service = OrderService(session)
    try:
        order = await service.get_customer_order(
            customer=current_user,
            order_id=order_id,
        )
        return OrderResponse.from_orm_order(order)
    except UnauthorizedOrderAccessError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except OrderNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
