"""FastAPI router for delivery partner operations."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.delivery.enums import DeliveryStatus
from app.delivery.exceptions import (
    DeliveryAlreadyAssignedError,
    DeliveryNotFoundError,
    DeliveryOrderConflictError,
    DeliveryPartnerNotEligibleError,
    DeliveryPartnerNotFoundError,
    InvalidDeliveryTransitionError,
    OrderNotReadyForPickupError,
    UnauthorizedDeliveryAccessError,
)
from app.delivery.schemas import (
    DeliveryListResponse,
    DeliveryPartnerAvailabilityUpdate,
    DeliveryPartnerProfileCreate,
    DeliveryPartnerProfileResponse,
    DeliveryResponse,
)
from app.delivery.service import DeliveryPartnerService
from app.identity.dependencies import require_delivery_partner
from app.identity.models import User

router = APIRouter(
    prefix="/api/v1/delivery-partner",
    tags=["Delivery Partner"],
)


# ==============================================================================
# 1. PROFILE & AVAILABILITY
# ==============================================================================


@router.get(
    "/profile",
    response_model=DeliveryPartnerProfileResponse,
    status_code=status.HTTP_200_OK,
    summary="Get delivery partner profile",
)
async def get_profile(
    current_user: User = Depends(require_delivery_partner),
    session: AsyncSession = Depends(get_db),
) -> DeliveryPartnerProfileResponse:
    """Retrieve the delivery partner profile for the authenticated DELIVERY_PARTNER user."""
    service = DeliveryPartnerService(session)
    try:
        partner = await service.get_partner_profile(current_user)
        return DeliveryPartnerProfileResponse.model_validate(partner)
    except DeliveryPartnerNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except UnauthorizedDeliveryAccessError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc


@router.post(
    "/profile",
    response_model=DeliveryPartnerProfileResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create or onboard delivery partner profile",
)
async def create_profile(
    payload: DeliveryPartnerProfileCreate,
    current_user: User = Depends(require_delivery_partner),
    session: AsyncSession = Depends(get_db),
) -> DeliveryPartnerProfileResponse:
    """Create a new delivery partner profile for the authenticated DELIVERY_PARTNER account."""
    service = DeliveryPartnerService(session)
    try:
        partner = await service.create_partner_profile(current_user, payload)
        return DeliveryPartnerProfileResponse.model_validate(partner)
    except DeliveryPartnerNotEligibleError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except UnauthorizedDeliveryAccessError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc


@router.patch(
    "/availability",
    response_model=DeliveryPartnerProfileResponse,
    status_code=status.HTTP_200_OK,
    summary="Update availability status",
)
async def update_availability(
    payload: DeliveryPartnerAvailabilityUpdate,
    current_user: User = Depends(require_delivery_partner),
    session: AsyncSession = Depends(get_db),
) -> DeliveryPartnerProfileResponse:
    """Toggle or update delivery partner availability (AVAILABLE / UNAVAILABLE)."""
    service = DeliveryPartnerService(session)
    try:
        partner = await service.update_availability(current_user, payload.availability)
        return DeliveryPartnerProfileResponse.model_validate(partner)
    except DeliveryPartnerNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except DeliveryPartnerNotEligibleError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except UnauthorizedDeliveryAccessError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc


# ==============================================================================
# 2. DISCOVERY & CURRENT DELIVERIES
# ==============================================================================


@router.get(
    "/available-deliveries",
    response_model=DeliveryListResponse,
    status_code=status.HTTP_200_OK,
    summary="List available eligible deliveries",
)
@router.get(
    "/deliveries/available",
    response_model=DeliveryListResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def list_available_deliveries(
    skip: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(20, ge=1, le=100, description="Page limit"),
    current_user: User = Depends(require_delivery_partner),
    session: AsyncSession = Depends(get_db),
) -> DeliveryListResponse:
    """List legitimate unassigned deliveries where the order is ready for pickup."""
    service = DeliveryPartnerService(session)
    try:
        deliveries, total = await service.list_available_deliveries(
            user=current_user, skip=skip, limit=limit
        )
        return DeliveryListResponse(
            items=[DeliveryResponse.from_orm_delivery(d) for d in deliveries],
            total=total,
            skip=skip,
            limit=limit,
        )
    except DeliveryPartnerNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except UnauthorizedDeliveryAccessError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc


@router.get(
    "/current-delivery",
    response_model=DeliveryResponse | None,
    status_code=status.HTTP_200_OK,
    summary="Get partner's active delivery assignment",
)
@router.get(
    "/deliveries/current",
    response_model=DeliveryResponse | None,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def get_current_delivery(
    current_user: User = Depends(require_delivery_partner),
    session: AsyncSession = Depends(get_db),
) -> DeliveryResponse | None:
    """Retrieve the currently active delivery assignment for the authenticated delivery partner."""
    service = DeliveryPartnerService(session)
    try:
        delivery = await service.get_current_delivery(current_user)
        if delivery is None:
            return None
        return DeliveryResponse.from_orm_delivery(delivery)
    except DeliveryPartnerNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except UnauthorizedDeliveryAccessError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc


@router.get(
    "/deliveries",
    response_model=DeliveryListResponse,
    status_code=status.HTTP_200_OK,
    summary="List delivery partner's delivery history",
)
async def list_my_deliveries(
    skip: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(20, ge=1, le=100, description="Page limit"),
    status_filter: DeliveryStatus | None = Query(
        None, alias="status", description="Filter by delivery status"
    ),
    current_user: User = Depends(require_delivery_partner),
    session: AsyncSession = Depends(get_db),
) -> DeliveryListResponse:
    """List deliveries assigned to the authenticated delivery partner with optional status filter."""
    service = DeliveryPartnerService(session)
    try:
        deliveries, total = await service.list_partner_deliveries(
            user=current_user,
            skip=skip,
            limit=limit,
            status=status_filter,
        )
        return DeliveryListResponse(
            items=[DeliveryResponse.from_orm_delivery(d) for d in deliveries],
            total=total,
            skip=skip,
            limit=limit,
        )
    except DeliveryPartnerNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except UnauthorizedDeliveryAccessError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc


@router.get(
    "/deliveries/{delivery_id}",
    response_model=DeliveryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get delivery details",
)
async def get_delivery_details(
    delivery_id: uuid.UUID,
    current_user: User = Depends(require_delivery_partner),
    session: AsyncSession = Depends(get_db),
) -> DeliveryResponse:
    """Retrieve details for a specific delivery assigned to the authenticated delivery partner."""
    service = DeliveryPartnerService(session)
    try:
        delivery = await service.get_delivery_details(current_user, delivery_id)
        return DeliveryResponse.from_orm_delivery(delivery)
    except DeliveryNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except DeliveryPartnerNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except UnauthorizedDeliveryAccessError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc


# ==============================================================================
# 3. ASSIGNMENT & LIFECYCLE TRANSITIONS
# ==============================================================================


@router.post(
    "/deliveries/{delivery_id}/accept",
    response_model=DeliveryResponse,
    status_code=status.HTTP_200_OK,
    summary="Accept an available delivery assignment",
)
async def accept_delivery(
    delivery_id: uuid.UUID,
    current_user: User = Depends(require_delivery_partner),
    session: AsyncSession = Depends(get_db),
) -> DeliveryResponse:
    """Accept and claim an available, unassigned delivery job atomically."""
    service = DeliveryPartnerService(session)
    try:
        delivery = await service.accept_delivery(current_user, delivery_id)
        return DeliveryResponse.from_orm_delivery(delivery)
    except DeliveryNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except DeliveryPartnerNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except UnauthorizedDeliveryAccessError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except (
        DeliveryAlreadyAssignedError,
        DeliveryPartnerNotEligibleError,
        InvalidDeliveryTransitionError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.post(
    "/deliveries/{delivery_id}/pickup",
    response_model=DeliveryResponse,
    status_code=status.HTTP_200_OK,
    summary="Mark order as picked up from restaurant",
)
async def pickup_delivery(
    delivery_id: uuid.UUID,
    current_user: User = Depends(require_delivery_partner),
    session: AsyncSession = Depends(get_db),
) -> DeliveryResponse:
    """Transition delivery and order to PICKED_UP atomically."""
    service = DeliveryPartnerService(session)
    try:
        delivery = await service.pickup_delivery(current_user, delivery_id)
        return DeliveryResponse.from_orm_delivery(delivery)
    except DeliveryNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except DeliveryPartnerNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except UnauthorizedDeliveryAccessError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except (
        InvalidDeliveryTransitionError,
        OrderNotReadyForPickupError,
        DeliveryOrderConflictError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.post(
    "/deliveries/{delivery_id}/out-for-delivery",
    response_model=DeliveryResponse,
    status_code=status.HTTP_200_OK,
    summary="Mark order as out for delivery",
)
@router.post(
    "/deliveries/{delivery_id}/start-delivery",
    response_model=DeliveryResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def start_delivery(
    delivery_id: uuid.UUID,
    current_user: User = Depends(require_delivery_partner),
    session: AsyncSession = Depends(get_db),
) -> DeliveryResponse:
    """Transition delivery and order to OUT_FOR_DELIVERY atomically."""
    service = DeliveryPartnerService(session)
    try:
        delivery = await service.start_delivery(current_user, delivery_id)
        return DeliveryResponse.from_orm_delivery(delivery)
    except DeliveryNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except DeliveryPartnerNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except UnauthorizedDeliveryAccessError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except (
        InvalidDeliveryTransitionError,
        DeliveryOrderConflictError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.post(
    "/deliveries/{delivery_id}/deliver",
    response_model=DeliveryResponse,
    status_code=status.HTTP_200_OK,
    summary="Mark order as delivered",
)
@router.post(
    "/deliveries/{delivery_id}/complete",
    response_model=DeliveryResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def complete_delivery(
    delivery_id: uuid.UUID,
    current_user: User = Depends(require_delivery_partner),
    session: AsyncSession = Depends(get_db),
) -> DeliveryResponse:
    """Transition delivery and order to DELIVERED atomically."""
    service = DeliveryPartnerService(session)
    try:
        delivery = await service.complete_delivery(current_user, delivery_id)
        return DeliveryResponse.from_orm_delivery(delivery)
    except DeliveryNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except DeliveryPartnerNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except UnauthorizedDeliveryAccessError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except (
        InvalidDeliveryTransitionError,
        DeliveryOrderConflictError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
