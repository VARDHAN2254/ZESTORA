"""Restaurant repository providing async database operations for restaurants."""

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.restaurants.models import Restaurant


class RestaurantRepository:
    """Async repository for querying and persisting Restaurant entities."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, restaurant_id: uuid.UUID) -> Restaurant | None:
        """Retrieve a restaurant by primary key UUID."""
        result = await self.session.execute(
            select(Restaurant).where(Restaurant.id == restaurant_id)
        )
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> Restaurant | None:
        """Retrieve a restaurant by unique slug."""
        result = await self.session.execute(
            select(Restaurant).where(Restaurant.slug == slug)
        )
        return result.scalar_one_or_none()

    async def list_by_owner(self, owner_id: uuid.UUID) -> Sequence[Restaurant]:
        """List all restaurants belonging to an owner."""
        result = await self.session.execute(
            select(Restaurant).where(Restaurant.owner_id == owner_id)
        )
        return result.scalars().all()

    async def create(self, restaurant: Restaurant) -> Restaurant:
        """Add and flush a new restaurant entity."""
        self.session.add(restaurant)
        await self.session.flush()
        return restaurant
