"""Restaurant repository providing async database operations for restaurants."""

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.restaurants.enums import RestaurantStatus
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
            select(Restaurant)
            .where(Restaurant.owner_id == owner_id)
            .order_by(Restaurant.created_at.desc())
        )
        return result.scalars().all()

    async def list_active(
        self,
        skip: int = 0,
        limit: int = 50,
        city: str | None = None,
    ) -> Sequence[Restaurant]:
        """List active restaurants eligible for public discovery with optional city filter and pagination."""
        query = select(Restaurant).where(Restaurant.status == RestaurantStatus.ACTIVE)
        if city:
            query = query.where(func.lower(Restaurant.city) == city.lower().strip())
        query = query.order_by(Restaurant.name.asc()).offset(skip).limit(limit)
        result = await self.session.execute(query)
        return result.scalars().all()

    async def count_active(self, city: str | None = None) -> int:
        """Count total active restaurants eligible for public discovery."""
        query = select(func.count(Restaurant.id)).where(
            Restaurant.status == RestaurantStatus.ACTIVE
        )
        if city:
            query = query.where(func.lower(Restaurant.city) == city.lower().strip())
        result = await self.session.execute(query)
        return int(result.scalar_one() or 0)

    async def create(self, restaurant: Restaurant) -> Restaurant:
        """Add and flush a new restaurant entity."""
        self.session.add(restaurant)
        await self.session.flush()
        return restaurant

    async def update(self, restaurant: Restaurant) -> Restaurant:
        """Flush an updated restaurant entity."""
        await self.session.flush()
        return restaurant
