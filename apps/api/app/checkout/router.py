"""FastAPI router for checkout endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.cart.exceptions import (
    MenuItemUnavailableError,
    RestaurantNotEligibleError,
    UnauthorizedCartAccessError,
)
from app.checkout.exceptions import (
    CheckoutRestaurantConflictError,
    EmptyCartCheckoutError,
    InvalidDeliveryAddressError,
)
from app.checkout.schemas import CheckoutRequest
from app.checkout.service import CheckoutService
from app.core.database import get_db
from app.identity.dependencies import require_customer
from app.identity.models import User
from app.orders.schemas import OrderResponse

router = APIRouter(prefix="/api/v1/checkout", tags=["Checkout"])


@router.post(
    "",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Checkout customer cart into order",
)
async def checkout(
    payload: CheckoutRequest,
    current_user: User = Depends(require_customer),
    session: AsyncSession = Depends(get_db),
) -> OrderResponse:
    """Execute checkout converting the customer's cart into a persistent order in PENDING_PAYMENT status."""
    service = CheckoutService(session)
    try:
        snapshot = payload.to_snapshot()
        order = await service.checkout(
            customer=current_user,
            delivery_address=snapshot,
        )
        return OrderResponse.from_orm_order(order)
    except UnauthorizedCartAccessError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except (
        EmptyCartCheckoutError,
        MenuItemUnavailableError,
        RestaurantNotEligibleError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except CheckoutRestaurantConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except InvalidDeliveryAddressError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
