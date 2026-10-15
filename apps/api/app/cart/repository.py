"""Cart repository providing async database operations for carts and cart items."""

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.cart.models import Cart, CartItem


class CartRepository:
    """Async repository for querying and persisting Cart entities."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_customer_id(
        self, customer_id: uuid.UUID, include_items: bool = True
    ) -> Cart | None:
        """Retrieve a cart by customer UUID."""
        stmt = select(Cart).where(Cart.customer_id == customer_id)
        if include_items:
            stmt = stmt.options(selectinload(Cart.items))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id(
        self, cart_id: uuid.UUID, include_items: bool = True
    ) -> Cart | None:
        """Retrieve a cart by primary key UUID."""
        stmt = select(Cart).where(Cart.id == cart_id)
        if include_items:
            stmt = stmt.options(selectinload(Cart.items))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_or_create(self, customer_id: uuid.UUID) -> Cart:
        """Get an existing cart for the customer or create and flush a new empty cart."""
        cart = await self.get_by_customer_id(customer_id, include_items=True)
        if cart is None:
            cart = Cart(customer_id=customer_id)
            self.session.add(cart)
            await self.session.flush()
        return cart

    async def create(self, cart: Cart) -> Cart:
        """Add and flush a new Cart entity."""
        self.session.add(cart)
        await self.session.flush()
        return cart

    async def get_cart_item(
        self, cart_id: uuid.UUID, menu_item_id: uuid.UUID
    ) -> CartItem | None:
        """Retrieve a specific CartItem by cart_id and menu_item_id."""
        result = await self.session.execute(
            select(CartItem).where(
                CartItem.cart_id == cart_id,
                CartItem.menu_item_id == menu_item_id,
            )
        )
        return result.scalar_one_or_none()

    async def remove_item(self, cart: Cart, menu_item_id: uuid.UUID) -> bool:
        """Remove a single item from the cart.

        If the cart becomes empty, reset restaurant_id to None.
        """
        item_to_remove = next(
            (item for item in cart.items if item.menu_item_id == menu_item_id),
            None,
        )
        if item_to_remove is None:
            return False

        cart.items.remove(item_to_remove)
        await self.session.delete(item_to_remove)
        if not cart.items:
            cart.restaurant_id = None
        await self.session.flush()
        return True

    async def clear_cart(self, cart: Cart) -> None:
        """Delete all items from the cart and reset restaurant_id to None."""
        await self.session.execute(delete(CartItem).where(CartItem.cart_id == cart.id))
        cart.restaurant_id = None
        cart.items.clear()
        await self.session.flush()
