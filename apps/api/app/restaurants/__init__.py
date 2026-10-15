"""Restaurant domain module for ZESTORA API."""

from app.restaurants.enums import RestaurantStatus
from app.restaurants.exceptions import (
    InvalidRestaurantStatusError,
    RestaurantError,
    RestaurantNotFoundError,
    RestaurantSlugAlreadyExistsError,
    UnauthorizedRestaurantAccessError,
)
from app.restaurants.models import Restaurant
from app.restaurants.repository import RestaurantRepository
from app.restaurants.router import router as restaurants_router
from app.restaurants.schemas import (
    RestaurantCreateRequest,
    RestaurantListResponse,
    RestaurantResponse,
    RestaurantUpdateRequest,
)
from app.restaurants.service import RestaurantService

__all__ = [
    "InvalidRestaurantStatusError",
    "Restaurant",
    "RestaurantCreateRequest",
    "RestaurantError",
    "RestaurantListResponse",
    "RestaurantNotFoundError",
    "RestaurantRepository",
    "RestaurantResponse",
    "RestaurantService",
    "RestaurantSlugAlreadyExistsError",
    "RestaurantStatus",
    "RestaurantUpdateRequest",
    "UnauthorizedRestaurantAccessError",
    "restaurants_router",
]
