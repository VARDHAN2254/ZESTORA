"""Checkout service orchestrating validation, server pricing, and atomic order creation."""

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.cart.exceptions import (
    MenuItemUnavailableError,
    RestaurantNotEligibleError,
    UnauthorizedCartAccessError,
)
from app.cart.repository import CartRepository
from app.catalog.models import MenuItem
from app.checkout.exceptions import (
    CheckoutRestaurantConflictError,
    EmptyCartCheckoutError,
)
from app.checkout.schemas import DeliveryAddressSnapshot
from app.identity.enums import UserRole
from app.identity.models import User
from app.orders.enums import OrderStatus
from app.orders.models import Order, OrderItem
from app.orders.repository import OrderRepository
from app.restaurants.enums import RestaurantStatus
from app.restaurants.models import Restaurant

TWO_PLACES = Decimal("0.01")


class CheckoutService:
    """Coordinates cart checkout flow into authoritative persistent Order records."""

    def __init__(
        self,
        session: AsyncSession,
        cart_repo: CartRepository | None = None,
        order_repo: OrderRepository | None = None,
    ) -> None:
        self.session = session
        self.cart_repo = cart_repo or CartRepository(session)
        self.order_repo = order_repo or OrderRepository(session)

    @staticmethod
    def _validate_customer(user: User) -> None:
        """Enforce that only users with CUSTOMER role can perform checkout."""
        if user.role != UserRole.CUSTOMER:
            role_val = (
                user.role.value if isinstance(user.role, UserRole) else str(user.role)
            )
            raise UnauthorizedCartAccessError(
                f"User with role '{role_val}' cannot perform checkout. "
                "Only CUSTOMER accounts are allowed."
            )

    async def checkout(
        self,
        customer: User,
        delivery_address: DeliveryAddressSnapshot,
    ) -> Order:
        """Execute transactional checkout from customer's persistent cart.

        Steps:
        1. Validates customer role (CUSTOMER only).
        2. Validates delivery address snapshot.
        3. Loads customer cart from DB; rejects empty cart.
        4. Validates restaurant eligibility (status ACTIVE).
        5. Recalculates prices and availability from current database records.
        6. Ensures single-restaurant cross-line integrity.
        7. Creates Order in initial PENDING_PAYMENT status.
        8. Creates OrderItem snapshots for each line.
        9. Clears the cart and flushes atomically.
        10. Leaves cart unchanged if validation or creation fails.
        """
        self._validate_customer(customer)
        delivery_address.validate()

        cart = await self.cart_repo.get_by_customer_id(customer.id, include_items=True)
        if cart is None or not cart.items:
            raise EmptyCartCheckoutError("Cannot checkout with an empty cart.")

        if cart.restaurant_id is None:
            raise EmptyCartCheckoutError("Cart has no restaurant assigned.")

        # Authoritative restaurant status check
        restaurant = await self.session.get(Restaurant, cart.restaurant_id)
        if restaurant is None or restaurant.status != RestaurantStatus.ACTIVE:
            status_val = restaurant.status.value if restaurant else "NOT_FOUND"
            raise RestaurantNotEligibleError(
                f"Restaurant is not eligible to accept orders (status: {status_val})."
            )

        # Recalculate prices and validate items from database immediately before order creation
        order_items_data: list[tuple[MenuItem, int, Decimal, Decimal]] = []
        calculated_subtotal = Decimal("0.00")

        for cart_item in cart.items:
            menu_item = await self.session.get(MenuItem, cart_item.menu_item_id)
            if menu_item is None:
                raise MenuItemUnavailableError(
                    f"Menu item '{cart_item.menu_item_id}' not found in the catalog."
                )

            if not menu_item.is_available:
                raise MenuItemUnavailableError(
                    f"Menu item '{menu_item.name}' is no longer available."
                )

            if menu_item.restaurant_id != cart.restaurant_id:
                raise CheckoutRestaurantConflictError(
                    f"Menu item '{menu_item.name}' belongs to a different restaurant "
                    f"({menu_item.restaurant_id}) than the cart ({cart.restaurant_id})."
                )

            unit_price = Decimal(str(menu_item.price)).quantize(TWO_PLACES)
            line_total = (unit_price * Decimal(cart_item.quantity)).quantize(TWO_PLACES)
            calculated_subtotal += line_total
            order_items_data.append(
                (menu_item, cart_item.quantity, unit_price, line_total)
            )

        subtotal = calculated_subtotal.quantize(TWO_PLACES)
        delivery_fee = Decimal("0.00")
        tax = Decimal("0.00")
        discount = Decimal("0.00")
        total = (subtotal + delivery_fee + tax - discount).quantize(TWO_PLACES)

        # Create Order using existing schema and initial status
        order = Order(
            customer_id=customer.id,
            restaurant_id=cart.restaurant_id,
            status=OrderStatus.PENDING_PAYMENT,
            subtotal=subtotal,
            delivery_fee=delivery_fee,
            tax=tax,
            discount=discount,
            total=total,
            currency="INR",
            delivery_address_line1=delivery_address.delivery_address_line1.strip(),
            delivery_address_line2=(
                delivery_address.delivery_address_line2.strip()
                if delivery_address.delivery_address_line2
                else None
            ),
            delivery_city=delivery_address.delivery_city.strip(),
            delivery_state=delivery_address.delivery_state.strip(),
            delivery_postal_code=delivery_address.delivery_postal_code.strip(),
            delivery_latitude=delivery_address.delivery_latitude,
            delivery_longitude=delivery_address.delivery_longitude,
            notes=delivery_address.notes,
        )

        # Create OrderItem historical snapshots
        for menu_item, quantity, unit_price, line_total in order_items_data:
            order_item = OrderItem(
                order_id=order.id,
                restaurant_id=order.restaurant_id,
                menu_item_id=menu_item.id,
                quantity=quantity,
                unit_price=unit_price,
                line_total=line_total,
                item_name=menu_item.name,
                item_description=menu_item.description,
            )
            order.items.append(order_item)

        # Persist order and clear cart atomically
        self.session.add(order)
        await self.cart_repo.clear_cart(cart)
        await self.session.flush()

        return order
