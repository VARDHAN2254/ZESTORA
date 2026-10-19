"""Cart domain module exposing models, repository, service, pricing, router, and exceptions."""

from app.cart.exceptions import (
    CartError,
    CartItemNotFoundError,
    CartNotFoundError,
    CartRestaurantConflictError,
    EmptyCartError,
    InvalidQuantityError,
    MenuItemUnavailableError,
    RestaurantNotEligibleError,
    UnauthorizedCartAccessError,
)
from app.cart.models import Cart, CartItem
from app.cart.pricing import PricedCart, PricedCartItem, calculate_cart_pricing
from app.cart.repository import CartRepository
from app.cart.router import router as cart_router
from app.cart.schemas import (
    CartItemAddRequest,
    CartItemResponse,
    CartItemUpdateRequest,
    CartResponse,
)
from app.cart.service import CartService

__all__ = [
    "Cart",
    "CartError",
    "CartItem",
    "CartItemAddRequest",
    "CartItemNotFoundError",
    "CartItemResponse",
    "CartItemUpdateRequest",
    "CartNotFoundError",
    "CartRepository",
    "CartResponse",
    "CartRestaurantConflictError",
    "CartService",
    "EmptyCartError",
    "InvalidQuantityError",
    "MenuItemUnavailableError",
    "PricedCart",
    "PricedCartItem",
    "RestaurantNotEligibleError",
    "UnauthorizedCartAccessError",
    "calculate_cart_pricing",
    "cart_router",
]
