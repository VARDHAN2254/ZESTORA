"""Catalog repository providing async database operations for categories and items."""

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.models import MenuCategory, MenuItem
from app.orders.models import OrderItem


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

    async def get_category_by_id_and_restaurant(
        self, category_id: uuid.UUID, restaurant_id: uuid.UUID
    ) -> MenuCategory | None:
        """Retrieve a category ensuring it belongs to the given restaurant."""
        result = await self.session.execute(
            select(MenuCategory).where(
                MenuCategory.id == category_id,
                MenuCategory.restaurant_id == restaurant_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_category_by_name_and_restaurant(
        self, name: str, restaurant_id: uuid.UUID
    ) -> MenuCategory | None:
        """Retrieve category by name within a restaurant."""
        result = await self.session.execute(
            select(MenuCategory).where(
                func.lower(MenuCategory.name) == name.lower().strip(),
                MenuCategory.restaurant_id == restaurant_id,
            )
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

    async def list_active_categories(
        self, restaurant_id: uuid.UUID
    ) -> Sequence[MenuCategory]:
        """List only active menu categories for a restaurant ordered by display_order."""
        result = await self.session.execute(
            select(MenuCategory)
            .where(
                MenuCategory.restaurant_id == restaurant_id,
                MenuCategory.is_active.is_(True),
            )
            .order_by(MenuCategory.display_order, MenuCategory.name)
        )
        return result.scalars().all()

    async def create_category(self, category: MenuCategory) -> MenuCategory:
        """Add and flush a new menu category."""
        self.session.add(category)
        await self.session.flush()
        return category

    async def update_category(self, category: MenuCategory) -> MenuCategory:
        """Flush an updated menu category."""
        await self.session.flush()
        return category

    async def delete_category(self, category: MenuCategory) -> None:
        """Delete a menu category."""
        await self.session.delete(category)
        await self.session.flush()

    async def get_item_by_id(self, item_id: uuid.UUID) -> MenuItem | None:
        """Retrieve a menu item by primary key UUID."""
        result = await self.session.execute(
            select(MenuItem).where(MenuItem.id == item_id)
        )
        return result.scalar_one_or_none()

    async def get_item_by_id_and_restaurant(
        self, item_id: uuid.UUID, restaurant_id: uuid.UUID
    ) -> MenuItem | None:
        """Retrieve a menu item ensuring it belongs to the given restaurant."""
        result = await self.session.execute(
            select(MenuItem).where(
                MenuItem.id == item_id,
                MenuItem.restaurant_id == restaurant_id,
            )
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

    async def list_available_items(
        self, restaurant_id: uuid.UUID, category_id: uuid.UUID | None = None
    ) -> Sequence[MenuItem]:
        """List only available menu items for a restaurant, optionally filtered by category."""
        query = select(MenuItem).where(
            MenuItem.restaurant_id == restaurant_id,
            MenuItem.is_available.is_(True),
        )
        if category_id is not None:
            query = query.where(MenuItem.category_id == category_id)
        query = query.order_by(MenuItem.name)
        result = await self.session.execute(query)
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

    async def update_item(self, item: MenuItem) -> MenuItem:
        """Flush an updated menu item."""
        await self.session.flush()
        return item

    async def delete_item(self, item: MenuItem) -> None:
        """Delete a menu item."""
        await self.session.delete(item)
        await self.session.flush()

    async def count_historical_orders_for_item(self, item_id: uuid.UUID) -> int:
        """Count how many order items reference this menu item."""
        result = await self.session.execute(
            select(func.count(OrderItem.id)).where(OrderItem.menu_item_id == item_id)
        )
        return int(result.scalar_one() or 0)
