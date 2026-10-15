"""Business logic coordinator for restaurant operations."""

import re
import uuid
from collections.abc import Sequence

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.enums import UserRole
from app.identity.models import User
from app.restaurants.enums import RestaurantStatus
from app.restaurants.exceptions import (
    InvalidRestaurantStatusError,
    RestaurantNotFoundError,
    RestaurantSlugAlreadyExistsError,
    UnauthorizedRestaurantAccessError,
)
from app.restaurants.models import Restaurant
from app.restaurants.repository import RestaurantRepository
from app.restaurants.schemas import RestaurantCreateRequest, RestaurantUpdateRequest


def slugify(text: str) -> str:
    """Generate a clean URL-safe slug from text."""
    clean = re.sub(r"[^\w\s-]", "", text.lower().strip())
    slug = re.sub(r"[-\s]+", "-", clean).strip("-")
    return slug or f"restaurant-{uuid.uuid4().hex[:8]}"


class RestaurantService:
    """Service layer enforcing restaurant lifecycle and ownership policies."""

    def __init__(
        self,
        session: AsyncSession,
        repo: RestaurantRepository | None = None,
    ) -> None:
        self.session = session
        self.repo = repo or RestaurantRepository(session)

    async def list_active_restaurants(
        self,
        skip: int = 0,
        limit: int = 50,
        city: str | None = None,
    ) -> tuple[Sequence[Restaurant], int]:
        """List active restaurants for public discovery and count total matching."""
        items = await self.repo.list_active(skip=skip, limit=limit, city=city)
        total = await self.repo.count_active(city=city)
        return items, total

    async def get_active_restaurant_by_slug(self, slug: str) -> Restaurant:
        """Retrieve an active restaurant by public identifier (slug).

        Raises:
            RestaurantNotFoundError: If restaurant does not exist or is not active.
        """
        restaurant = await self.repo.get_by_slug(slug.strip().lower())
        if restaurant is None or restaurant.status != RestaurantStatus.ACTIVE:
            raise RestaurantNotFoundError(f"Restaurant with slug '{slug}' not found.")
        return restaurant

    async def get_restaurant_by_id(self, restaurant_id: uuid.UUID) -> Restaurant:
        """Retrieve a restaurant by UUID primary key.

        Raises:
            RestaurantNotFoundError: If restaurant does not exist.
        """
        restaurant = await self.repo.get_by_id(restaurant_id)
        if restaurant is None:
            raise RestaurantNotFoundError(
                f"Restaurant with ID '{restaurant_id}' not found."
            )
        return restaurant

    async def create_restaurant(
        self,
        owner: User,
        payload: RestaurantCreateRequest,
    ) -> Restaurant:
        """Create a new restaurant owned by the authenticated RESTAURANT user.

        Raises:
            UnauthorizedRestaurantAccessError: If user does not have RESTAURANT role.
            RestaurantSlugAlreadyExistsError: If slug is already taken.
        """
        if owner.role != UserRole.RESTAURANT:
            raise UnauthorizedRestaurantAccessError(
                "Only users with RESTAURANT role can create a restaurant."
            )

        # Generate or normalize slug
        target_slug = slugify(payload.slug) if payload.slug else slugify(payload.name)

        existing = await self.repo.get_by_slug(target_slug)
        if existing is not None:
            raise RestaurantSlugAlreadyExistsError(
                f"Restaurant slug '{target_slug}' is already in use."
            )

        restaurant = Restaurant(
            owner_id=owner.id,
            name=payload.name.strip(),
            slug=target_slug,
            description=payload.description.strip() if payload.description else None,
            phone=payload.phone.strip(),
            address_line1=payload.address_line1.strip(),
            address_line2=payload.address_line2.strip()
            if payload.address_line2
            else None,
            city=payload.city.strip(),
            state=payload.state.strip(),
            postal_code=payload.postal_code.strip(),
            latitude=payload.latitude,
            longitude=payload.longitude,
            status=RestaurantStatus.ACTIVE,
        )

        try:
            await self.repo.create(restaurant)
        except IntegrityError as exc:
            await self.session.rollback()
            raise RestaurantSlugAlreadyExistsError(
                f"Restaurant slug '{target_slug}' is already in use."
            ) from exc

        return restaurant

    async def list_owner_restaurants(self, owner: User) -> Sequence[Restaurant]:
        """List all restaurants owned by the authenticated RESTAURANT user."""
        if owner.role != UserRole.RESTAURANT:
            raise UnauthorizedRestaurantAccessError(
                "Only users with RESTAURANT role can access their restaurant list."
            )
        return await self.repo.list_by_owner(owner.id)

    async def update_restaurant(
        self,
        owner: User,
        restaurant_id: uuid.UUID,
        payload: RestaurantUpdateRequest,
    ) -> Restaurant:
        """Update permitted profile fields for a restaurant owned by the caller.

        Raises:
            UnauthorizedRestaurantAccessError: If user does not own the restaurant or lacks role.
            RestaurantNotFoundError: If restaurant does not exist.
            InvalidRestaurantStatusError: If invalid status transition is attempted.
            RestaurantSlugAlreadyExistsError: If updated slug is already taken.
        """
        if owner.role != UserRole.RESTAURANT:
            raise UnauthorizedRestaurantAccessError(
                "Only users with RESTAURANT role can update a restaurant."
            )

        restaurant = await self.repo.get_by_id(restaurant_id)
        if restaurant is None:
            raise RestaurantNotFoundError(
                f"Restaurant with ID '{restaurant_id}' not found."
            )

        # Authoritative ownership verification
        if restaurant.owner_id != owner.id:
            raise UnauthorizedRestaurantAccessError(
                "You do not have permission to modify this restaurant."
            )

        # Status transition checks
        if payload.status is not None:
            if restaurant.status == RestaurantStatus.SUSPENDED:
                raise InvalidRestaurantStatusError(
                    "Suspended restaurants cannot be modified by the owner."
                )
            if payload.status == RestaurantStatus.SUSPENDED:
                raise InvalidRestaurantStatusError(
                    "Restaurant owners cannot suspend restaurants."
                )
            restaurant.status = payload.status

        # Slug uniqueness check if updating slug
        if payload.slug is not None:
            new_slug = slugify(payload.slug)
            if new_slug != restaurant.slug:
                existing = await self.repo.get_by_slug(new_slug)
                if existing is not None and existing.id != restaurant.id:
                    raise RestaurantSlugAlreadyExistsError(
                        f"Restaurant slug '{new_slug}' is already in use."
                    )
                restaurant.slug = new_slug

        # Update permitted fields
        if payload.name is not None:
            restaurant.name = payload.name.strip()
        if payload.description is not None:
            restaurant.description = (
                payload.description.strip() if payload.description else None
            )
        if payload.phone is not None:
            restaurant.phone = payload.phone.strip()
        if payload.address_line1 is not None:
            restaurant.address_line1 = payload.address_line1.strip()
        if payload.address_line2 is not None:
            restaurant.address_line2 = (
                payload.address_line2.strip() if payload.address_line2 else None
            )
        if payload.city is not None:
            restaurant.city = payload.city.strip()
        if payload.state is not None:
            restaurant.state = payload.state.strip()
        if payload.postal_code is not None:
            restaurant.postal_code = payload.postal_code.strip()
        if payload.latitude is not None:
            restaurant.latitude = payload.latitude
        if payload.longitude is not None:
            restaurant.longitude = payload.longitude

        try:
            await self.repo.update(restaurant)
        except IntegrityError as exc:
            await self.session.rollback()
            raise RestaurantSlugAlreadyExistsError(
                "Failed to update restaurant due to a uniqueness constraint conflict."
            ) from exc

        return restaurant
