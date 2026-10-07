"""Catalog repository providing async database operations for categories and items."""

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.models import MenuCategory, MenuItem


class CatalogRepository:
    """Async repository for querying and persisting MenuCategory and MenuItem entities."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_category_by_id(self, category_id: uuid.UUID) -> MenuCategory | None:
        """Retrieve a menu category by primary key UUID."""
        result = await self.session.execute(
            select(MenuCategory).where(MenuCategory.id == category_id)
        )
        return result.scalar_one_or_none()

    async def list_categories_by_restaurant(
        self, restaurant_id: uuid.UUID
    ) -> Sequence[MenuCategory]:
        """List all menu categories for a restaurant ordered by display_order."""
        result = await self.session.execute(
            select(MenuCategory)
            .where(MenuCategory.restaurant_id == restaurant_id)
            .order_by(MenuCategory.display_order, MenuCategory.name)
        )
        return result.scalars().all()

    async def create_category(self, category: MenuCategory) -> MenuCategory:
        """Add and flush a new menu category."""
        self.session.add(category)
        await self.session.flush()
        return category

    async def get_item_by_id(self, item_id: uuid.UUID) -> MenuItem | None:
        """Retrieve a menu item by primary key UUID."""
        result = await self.session.execute(
            select(MenuItem).where(MenuItem.id == item_id)
        )
        return result.scalar_one_or_none()

    async def list_items_by_restaurant(
        self, restaurant_id: uuid.UUID
    ) -> Sequence[MenuItem]:
        """List all menu items for a restaurant."""
        result = await self.session.execute(
            select(MenuItem)
            .where(MenuItem.restaurant_id == restaurant_id)
            .order_by(MenuItem.name)
        )
        return result.scalars().all()

    async def list_items_by_category(
        self, category_id: uuid.UUID
    ) -> Sequence[MenuItem]:
        """List all menu items within a category."""
        result = await self.session.execute(
            select(MenuItem)
            .where(MenuItem.category_id == category_id)
            .order_by(MenuItem.name)
        )
        return result.scalars().all()

    async def create_item(self, item: MenuItem) -> MenuItem:
        """Add and flush a new menu item."""
        self.session.add(item)
        await self.session.flush()
        return item
