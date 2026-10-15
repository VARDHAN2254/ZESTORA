"""Cart service implementing application boundary logic and role enforcement."""

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.cart.exceptions import (
    CartItemNotFoundError,
    CartNotFoundError,
    CartRestaurantConflictError,
    InvalidQuantityError,
    MenuItemUnavailableError,
    RestaurantNotEligibleError,
    UnauthorizedCartAccessError,
)
from app.cart.models import Cart, CartItem
from app.cart.pricing import PricedCart, calculate_cart_pricing
from app.cart.repository import CartRepository
from app.catalog.models import MenuItem
from app.identity.enums import UserRole
from app.identity.models import User
from app.restaurants.enums import RestaurantStatus
from app.restaurants.models import Restaurant


def utc_now() -> datetime:
    """Return timezone-aware UTC datetime."""
    return datetime.now(UTC)


class CartService:
    """Business logic coordinator for customer shopping cart operations."""

    def __init__(
        self,
        session: AsyncSession,
        cart_repo: CartRepository | None = None,
    ) -> None:
        self.session = session
        self.cart_repo = cart_repo or CartRepository(session)

    @staticmethod
    def _validate_customer(user: User) -> None:
        """Enforce that only users with CUSTOMER role can perform cart operations."""
        if user.role != UserRole.CUSTOMER:
            role_val = (
                user.role.value if isinstance(user.role, UserRole) else str(user.role)
            )
            raise UnauthorizedCartAccessError(
                f"User with role '{role_val}' cannot perform cart operations. "
                "Only CUSTOMER accounts are allowed."
            )

    async def get_or_create_cart(self, user: User) -> Cart:
        """Retrieve existing persistent cart or create an empty one."""
        self._validate_customer(user)
        return await self.cart_repo.get_or_create(user.id)

    async def get_cart(self, user: User) -> Cart:
        """Retrieve customer's persistent cart, creating one if not yet present."""
        self._validate_customer(user)
        return await self.cart_repo.get_or_create(user.id)

    async def add_item(
        self,
        user: User,
        menu_item_id: uuid.UUID,
        quantity: int = 1,
    ) -> Cart:
        """Add a menu item to the customer's cart or increment quantity if already present.

        Enforces:
        - Role check (CUSTOMER only).
        - Quantity > 0.
        - Menu item existence and availability.
        - Restaurant status is ACTIVE.
        - Single-restaurant invariant: rejects cross-restaurant items without clearing cart.
        - Increment policy for existing cart lines.
        """
        self._validate_customer(user)
        if quantity <= 0:
            raise InvalidQuantityError("Quantity must be a positive integer.")

        # Authoritative database lookup of menu item
        menu_item = await self.session.get(MenuItem, menu_item_id)
        if menu_item is None:
            raise MenuItemUnavailableError(
                f"Menu item '{menu_item_id}' not found in the catalog."
            )

        if not menu_item.is_available:
            raise MenuItemUnavailableError(
                f"Menu item '{menu_item.name}' is currently unavailable."
            )

        # Validate restaurant eligibility
        restaurant = await self.session.get(Restaurant, menu_item.restaurant_id)
        if restaurant is None or restaurant.status != RestaurantStatus.ACTIVE:
            status_val = restaurant.status.value if restaurant else "NOT_FOUND"
            raise RestaurantNotEligibleError(
                f"Restaurant is not eligible to accept orders (status: {status_val})."
            )

        cart = await self.cart_repo.get_or_create(user.id)

        # Single-restaurant invariant
        if (
            cart.restaurant_id is not None
            and cart.restaurant_id != menu_item.restaurant_id
        ):
            raise CartRestaurantConflictError(
                f"Cannot add item from a different restaurant. "
                f"Cart is locked to restaurant '{cart.restaurant_id}', "
                f"attempted to add item from restaurant '{menu_item.restaurant_id}'."
            )

        if cart.restaurant_id is None:
            cart.restaurant_id = menu_item.restaurant_id

        # Check for duplicate item line
        existing_item = next(
            (item for item in cart.items if item.menu_item_id == menu_item.id),
            None,
        )

        if existing_item is not None:
            # Increment quantity
            existing_item.quantity += quantity
            existing_item.updated_at = utc_now()
        else:
            new_item = CartItem(
                cart_id=cart.id,
                restaurant_id=menu_item.restaurant_id,
                menu_item_id=menu_item.id,
                quantity=quantity,
            )
            cart.items.append(new_item)

        cart.updated_at = utc_now()
        await self.session.flush()
        return cart

    async def update_item_quantity(
        self,
        user: User,
        menu_item_id: uuid.UUID,
        quantity: int,
    ) -> Cart:
        """Update the quantity of an existing cart line."""
        self._validate_customer(user)
        if quantity <= 0:
            raise InvalidQuantityError("Quantity must be a positive integer.")

        cart = await self.cart_repo.get_by_customer_id(user.id, include_items=True)
        if cart is None:
            raise CartNotFoundError("Cart not found.")

        existing_item = next(
            (item for item in cart.items if item.menu_item_id == menu_item_id),
            None,
        )
        if existing_item is None:
            raise CartItemNotFoundError(
                f"Menu item '{menu_item_id}' is not in the cart."
            )

        existing_item.quantity = quantity
        existing_item.updated_at = utc_now()
        cart.updated_at = utc_now()
        await self.session.flush()
        return cart

    async def remove_item(
        self,
        user: User,
        menu_item_id: uuid.UUID,
    ) -> Cart:
        """Remove a menu item line from the cart.

        If removing the final item, leaves the cart in a valid empty state
        with restaurant_id set to None.
        """
        self._validate_customer(user)
        cart = await self.cart_repo.get_by_customer_id(user.id, include_items=True)
        if cart is None:
            raise CartNotFoundError("Cart not found.")

        existing_item = next(
            (item for item in cart.items if item.menu_item_id == menu_item_id),
            None,
        )
        if existing_item is None:
            raise CartItemNotFoundError(
                f"Menu item '{menu_item_id}' is not in the cart."
            )

        cart.items.remove(existing_item)
        await self.session.delete(existing_item)

        if not cart.items:
            cart.restaurant_id = None

        cart.updated_at = utc_now()
        await self.session.flush()
        return cart

    async def clear_cart(self, user: User) -> Cart:
        """Empty the cart and reset restaurant_id to None."""
        self._validate_customer(user)
        cart = await self.cart_repo.get_or_create(user.id)
        await self.cart_repo.clear_cart(cart)
        return cart

    async def get_priced_cart(
        self,
        user: User,
        *,
        validate_eligibility: bool = True,
    ) -> PricedCart:
        """Calculate and return authoritative server-side cart pricing."""
        self._validate_customer(user)
        cart = await self.cart_repo.get_or_create(user.id)
        return await calculate_cart_pricing(
            self.session,
            cart,
            validate_eligibility=validate_eligibility,
        )
