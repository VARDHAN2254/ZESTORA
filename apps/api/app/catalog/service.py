"""Business logic coordinator for catalog and menu operations."""

import uuid
from collections import defaultdict
from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.exceptions import (
    InvalidCategoryAssignmentError,
    InvalidPriceError,
    MenuCategoryAlreadyExistsError,
    MenuCategoryNotFoundError,
    MenuItemInUseError,
    MenuItemNotFoundError,
)
from app.catalog.models import MenuCategory, MenuItem
from app.catalog.repository import CatalogRepository
from app.catalog.schemas import (
    MenuCategoryCreateRequest,
    MenuCategoryUpdateRequest,
    MenuCategoryWithItemsResponse,
    MenuItemCreateRequest,
    MenuItemResponse,
    MenuItemUpdateRequest,
)
from app.identity.enums import UserRole
from app.identity.models import User
from app.restaurants.enums import RestaurantStatus
from app.restaurants.exceptions import (
    RestaurantNotFoundError,
    UnauthorizedRestaurantAccessError,
)
from app.restaurants.models import Restaurant
from app.restaurants.repository import RestaurantRepository


class CatalogService:
    """Service layer managing public menu browsing and owner menu administration."""

    def __init__(
        self,
        session: AsyncSession,
        catalog_repo: CatalogRepository | None = None,
        restaurant_repo: RestaurantRepository | None = None,
    ) -> None:
        self.session = session
        self.catalog_repo = catalog_repo or CatalogRepository(session)
        self.restaurant_repo = restaurant_repo or RestaurantRepository(session)

    # ==============================================================================
    # 1. PUBLIC MENU BROWSING
    # ==============================================================================

    async def resolve_active_restaurant(
        self, identifier: str | uuid.UUID
    ) -> Restaurant:
        """Resolve a restaurant by slug or UUID and ensure it is active.

        Raises:
            RestaurantNotFoundError: If restaurant is not found or not ACTIVE.
        """
        restaurant: Restaurant | None = None
        if isinstance(identifier, uuid.UUID):
            restaurant = await self.restaurant_repo.get_by_id(identifier)
        else:
            ident_str = str(identifier).strip()
            # Try UUID parsing first if string has UUID structure
            try:
                parsed_uuid = uuid.UUID(ident_str)
                restaurant = await self.restaurant_repo.get_by_id(parsed_uuid)
            except ValueError:
                pass

            if restaurant is None:
                restaurant = await self.restaurant_repo.get_by_slug(ident_str.lower())

        if restaurant is None or restaurant.status != RestaurantStatus.ACTIVE:
            raise RestaurantNotFoundError(f"Restaurant '{identifier}' not found.")
        return restaurant

    async def list_public_categories(
        self, restaurant_slug: str
    ) -> tuple[Restaurant, Sequence[MenuCategory]]:
        """List active categories for an active restaurant."""
        restaurant = await self.resolve_active_restaurant(restaurant_slug)
        categories = await self.catalog_repo.list_active_categories(restaurant.id)
        return restaurant, categories

    async def list_public_items(
        self, restaurant_slug: str, category_id: uuid.UUID | None = None
    ) -> tuple[Restaurant, Sequence[MenuItem]]:
        """List available menu items for an active restaurant."""
        restaurant = await self.resolve_active_restaurant(restaurant_slug)

        if category_id is not None:
            category = await self.catalog_repo.get_category_by_id_and_restaurant(
                category_id=category_id, restaurant_id=restaurant.id
            )
            if category is None or not category.is_active:
                raise MenuCategoryNotFoundError(
                    f"Menu category '{category_id}' not found for this restaurant."
                )

        items = await self.catalog_repo.list_available_items(
            restaurant_id=restaurant.id, category_id=category_id
        )
        return restaurant, items

    async def get_public_menu(
        self, restaurant_slug: str
    ) -> tuple[Restaurant, list[MenuCategoryWithItemsResponse]]:
        """Load complete public menu without N+1 query overhead.

        Executes exactly two queries: one for active categories and one for available items.
        """
        restaurant = await self.resolve_active_restaurant(restaurant_slug)
        categories = await self.catalog_repo.list_active_categories(restaurant.id)
        items = await self.catalog_repo.list_available_items(restaurant.id)

        items_by_cat: dict[uuid.UUID, list[MenuItemResponse]] = defaultdict(list)
        for item in items:
            items_by_cat[item.category_id].append(MenuItemResponse.model_validate(item))

        result: list[MenuCategoryWithItemsResponse] = []
        for cat in categories:
            result.append(
                MenuCategoryWithItemsResponse(
                    id=cat.id,
                    restaurant_id=cat.restaurant_id,
                    name=cat.name,
                    description=cat.description,
                    display_order=cat.display_order,
                    is_active=cat.is_active,
                    items=items_by_cat.get(cat.id, []),
                )
            )

        return restaurant, result

    async def get_public_item(
        self, restaurant_slug: str, item_id: uuid.UUID
    ) -> tuple[Restaurant, MenuItem]:
        """Retrieve a specific available menu item for an active restaurant."""
        restaurant = await self.resolve_active_restaurant(restaurant_slug)
        item = await self.catalog_repo.get_item_by_id_and_restaurant(
            item_id=item_id, restaurant_id=restaurant.id
        )
        if item is None or not item.is_available:
            raise MenuItemNotFoundError(
                f"Menu item '{item_id}' not found for this restaurant."
            )

        category = await self.catalog_repo.get_category_by_id_and_restaurant(
            category_id=item.category_id, restaurant_id=restaurant.id
        )
        if category is None or not category.is_active:
            raise MenuItemNotFoundError(f"Menu item '{item_id}' category is inactive.")

        return restaurant, item

    # ==============================================================================
    # 2. RESTAURANT OWNER MENU MANAGEMENT
    # ==============================================================================

    async def _verify_restaurant_ownership(
        self, owner: User, restaurant_id: uuid.UUID
    ) -> Restaurant:
        """Verify that the user has RESTAURANT role and owns the target restaurant."""
        if owner.role != UserRole.RESTAURANT:
            raise UnauthorizedRestaurantAccessError(
                "Only users with RESTAURANT role can manage menus."
            )

        restaurant = await self.restaurant_repo.get_by_id(restaurant_id)
        if restaurant is None:
            raise RestaurantNotFoundError(f"Restaurant '{restaurant_id}' not found.")

        if restaurant.owner_id != owner.id:
            raise UnauthorizedRestaurantAccessError(
                "You do not have permission to manage this restaurant's menu."
            )

        return restaurant

    async def create_category(
        self,
        owner: User,
        restaurant_id: uuid.UUID,
        payload: MenuCategoryCreateRequest,
    ) -> MenuCategory:
        """Create a new menu category for the caller's restaurant."""
        await self._verify_restaurant_ownership(owner, restaurant_id)

        existing = await self.catalog_repo.get_category_by_name_and_restaurant(
            name=payload.name, restaurant_id=restaurant_id
        )
        if existing is not None:
            raise MenuCategoryAlreadyExistsError(
                f"A category named '{payload.name}' already exists for this restaurant."
            )

        category = MenuCategory(
            restaurant_id=restaurant_id,
            name=payload.name.strip(),
            description=payload.description.strip() if payload.description else None,
            display_order=payload.display_order,
            is_active=payload.is_active,
        )

        try:
            await self.catalog_repo.create_category(category)
        except IntegrityError as exc:
            await self.session.rollback()
            raise MenuCategoryAlreadyExistsError(
                f"Category '{payload.name}' already exists for this restaurant."
            ) from exc

        return category

    async def update_category(
        self,
        owner: User,
        restaurant_id: uuid.UUID,
        category_id: uuid.UUID,
        payload: MenuCategoryUpdateRequest,
    ) -> MenuCategory:
        """Update an existing menu category."""
        await self._verify_restaurant_ownership(owner, restaurant_id)

        category = await self.catalog_repo.get_category_by_id_and_restaurant(
            category_id=category_id, restaurant_id=restaurant_id
        )
        if category is None:
            raise MenuCategoryNotFoundError(
                f"Category '{category_id}' not found in this restaurant."
            )

        if (
            payload.name is not None
            and payload.name.strip().lower() != category.name.lower()
        ):
            existing = await self.catalog_repo.get_category_by_name_and_restaurant(
                name=payload.name, restaurant_id=restaurant_id
            )
            if existing is not None and existing.id != category.id:
                raise MenuCategoryAlreadyExistsError(
                    f"A category named '{payload.name}' already exists for this restaurant."
                )
            category.name = payload.name.strip()

        if payload.description is not None:
            category.description = (
                payload.description.strip() if payload.description else None
            )
        if payload.display_order is not None:
            category.display_order = payload.display_order
        if payload.is_active is not None:
            category.is_active = payload.is_active

        try:
            await self.catalog_repo.update_category(category)
        except IntegrityError as exc:
            await self.session.rollback()
            raise MenuCategoryAlreadyExistsError(
                "Failed to update category due to a name collision."
            ) from exc

        return category

    async def delete_category(
        self,
        owner: User,
        restaurant_id: uuid.UUID,
        category_id: uuid.UUID,
    ) -> None:
        """Delete a menu category if no historical order items depend on it."""
        await self._verify_restaurant_ownership(owner, restaurant_id)

        category = await self.catalog_repo.get_category_by_id_and_restaurant(
            category_id=category_id, restaurant_id=restaurant_id
        )
        if category is None:
            raise MenuCategoryNotFoundError(
                f"Category '{category_id}' not found in this restaurant."
            )

        try:
            await self.catalog_repo.delete_category(category)
        except IntegrityError as exc:
            await self.session.rollback()
            raise MenuItemInUseError(
                "Category contains items referenced in historical orders and cannot be deleted. "
                "Deactivate the category by setting is_active=false instead."
            ) from exc

    async def create_item(
        self,
        owner: User,
        restaurant_id: uuid.UUID,
        payload: MenuItemCreateRequest,
    ) -> MenuItem:
        """Create a new menu item belonging to the restaurant."""
        await self._verify_restaurant_ownership(owner, restaurant_id)

        if payload.price < Decimal("0.00"):
            raise InvalidPriceError("Price must be a non-negative value.")

        # Enforce that category belongs to the SAME restaurant
        category = await self.catalog_repo.get_category_by_id_and_restaurant(
            category_id=payload.category_id, restaurant_id=restaurant_id
        )
        if category is None:
            raise InvalidCategoryAssignmentError(
                f"Category '{payload.category_id}' does not belong to this restaurant."
            )

        item = MenuItem(
            restaurant_id=restaurant_id,
            category_id=payload.category_id,
            name=payload.name.strip(),
            description=payload.description.strip() if payload.description else None,
            price=payload.price,
            is_available=payload.is_available,
        )

        try:
            await self.catalog_repo.create_item(item)
        except IntegrityError as exc:
            await self.session.rollback()
            raise InvalidCategoryAssignmentError(
                "Failed to associate menu item with the requested category."
            ) from exc

        return item

    async def update_item(
        self,
        owner: User,
        restaurant_id: uuid.UUID,
        item_id: uuid.UUID,
        payload: MenuItemUpdateRequest,
    ) -> MenuItem:
        """Update permitted fields of a menu item."""
        await self._verify_restaurant_ownership(owner, restaurant_id)

        item = await self.catalog_repo.get_item_by_id_and_restaurant(
            item_id=item_id, restaurant_id=restaurant_id
        )
        if item is None:
            raise MenuItemNotFoundError(
                f"Menu item '{item_id}' not found in this restaurant."
            )

        if payload.category_id is not None and payload.category_id != item.category_id:
            category = await self.catalog_repo.get_category_by_id_and_restaurant(
                category_id=payload.category_id, restaurant_id=restaurant_id
            )
            if category is None:
                raise InvalidCategoryAssignmentError(
                    f"Category '{payload.category_id}' does not belong to this restaurant."
                )
            item.category_id = payload.category_id

        if payload.price is not None:
            if payload.price < Decimal("0.00"):
                raise InvalidPriceError("Price must be a non-negative value.")
            item.price = payload.price

        if payload.name is not None:
            item.name = payload.name.strip()
        if payload.description is not None:
            item.description = (
                payload.description.strip() if payload.description else None
            )
        if payload.is_available is not None:
            item.is_available = payload.is_available

        try:
            await self.catalog_repo.update_item(item)
        except IntegrityError as exc:
            await self.session.rollback()
            raise InvalidCategoryAssignmentError(
                "Failed to update menu item due to constraint violation."
            ) from exc

        return item

    async def delete_or_deactivate_item(
        self,
        owner: User,
        restaurant_id: uuid.UUID,
        item_id: uuid.UUID,
    ) -> None:
        """Safely delete menu item, rejecting deletion if referenced in historical orders."""
        await self._verify_restaurant_ownership(owner, restaurant_id)

        item = await self.catalog_repo.get_item_by_id_and_restaurant(
            item_id=item_id, restaurant_id=restaurant_id
        )
        if item is None:
            raise MenuItemNotFoundError(
                f"Menu item '{item_id}' not found in this restaurant."
            )

        # Protect historical orders
        order_count = await self.catalog_repo.count_historical_orders_for_item(item.id)
        if order_count > 0:
            raise MenuItemInUseError(
                f"Menu item '{item.name}' cannot be deleted because it is part of {order_count} "
                "historical order(s). Deactivate it by setting is_available=false instead."
            )

        try:
            await self.catalog_repo.delete_item(item)
        except IntegrityError as exc:
            await self.session.rollback()
            raise MenuItemInUseError(
                f"Menu item '{item.name}' cannot be deleted due to order history constraints. "
                "Deactivate it by setting is_available=false instead."
            ) from exc
