"""Authoritative server-side cart pricing and validation."""

import uuid
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.cart.exceptions import (
    CartRestaurantConflictError,
    EmptyCartError,
    MenuItemUnavailableError,
    RestaurantNotEligibleError,
)
from app.cart.models import Cart
from app.catalog.models import MenuItem
from app.restaurants.enums import RestaurantStatus
from app.restaurants.models import Restaurant

TWO_PLACES = Decimal("0.01")


@dataclass(frozen=True)
class PricedCartItem:
    """Immutable snapshot of a priced cart item calculated from the database."""

    menu_item_id: uuid.UUID
    name: str
    description: str | None
    quantity: int
    unit_price: Decimal
    line_total: Decimal
    is_available: bool


@dataclass(frozen=True)
class PricedCart:
    """Immutable priced cart summary calculated strictly using Decimal arithmetic."""

    cart_id: uuid.UUID
    customer_id: uuid.UUID
    restaurant_id: uuid.UUID | None
    items: list[PricedCartItem] = field(default_factory=list)
    item_count: int = 0
    subtotal: Decimal = Decimal("0.00")
    currency: str = "INR"


async def calculate_cart_pricing(
    session: AsyncSession,
    cart: Cart,
    *,
    validate_eligibility: bool = True,
    require_items: bool = False,
) -> PricedCart:
    """Calculate authoritative server-side cart pricing from database records.

    Args:
        session: Active AsyncSession to fetch current catalog and restaurant records.
        cart: The customer's Cart model instance with its items.
        validate_eligibility: When True, checks menu item availability and restaurant status.
        require_items: When True, raises EmptyCartError if the cart contains no items.

    Returns:
        PricedCart containing line totals, subtotal, and item metadata.

    Raises:
        EmptyCartError: If require_items is True and the cart is empty.
        RestaurantNotEligibleError: If the restaurant is not in ACTIVE status.
        MenuItemUnavailableError: If a menu item does not exist or is marked unavailable.
        CartRestaurantConflictError: If a menu item belongs to a different restaurant.
    """
    if require_items and not cart.items:
        raise EmptyCartError("Cart is empty; pricing calculation requires items.")

    if not cart.items:
        return PricedCart(
            cart_id=cart.id,
            customer_id=cart.customer_id,
            restaurant_id=cart.restaurant_id,
            items=[],
            item_count=0,
            subtotal=Decimal("0.00"),
            currency="INR",
        )

    # Validate restaurant eligibility
    if validate_eligibility and cart.restaurant_id is not None:
        restaurant = await session.get(Restaurant, cart.restaurant_id)
        if restaurant is None or restaurant.status != RestaurantStatus.ACTIVE:
            status_val = restaurant.status.value if restaurant else "NOT_FOUND"
            raise RestaurantNotEligibleError(
                f"Restaurant is not eligible to accept orders (status: {status_val})."
            )

    priced_items: list[PricedCartItem] = []
    total_quantity = 0
    calculated_subtotal = Decimal("0.00")

    for item in cart.items:
        menu_item = await session.get(MenuItem, item.menu_item_id)
        if menu_item is None:
            raise MenuItemUnavailableError(
                f"Menu item '{item.menu_item_id}' no longer exists in the catalog."
            )

        if validate_eligibility:
            if not menu_item.is_available:
                raise MenuItemUnavailableError(
                    f"Menu item '{menu_item.name}' is currently unavailable."
                )
            if (
                cart.restaurant_id is not None
                and menu_item.restaurant_id != cart.restaurant_id
            ):
                raise CartRestaurantConflictError(
                    f"Menu item '{menu_item.name}' does not belong to the cart's restaurant."
                )

        # Decimal arithmetic only
        unit_price = Decimal(str(menu_item.price)).quantize(TWO_PLACES)
        line_total = (unit_price * Decimal(item.quantity)).quantize(TWO_PLACES)
        calculated_subtotal += line_total
        total_quantity += item.quantity

        priced_items.append(
            PricedCartItem(
                menu_item_id=menu_item.id,
                name=menu_item.name,
                description=menu_item.description,
                quantity=item.quantity,
                unit_price=unit_price,
                line_total=line_total,
                is_available=menu_item.is_available,
            )
        )

    return PricedCart(
        cart_id=cart.id,
        customer_id=cart.customer_id,
        restaurant_id=cart.restaurant_id,
        items=priced_items,
        item_count=total_quantity,
        subtotal=calculated_subtotal.quantize(TWO_PLACES),
        currency="INR",
    )
