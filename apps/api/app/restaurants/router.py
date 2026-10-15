"""FastAPI router for restaurant endpoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.identity.dependencies import require_restaurant
from app.identity.models import User
from app.restaurants.exceptions import (
    InvalidRestaurantStatusError,
    RestaurantNotFoundError,
    RestaurantSlugAlreadyExistsError,
    UnauthorizedRestaurantAccessError,
)
from app.restaurants.schemas import (
    RestaurantCreateRequest,
    RestaurantListResponse,
    RestaurantResponse,
    RestaurantUpdateRequest,
)
from app.restaurants.service import RestaurantService

router = APIRouter(prefix="/api/v1/restaurants", tags=["Restaurants"])


@router.get(
    "",
    response_model=RestaurantListResponse,
    status_code=status.HTTP_200_OK,
    summary="List active restaurants (Public Discovery)",
)
async def list_restaurants(
    skip: int = Query(0, ge=0, description="Offset for pagination"),
    limit: int = Query(20, ge=1, le=100, description="Page size limit"),
    city: str | None = Query(None, description="Filter by city name"),
    session: AsyncSession = Depends(get_db),
) -> RestaurantListResponse:
    """List active restaurants eligible for public discovery."""
    service = RestaurantService(session)
    items, total = await service.list_active_restaurants(
        skip=skip, limit=limit, city=city
    )
    return RestaurantListResponse(
        items=[RestaurantResponse.model_validate(r) for r in items],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/mine",
    response_model=list[RestaurantResponse],
    status_code=status.HTTP_200_OK,
    summary="List caller's restaurants (Restaurant Management)",
)
async def list_my_restaurants(
    current_user: User = Depends(require_restaurant),
    session: AsyncSession = Depends(get_db),
) -> list[RestaurantResponse]:
    """List all restaurants owned by the authenticated RESTAURANT user."""
    service = RestaurantService(session)
    restaurants = await service.list_owner_restaurants(current_user)
    return [RestaurantResponse.model_validate(r) for r in restaurants]


@router.get(
    "/{slug}",
    response_model=RestaurantResponse,
    status_code=status.HTTP_200_OK,
    summary="Get active restaurant details by slug (Public Discovery)",
)
async def get_restaurant_by_slug(
    slug: str,
    session: AsyncSession = Depends(get_db),
) -> RestaurantResponse:
    """Retrieve details for a single active restaurant by its public identifier (slug)."""
    service = RestaurantService(session)
    try:
        restaurant = await service.get_active_restaurant_by_slug(slug)
        return RestaurantResponse.model_validate(restaurant)
    except RestaurantNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.post(
    "",
    response_model=RestaurantResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new restaurant (Restaurant Management)",
)
async def create_restaurant(
    payload: RestaurantCreateRequest,
    current_user: User = Depends(require_restaurant),
    session: AsyncSession = Depends(get_db),
) -> RestaurantResponse:
    """Create a new restaurant for the authenticated RESTAURANT owner."""
    service = RestaurantService(session)
    try:
        restaurant = await service.create_restaurant(
            owner=current_user, payload=payload
        )
        return RestaurantResponse.model_validate(restaurant)
    except UnauthorizedRestaurantAccessError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except RestaurantSlugAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.patch(
    "/{restaurant_id}",
    response_model=RestaurantResponse,
    status_code=status.HTTP_200_OK,
    summary="Update restaurant profile (Restaurant Management)",
)
async def update_restaurant(
    restaurant_id: uuid.UUID,
    payload: RestaurantUpdateRequest,
    current_user: User = Depends(require_restaurant),
    session: AsyncSession = Depends(get_db),
) -> RestaurantResponse:
    """Update permitted fields on a restaurant owned by the authenticated caller."""
    service = RestaurantService(session)
    try:
        restaurant = await service.update_restaurant(
            owner=current_user,
            restaurant_id=restaurant_id,
            payload=payload,
        )
        return RestaurantResponse.model_validate(restaurant)
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
    except InvalidRestaurantStatusError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except RestaurantSlugAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
