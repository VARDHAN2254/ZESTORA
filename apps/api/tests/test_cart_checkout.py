"""Comprehensive tests for Cart and Checkout domain models, pricing, service, and migrations."""

import uuid
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import sqlalchemy as sa
from alembic.command import downgrade, upgrade
from alembic.config import Config

from app.cart import (
    Cart,
    CartItem,
    CartItemNotFoundError,
    CartNotFoundError,
    CartRepository,
    CartRestaurantConflictError,
    CartService,
    EmptyCartError,
    InvalidQuantityError,
    MenuItemUnavailableError,
    PricedCart,
    PricedCartItem,
    RestaurantNotEligibleError,
    UnauthorizedCartAccessError,
    calculate_cart_pricing,
)
from app.catalog.models import MenuItem
from app.checkout import (
    CheckoutError,
    CheckoutRestaurantConflictError,
    CheckoutService,
    DeliveryAddressSnapshot,
    EmptyCartCheckoutError,
    InvalidDeliveryAddressError,
)
from app.core.database import Base
from app.identity.enums import UserRole, UserStatus
from app.identity.models import User
from app.orders.enums import OrderStatus
from app.orders.models import Order, OrderItem
from app.restaurants.enums import RestaurantStatus
from app.restaurants.models import Restaurant

# ==============================================================================
# 1. DATABASE METADATA & SCHEMA TESTS
# ==============================================================================


def test_cart_table_metadata():
    """Verify Cart table registration, columns, nullability, constraints, and indexes."""
    assert "carts" in Base.metadata.tables
    table = Base.metadata.tables["carts"]

    # Primary key
    assert [col.name for col in table.primary_key.columns] == ["id"]
    assert isinstance(table.c.id.type, sa.Uuid)

    # Columns and nullability
    expected_cols = {
        "id": (False, sa.Uuid),
        "customer_id": (False, sa.Uuid),
        "restaurant_id": (True, sa.Uuid),
        "created_at": (False, sa.DateTime),
        "updated_at": (False, sa.DateTime),
    }

    for col_name, (nullable, expected_type) in expected_cols.items():
        assert col_name in table.columns, f"Column {col_name} missing from carts"
        col = table.columns[col_name]
        assert col.nullable is nullable
        assert isinstance(col.type, expected_type)

    # Foreign keys
    fk_targets = [(fk.column.table.name, fk.column.name) for fk in table.foreign_keys]
    assert ("users", "id") in fk_targets
    assert ("restaurants", "id") in fk_targets

    # Unique constraints
    unique_constraints = [
        c for c in table.constraints if isinstance(c, sa.UniqueConstraint)
    ]
    uq_col_sets = [{col.name for col in c.columns} for c in unique_constraints]
    assert {"customer_id"} in uq_col_sets
    assert {"id", "restaurant_id"} in uq_col_sets

    # Indexes
    index_names = {idx.name: [c.name for c in idx.columns] for idx in table.indexes}
    assert "ix_carts_customer_id" in index_names
    assert "ix_carts_restaurant_id" in index_names


def test_cart_item_table_metadata_and_integrity():
    """Verify CartItem table registration, composite foreign keys, constraints, and indexes."""
    assert "cart_items" in Base.metadata.tables
    table = Base.metadata.tables["cart_items"]

    # Primary key
    assert [col.name for col in table.primary_key.columns] == ["id"]
    assert isinstance(table.c.id.type, sa.Uuid)

    # Columns and nullability
    expected_cols = {
        "id": (False, sa.Uuid),
        "cart_id": (False, sa.Uuid),
        "restaurant_id": (False, sa.Uuid),
        "menu_item_id": (False, sa.Uuid),
        "quantity": (False, sa.Integer),
        "created_at": (False, sa.DateTime),
        "updated_at": (False, sa.DateTime),
    }

    for col_name, (nullable, expected_type) in expected_cols.items():
        assert col_name in table.columns, f"Column {col_name} missing from cart_items"
        col = table.columns[col_name]
        assert col.nullable is nullable
        assert isinstance(col.type, expected_type)

    # Composite Foreign Keys
    fk_constraints = [
        c for c in table.constraints if isinstance(c, sa.ForeignKeyConstraint)
    ]
    fk_details = [
        (
            [col.name for col in c.columns],
            c.referred_table.name,
            [col.name for col in c.elements],
            c.ondelete,
        )
        for c in fk_constraints
    ]

    # Verify cart composite FK: (cart_id, restaurant_id) -> carts(id, restaurant_id) ON DELETE CASCADE
    assert any(
        cols == ["cart_id", "restaurant_id"]
        and ref_table == "carts"
        and ondelete == "CASCADE"
        for cols, ref_table, _, ondelete in fk_details
    )

    # Verify menu item composite FK: (menu_item_id, restaurant_id) -> menu_items(id, restaurant_id) ON DELETE RESTRICT
    assert any(
        cols == ["menu_item_id", "restaurant_id"]
        and ref_table == "menu_items"
        and ondelete == "RESTRICT"
        for cols, ref_table, _, ondelete in fk_details
    )

    # Unique constraint on (cart_id, menu_item_id)
    unique_constraints = [
        c for c in table.constraints if isinstance(c, sa.UniqueConstraint)
    ]
    uq_col_sets = [{col.name for col in c.columns} for c in unique_constraints]
    assert {"cart_id", "menu_item_id"} in uq_col_sets

    # Check constraint on quantity > 0
    check_constraints = [
        c for c in table.constraints if isinstance(c, sa.CheckConstraint)
    ]
    sql_texts = [str(c.sqltext) for c in check_constraints]
    assert any("quantity > 0" in text for text in sql_texts)

    # Indexes
    index_names = {idx.name: [c.name for c in idx.columns] for idx in table.indexes}
    assert "ix_cart_items_cart_id" in index_names
    assert "ix_cart_items_menu_item_id" in index_names


def test_cart_relationships_declarations():
    """Verify ORM relationships configured across Cart, CartItem, User, Restaurant, MenuItem."""
    from sqlalchemy.orm import class_mapper

    # Cart mapper
    cart_mapper = class_mapper(Cart)
    assert "customer" in cart_mapper.relationships
    assert "restaurant" in cart_mapper.relationships
    assert "items" in cart_mapper.relationships

    # CartItem mapper
    item_mapper = class_mapper(CartItem)
    assert "cart" in item_mapper.relationships
    assert "menu_item" in item_mapper.relationships

    # User mapper
    user_mapper = class_mapper(User)
    assert "cart" in user_mapper.relationships


# ==============================================================================
# 2. MODEL INSTANTIATION & VALIDATION TESTS
# ==============================================================================


def test_cart_model_instantiation_and_defaults():
    """Verify Cart model instantiation with defaults and empty state support."""
    customer_id = uuid.uuid4()
    cart = Cart(customer_id=customer_id)

    assert cart.id is not None
    assert cart.customer_id == customer_id
    assert cart.restaurant_id is None
    assert cart.created_at is not None
    assert cart.updated_at is not None
    assert "Cart" in repr(cart)


def test_cart_item_instantiation_valid():
    """Verify CartItem model instantiation with valid positive quantity."""
    cart_id = uuid.uuid4()
    restaurant_id = uuid.uuid4()
    menu_item_id = uuid.uuid4()

    item = CartItem(
        cart_id=cart_id,
        restaurant_id=restaurant_id,
        menu_item_id=menu_item_id,
        quantity=3,
    )
    assert item.id is not None
    assert item.cart_id == cart_id
    assert item.restaurant_id == restaurant_id
    assert item.menu_item_id == menu_item_id
    assert item.quantity == 3
    assert item.created_at is not None
    assert item.updated_at is not None
    assert "CartItem" in repr(item)


def test_cart_item_instantiation_rejects_non_positive_quantity():
    """Verify CartItem instantiation rejects zero or negative quantity."""
    cart_id = uuid.uuid4()
    restaurant_id = uuid.uuid4()
    menu_item_id = uuid.uuid4()

    with pytest.raises(ValueError, match="positive integer"):
        CartItem(
            cart_id=cart_id,
            restaurant_id=restaurant_id,
            menu_item_id=menu_item_id,
            quantity=0,
        )

    with pytest.raises(ValueError, match="positive integer"):
        CartItem(
            cart_id=cart_id,
            restaurant_id=restaurant_id,
            menu_item_id=menu_item_id,
            quantity=-5,
        )


# ==============================================================================
# 3. CART SERVICE BUSINESS LOGIC & ROLE TESTS
# ==============================================================================


@pytest.fixture
def mock_customer():
    """Create a mock User with CUSTOMER role."""
    return User(
        id=uuid.uuid4(),
        email="customer@example.com",
        password_hash="hashed_pw",
        first_name="Jane",
        last_name="Doe",
        role=UserRole.CUSTOMER,
        status=UserStatus.ACTIVE,
    )


@pytest.fixture
def mock_non_customer():
    """Create a mock User with RESTAURANT role."""
    return User(
        id=uuid.uuid4(),
        email="owner@example.com",
        password_hash="hashed_pw",
        first_name="Chef",
        last_name="Owner",
        role=UserRole.RESTAURANT,
        status=UserStatus.ACTIVE,
    )


@pytest.fixture
def mock_active_restaurant():
    """Create a mock active Restaurant entity."""
    return Restaurant(
        id=uuid.uuid4(),
        owner_id=uuid.uuid4(),
        name="Tandoori Delights",
        slug="tandoori-delights",
        phone="+919876543210",
        address_line1="42 Main Road",
        city="Mumbai",
        state="Maharashtra",
        postal_code="400001",
        status=RestaurantStatus.ACTIVE,
    )


@pytest.fixture
def mock_menu_item(mock_active_restaurant):
    """Create a mock active MenuItem entity."""
    return MenuItem(
        id=uuid.uuid4(),
        restaurant_id=mock_active_restaurant.id,
        category_id=uuid.uuid4(),
        name="Butter Chicken",
        price=Decimal("350.00"),
        is_available=True,
    )


@pytest.mark.asyncio
async def test_cart_service_rejects_non_customer_role(mock_non_customer):
    """Verify cart operations reject users whose role is not CUSTOMER."""
    mock_session = AsyncMock()
    service = CartService(mock_session)

    with pytest.raises(UnauthorizedCartAccessError) as exc_info:
        await service.get_cart(mock_non_customer)
    assert "Only CUSTOMER accounts are allowed" in str(exc_info.value)

    with pytest.raises(UnauthorizedCartAccessError):
        await service.add_item(mock_non_customer, uuid.uuid4(), quantity=1)

    with pytest.raises(UnauthorizedCartAccessError):
        await service.update_item_quantity(mock_non_customer, uuid.uuid4(), quantity=2)

    with pytest.raises(UnauthorizedCartAccessError):
        await service.remove_item(mock_non_customer, uuid.uuid4())

    with pytest.raises(UnauthorizedCartAccessError):
        await service.clear_cart(mock_non_customer)


@pytest.mark.asyncio
async def test_cart_service_add_item_success(
    mock_customer, mock_active_restaurant, mock_menu_item
):
    """Verify adding an item to an empty cart sets restaurant_id and appends CartItem."""
    mock_session = AsyncMock()
    cart_repo = MagicMock(spec=CartRepository)

    cart = Cart(customer_id=mock_customer.id)
    cart.items = []
    cart_repo.get_or_create = AsyncMock(return_value=cart)

    # Mock DB lookups
    async def session_get(model, pk):
        if model is MenuItem and pk == mock_menu_item.id:
            return mock_menu_item
        if model is Restaurant and pk == mock_active_restaurant.id:
            return mock_active_restaurant
        return None

    mock_session.get = AsyncMock(side_effect=session_get)

    service = CartService(mock_session, cart_repo=cart_repo)
    result = await service.add_item(mock_customer, mock_menu_item.id, quantity=2)

    assert result.restaurant_id == mock_active_restaurant.id
    assert len(result.items) == 1
    assert result.items[0].menu_item_id == mock_menu_item.id
    assert result.items[0].quantity == 2
    mock_session.flush.assert_awaited()


@pytest.mark.asyncio
async def test_cart_service_add_existing_item_increments_quantity(
    mock_customer, mock_active_restaurant, mock_menu_item
):
    """Verify adding an already present item increments quantity instead of duplicating lines."""
    mock_session = AsyncMock()
    cart_repo = MagicMock(spec=CartRepository)

    cart = Cart(customer_id=mock_customer.id, restaurant_id=mock_active_restaurant.id)
    existing_item = CartItem(
        cart_id=cart.id,
        restaurant_id=mock_active_restaurant.id,
        menu_item_id=mock_menu_item.id,
        quantity=2,
    )
    cart.items = [existing_item]
    cart_repo.get_or_create = AsyncMock(return_value=cart)

    async def session_get(model, pk):
        if model is MenuItem and pk == mock_menu_item.id:
            return mock_menu_item
        if model is Restaurant and pk == mock_active_restaurant.id:
            return mock_active_restaurant
        return None

    mock_session.get = AsyncMock(side_effect=session_get)

    service = CartService(mock_session, cart_repo=cart_repo)
    result = await service.add_item(mock_customer, mock_menu_item.id, quantity=3)

    assert len(result.items) == 1
    assert result.items[0].quantity == 5  # 2 + 3
    mock_session.flush.assert_awaited()


@pytest.mark.asyncio
async def test_cart_service_rejects_item_from_different_restaurant(
    mock_customer, mock_active_restaurant
):
    """Verify adding an item from a different restaurant raises CartRestaurantConflictError and preserves cart."""
    mock_session = AsyncMock()
    cart_repo = MagicMock(spec=CartRepository)

    existing_restaurant_id = mock_active_restaurant.id
    different_restaurant_id = uuid.uuid4()

    cart = Cart(customer_id=mock_customer.id, restaurant_id=existing_restaurant_id)
    existing_item = CartItem(
        cart_id=cart.id,
        restaurant_id=existing_restaurant_id,
        menu_item_id=uuid.uuid4(),
        quantity=1,
    )
    cart.items = [existing_item]
    cart_repo.get_or_create = AsyncMock(return_value=cart)

    other_restaurant = Restaurant(
        id=different_restaurant_id,
        owner_id=uuid.uuid4(),
        name="Burger Joint",
        slug="burger-joint",
        phone="+919876543211",
        address_line1="12 High St",
        city="Mumbai",
        state="Maharashtra",
        postal_code="400001",
        status=RestaurantStatus.ACTIVE,
    )

    other_item = MenuItem(
        id=uuid.uuid4(),
        restaurant_id=different_restaurant_id,
        category_id=uuid.uuid4(),
        name="Cheeseburger",
        price=Decimal("200.00"),
        is_available=True,
    )

    async def session_get(model, pk):
        if model is MenuItem and pk == other_item.id:
            return other_item
        if model is Restaurant and pk == different_restaurant_id:
            return other_restaurant
        return None

    mock_session.get = AsyncMock(side_effect=session_get)

    service = CartService(mock_session, cart_repo=cart_repo)
    with pytest.raises(CartRestaurantConflictError) as exc_info:
        await service.add_item(mock_customer, other_item.id, quantity=1)

    assert "Cannot add item from a different restaurant" in str(exc_info.value)
    # Cart remains unchanged with existing item
    assert len(cart.items) == 1
    assert cart.restaurant_id == existing_restaurant_id


@pytest.mark.asyncio
async def test_cart_service_rejects_invalid_quantity(mock_customer):
    """Verify adding or updating with non-positive quantity raises InvalidQuantityError."""
    mock_session = AsyncMock()
    service = CartService(mock_session)

    with pytest.raises(InvalidQuantityError):
        await service.add_item(mock_customer, uuid.uuid4(), quantity=0)

    with pytest.raises(InvalidQuantityError):
        await service.add_item(mock_customer, uuid.uuid4(), quantity=-1)

    with pytest.raises(InvalidQuantityError):
        await service.update_item_quantity(mock_customer, uuid.uuid4(), quantity=0)


@pytest.mark.asyncio
async def test_cart_service_update_quantity_success(
    mock_customer, mock_active_restaurant, mock_menu_item
):
    """Verify updating the quantity of an existing item in cart."""
    mock_session = AsyncMock()
    cart_repo = MagicMock(spec=CartRepository)

    cart = Cart(customer_id=mock_customer.id, restaurant_id=mock_active_restaurant.id)
    item = CartItem(
        cart_id=cart.id,
        restaurant_id=mock_active_restaurant.id,
        menu_item_id=mock_menu_item.id,
        quantity=1,
    )
    cart.items = [item]
    cart_repo.get_by_customer_id = AsyncMock(return_value=cart)

    service = CartService(mock_session, cart_repo=cart_repo)
    result = await service.update_item_quantity(
        mock_customer, mock_menu_item.id, quantity=4
    )

    assert result.items[0].quantity == 4
    mock_session.flush.assert_awaited()


@pytest.mark.asyncio
async def test_cart_service_remove_item_leaves_valid_empty_state(
    mock_customer, mock_active_restaurant, mock_menu_item
):
    """Verify removing the final item leaves the cart in a valid empty state with restaurant_id=None."""
    mock_session = AsyncMock()
    mock_session.delete = AsyncMock()
    cart_repo = MagicMock(spec=CartRepository)

    cart = Cart(customer_id=mock_customer.id, restaurant_id=mock_active_restaurant.id)
    item = CartItem(
        cart_id=cart.id,
        restaurant_id=mock_active_restaurant.id,
        menu_item_id=mock_menu_item.id,
        quantity=2,
    )
    cart.items = [item]
    cart_repo.get_by_customer_id = AsyncMock(return_value=cart)

    service = CartService(mock_session, cart_repo=cart_repo)
    result = await service.remove_item(mock_customer, mock_menu_item.id)

    assert len(result.items) == 0
    assert result.restaurant_id is None
    mock_session.delete.assert_awaited_with(item)
    mock_session.flush.assert_awaited()


# ==============================================================================
# 4. SERVER-SIDE PRICING & VALIDATION TESTS
# ==============================================================================


@pytest.mark.asyncio
async def test_pricing_empty_cart(mock_customer):
    """Verify pricing an empty cart returns subtotal 0.00 without error unless required."""
    mock_session = AsyncMock()
    cart = Cart(customer_id=mock_customer.id)
    cart.items = []

    priced = await calculate_cart_pricing(
        mock_session, cart, validate_eligibility=True, require_items=False
    )
    assert priced.subtotal == Decimal("0.00")
    assert priced.item_count == 0
    assert len(priced.items) == 0
    assert priced.currency == "INR"

    with pytest.raises(EmptyCartError):
        await calculate_cart_pricing(
            mock_session, cart, validate_eligibility=True, require_items=True
        )


@pytest.mark.asyncio
async def test_pricing_multiple_items_decimal_precision(
    mock_customer, mock_active_restaurant
):
    """Verify authoritative Decimal subtotal and line calculations across multiple items."""
    mock_session = AsyncMock()

    item1 = MenuItem(
        id=uuid.uuid4(),
        restaurant_id=mock_active_restaurant.id,
        category_id=uuid.uuid4(),
        name="Paneer Butter Masala",
        price=Decimal("249.50"),
        is_available=True,
    )
    item2 = MenuItem(
        id=uuid.uuid4(),
        restaurant_id=mock_active_restaurant.id,
        category_id=uuid.uuid4(),
        name="Garlic Naan",
        price=Decimal("45.25"),
        is_available=True,
    )

    cart = Cart(customer_id=mock_customer.id, restaurant_id=mock_active_restaurant.id)
    cart_item1 = CartItem(
        cart_id=cart.id,
        restaurant_id=mock_active_restaurant.id,
        menu_item_id=item1.id,
        quantity=2,
    )
    cart_item2 = CartItem(
        cart_id=cart.id,
        restaurant_id=mock_active_restaurant.id,
        menu_item_id=item2.id,
        quantity=3,
    )
    cart.items = [cart_item1, cart_item2]

    async def session_get(model, pk):
        if model is MenuItem and pk == item1.id:
            return item1
        if model is MenuItem and pk == item2.id:
            return item2
        if model is Restaurant and pk == mock_active_restaurant.id:
            return mock_active_restaurant
        return None

    mock_session.get = AsyncMock(side_effect=session_get)

    priced = await calculate_cart_pricing(mock_session, cart)

    assert isinstance(priced, PricedCart)
    assert all(isinstance(i, PricedCartItem) for i in priced.items)

    # Expected: 2 * 249.50 = 499.00; 3 * 45.25 = 135.75; Total = 634.75
    assert priced.items[0].line_total == Decimal("499.00")
    assert priced.items[1].line_total == Decimal("135.75")
    assert priced.subtotal == Decimal("634.75")
    assert priced.item_count == 5
    assert isinstance(priced.subtotal, Decimal)


@pytest.mark.asyncio
async def test_pricing_detects_unavailable_item(mock_customer, mock_active_restaurant):
    """Verify pricing detects stale carts with unavailable menu items."""
    mock_session = AsyncMock()
    unavailable_item = MenuItem(
        id=uuid.uuid4(),
        restaurant_id=mock_active_restaurant.id,
        category_id=uuid.uuid4(),
        name="Special Biryani",
        price=Decimal("300.00"),
        is_available=False,  # Out of stock
    )

    cart = Cart(customer_id=mock_customer.id, restaurant_id=mock_active_restaurant.id)
    cart_item = CartItem(
        cart_id=cart.id,
        restaurant_id=mock_active_restaurant.id,
        menu_item_id=unavailable_item.id,
        quantity=1,
    )
    cart.items = [cart_item]

    async def session_get(model, pk):
        if model is MenuItem and pk == unavailable_item.id:
            return unavailable_item
        if model is Restaurant and pk == mock_active_restaurant.id:
            return mock_active_restaurant
        return None

    mock_session.get = AsyncMock(side_effect=session_get)

    with pytest.raises(MenuItemUnavailableError) as exc_info:
        await calculate_cart_pricing(mock_session, cart, validate_eligibility=True)
    assert "currently unavailable" in str(exc_info.value)


@pytest.mark.asyncio
async def test_pricing_detects_ineligible_restaurant(
    mock_customer, mock_active_restaurant
):
    """Verify pricing detects when a restaurant is no longer ACTIVE."""
    mock_session = AsyncMock()
    mock_active_restaurant.status = RestaurantStatus.SUSPENDED

    item = MenuItem(
        id=uuid.uuid4(),
        restaurant_id=mock_active_restaurant.id,
        category_id=uuid.uuid4(),
        name="Item",
        price=Decimal("100.00"),
        is_available=True,
    )

    cart = Cart(customer_id=mock_customer.id, restaurant_id=mock_active_restaurant.id)
    cart.items = [
        CartItem(
            cart_id=cart.id,
            restaurant_id=mock_active_restaurant.id,
            menu_item_id=item.id,
            quantity=1,
        )
    ]

    async def session_get(model, pk):
        if model is Restaurant and pk == mock_active_restaurant.id:
            return mock_active_restaurant
        if model is MenuItem and pk == item.id:
            return item
        return None

    mock_session.get = AsyncMock(side_effect=session_get)

    with pytest.raises(RestaurantNotEligibleError) as exc_info:
        await calculate_cart_pricing(mock_session, cart, validate_eligibility=True)
    assert "not eligible to accept orders" in str(exc_info.value)


# ==============================================================================
# 5. CHECKOUT BUSINESS LOGIC & TRANSACTION INTEGRITY TESTS
# ==============================================================================


@pytest.fixture
def valid_delivery_address():
    """Create a valid DeliveryAddressSnapshot."""
    return DeliveryAddressSnapshot(
        delivery_address_line1="Apartment 5B, Skyline Towers",
        delivery_address_line2="Near Cyber City",
        delivery_city="Bengaluru",
        delivery_state="Karnataka",
        delivery_postal_code="560001",
        delivery_latitude=Decimal("12.971598"),
        delivery_longitude=Decimal("77.594566"),
        notes="Please leave at the door.",
    )


def test_delivery_address_snapshot_validation():
    """Verify delivery address snapshot validates mandatory address components."""
    # Blank line1
    with pytest.raises(InvalidDeliveryAddressError, match="delivery_address_line1"):
        DeliveryAddressSnapshot(
            delivery_address_line1="",
            delivery_city="City",
            delivery_state="State",
            delivery_postal_code="123456",
        ).validate()

    # Blank city
    with pytest.raises(InvalidDeliveryAddressError, match="delivery_city"):
        DeliveryAddressSnapshot(
            delivery_address_line1="Line 1",
            delivery_city="   ",
            delivery_state="State",
            delivery_postal_code="123456",
        ).validate()

    # Blank state
    with pytest.raises(InvalidDeliveryAddressError, match="delivery_state"):
        DeliveryAddressSnapshot(
            delivery_address_line1="Line 1",
            delivery_city="City",
            delivery_state="",
            delivery_postal_code="123456",
        ).validate()

    # Blank postal code
    with pytest.raises(InvalidDeliveryAddressError, match="delivery_postal_code"):
        DeliveryAddressSnapshot(
            delivery_address_line1="Line 1",
            delivery_city="City",
            delivery_state="State",
            delivery_postal_code="",
        ).validate()


@pytest.mark.asyncio
async def test_checkout_successful_order_creation_and_snapshots(
    mock_customer, mock_active_restaurant, valid_delivery_address
):
    """Verify successful checkout creates Order and OrderItems with exact snapshots and initial status."""
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    cart_repo = MagicMock(spec=CartRepository)

    item1 = MenuItem(
        id=uuid.uuid4(),
        restaurant_id=mock_active_restaurant.id,
        category_id=uuid.uuid4(),
        name="Chicken Tikka",
        description="Juicy roasted chicken chunks",
        price=Decimal("300.00"),
        is_available=True,
    )
    item2 = MenuItem(
        id=uuid.uuid4(),
        restaurant_id=mock_active_restaurant.id,
        category_id=uuid.uuid4(),
        name="Roti",
        description="Fresh whole wheat bread",
        price=Decimal("20.00"),
        is_available=True,
    )

    cart = Cart(customer_id=mock_customer.id, restaurant_id=mock_active_restaurant.id)
    cart_item1 = CartItem(
        cart_id=cart.id,
        restaurant_id=mock_active_restaurant.id,
        menu_item_id=item1.id,
        quantity=2,
    )
    cart_item2 = CartItem(
        cart_id=cart.id,
        restaurant_id=mock_active_restaurant.id,
        menu_item_id=item2.id,
        quantity=4,
    )
    cart.items = [cart_item1, cart_item2]

    cart_repo.get_by_customer_id = AsyncMock(return_value=cart)
    cart_repo.clear_cart = AsyncMock()

    async def session_get(model, pk):
        if model is Restaurant and pk == mock_active_restaurant.id:
            return mock_active_restaurant
        if model is MenuItem and pk == item1.id:
            return item1
        if model is MenuItem and pk == item2.id:
            return item2
        return None

    mock_session.get = AsyncMock(side_effect=session_get)

    checkout_service = CheckoutService(mock_session, cart_repo=cart_repo)
    order = await checkout_service.checkout(mock_customer, valid_delivery_address)

    # 1. Order assertions
    assert isinstance(order, Order)
    assert order.customer_id == mock_customer.id
    assert order.restaurant_id == mock_active_restaurant.id
    assert order.status == OrderStatus.PENDING_PAYMENT
    assert order.subtotal == Decimal("680.00")  # (2*300) + (4*20)
    assert order.delivery_fee == Decimal("0.00")
    assert order.tax == Decimal("0.00")
    assert order.discount == Decimal("0.00")
    assert order.total == Decimal("680.00")
    assert order.currency == "INR"

    # Address snapshot assertions
    assert order.delivery_address_line1 == valid_delivery_address.delivery_address_line1
    assert order.delivery_address_line2 == valid_delivery_address.delivery_address_line2
    assert order.delivery_city == valid_delivery_address.delivery_city
    assert order.delivery_state == valid_delivery_address.delivery_state
    assert order.delivery_postal_code == valid_delivery_address.delivery_postal_code
    assert order.delivery_latitude == valid_delivery_address.delivery_latitude
    assert order.delivery_longitude == valid_delivery_address.delivery_longitude
    assert order.notes == valid_delivery_address.notes

    # 2. OrderItem assertions
    assert len(order.items) == 2
    order_item1 = next(i for i in order.items if i.menu_item_id == item1.id)
    assert isinstance(order_item1, OrderItem)
    assert order_item1.item_name == "Chicken Tikka"
    assert order_item1.item_description == "Juicy roasted chicken chunks"
    assert order_item1.unit_price == Decimal("300.00")
    assert order_item1.quantity == 2
    assert order_item1.line_total == Decimal("600.00")
    assert order_item1.restaurant_id == mock_active_restaurant.id

    order_item2 = next(i for i in order.items if i.menu_item_id == item2.id)
    assert isinstance(order_item2, OrderItem)
    assert order_item2.item_name == "Roti"
    assert order_item2.item_description == "Fresh whole wheat bread"
    assert order_item2.unit_price == Decimal("20.00")
    assert order_item2.quantity == 4
    assert order_item2.line_total == Decimal("80.00")

    # 3. Cart clearing and session flush
    mock_session.add.assert_called_once_with(order)
    cart_repo.clear_cart.assert_awaited_once_with(cart)
    mock_session.flush.assert_awaited()


@pytest.mark.asyncio
async def test_checkout_cross_restaurant_conflict(
    mock_customer, mock_active_restaurant, valid_delivery_address
):
    """Verify checkout rejects when a cart item belongs to a different restaurant than cart.restaurant_id."""
    mock_session = AsyncMock()
    cart_repo = MagicMock(spec=CartRepository)
    other_restaurant_id = uuid.uuid4()

    item = MenuItem(
        id=uuid.uuid4(),
        restaurant_id=other_restaurant_id,  # Cross-restaurant mismatch
        category_id=uuid.uuid4(),
        name="Mismatched Item",
        price=Decimal("150.00"),
        is_available=True,
    )

    cart = Cart(customer_id=mock_customer.id, restaurant_id=mock_active_restaurant.id)
    cart_item = CartItem(
        cart_id=cart.id,
        restaurant_id=mock_active_restaurant.id,
        menu_item_id=item.id,
        quantity=1,
    )
    cart.items = [cart_item]
    cart_repo.get_by_customer_id = AsyncMock(return_value=cart)

    async def session_get(model, pk):
        if model is Restaurant:
            return mock_active_restaurant
        if model is MenuItem:
            return item
        return None

    mock_session.get = AsyncMock(side_effect=session_get)

    checkout_service = CheckoutService(mock_session, cart_repo=cart_repo)
    with pytest.raises(CheckoutRestaurantConflictError) as exc_info:
        await checkout_service.checkout(mock_customer, valid_delivery_address)
    assert isinstance(exc_info.value, CheckoutError)


@pytest.mark.asyncio
async def test_cart_service_item_not_found(mock_customer, mock_active_restaurant):
    """Verify CartItemNotFoundError when attempting to update or remove an item not in cart."""
    mock_session = AsyncMock()
    cart_repo = MagicMock(spec=CartRepository)

    cart = Cart(customer_id=mock_customer.id, restaurant_id=mock_active_restaurant.id)
    cart.items = []
    cart_repo.get_by_customer_id = AsyncMock(return_value=cart)

    service = CartService(mock_session, cart_repo=cart_repo)
    missing_id = uuid.uuid4()

    with pytest.raises(CartItemNotFoundError):
        await service.update_item_quantity(mock_customer, missing_id, quantity=2)

    with pytest.raises(CartItemNotFoundError):
        await service.remove_item(mock_customer, missing_id)


@pytest.mark.asyncio
async def test_cart_service_cart_not_found(mock_customer):
    """Verify CartNotFoundError when attempting to update or remove from a non-existent cart."""
    mock_session = AsyncMock()
    cart_repo = MagicMock(spec=CartRepository)
    cart_repo.get_by_customer_id = AsyncMock(return_value=None)

    service = CartService(mock_session, cart_repo=cart_repo)
    item_id = uuid.uuid4()

    with pytest.raises(CartNotFoundError):
        await service.update_item_quantity(mock_customer, item_id, quantity=2)

    with pytest.raises(CartNotFoundError):
        await service.remove_item(mock_customer, item_id)


@pytest.mark.asyncio
async def test_cart_repository_crud_operations():
    """Verify CartRepository CRUD methods with mocked AsyncSession."""
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.delete = AsyncMock()
    repo = CartRepository(mock_session)

    # get_by_customer_id
    customer_id = uuid.uuid4()
    mock_cart = Cart(customer_id=customer_id)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_cart
    mock_session.execute.return_value = mock_result

    assert await repo.get_by_customer_id(customer_id) == mock_cart

    # get_by_id
    cart_id = uuid.uuid4()
    assert await repo.get_by_id(cart_id) == mock_cart

    # create
    new_cart = Cart(customer_id=uuid.uuid4())
    assert await repo.create(new_cart) == new_cart
    mock_session.add.assert_called_with(new_cart)
    mock_session.flush.assert_awaited()

    # get_or_create existing
    assert await repo.get_or_create(customer_id) == mock_cart

    # get_cart_item
    mock_item = MagicMock(spec=CartItem)
    mock_res_item = MagicMock()
    mock_res_item.scalar_one_or_none.return_value = mock_item
    mock_session.execute.return_value = mock_res_item
    assert await repo.get_cart_item(cart_id, uuid.uuid4()) == mock_item

    # remove_item found
    cart_with_items = Cart(customer_id=customer_id, restaurant_id=uuid.uuid4())
    menu_id = uuid.uuid4()
    item_line = CartItem(
        cart_id=cart_with_items.id,
        restaurant_id=cart_with_items.restaurant_id,
        menu_item_id=menu_id,
        quantity=1,
    )
    cart_with_items.items = [item_line]
    assert await repo.remove_item(cart_with_items, menu_id) is True
    assert cart_with_items.restaurant_id is None
    assert len(cart_with_items.items) == 0

    # remove_item not found
    assert await repo.remove_item(cart_with_items, uuid.uuid4()) is False


@pytest.mark.asyncio
async def test_checkout_rejects_empty_cart(mock_customer, valid_delivery_address):
    """Verify checkout rejects an empty cart without creating orders."""
    mock_session = AsyncMock()
    cart_repo = MagicMock(spec=CartRepository)

    cart = Cart(customer_id=mock_customer.id)
    cart.items = []
    cart_repo.get_by_customer_id = AsyncMock(return_value=cart)

    checkout_service = CheckoutService(mock_session, cart_repo=cart_repo)
    with pytest.raises(EmptyCartCheckoutError):
        await checkout_service.checkout(mock_customer, valid_delivery_address)


@pytest.mark.asyncio
async def test_checkout_authoritative_price_recalculation(
    mock_customer, mock_active_restaurant, valid_delivery_address
):
    """Verify checkout recalculates prices from DB immediately before order creation."""
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    cart_repo = MagicMock(spec=CartRepository)

    # Menu item price changed in database from 200.00 to 250.00
    updated_item = MenuItem(
        id=uuid.uuid4(),
        restaurant_id=mock_active_restaurant.id,
        category_id=uuid.uuid4(),
        name="Updated Price Pizza",
        price=Decimal("250.00"),
        is_available=True,
    )

    cart = Cart(customer_id=mock_customer.id, restaurant_id=mock_active_restaurant.id)
    cart_item = CartItem(
        cart_id=cart.id,
        restaurant_id=mock_active_restaurant.id,
        menu_item_id=updated_item.id,
        quantity=2,
    )
    cart.items = [cart_item]
    cart_repo.get_by_customer_id = AsyncMock(return_value=cart)
    cart_repo.clear_cart = AsyncMock()

    async def session_get(model, pk):
        if model is Restaurant:
            return mock_active_restaurant
        if model is MenuItem:
            return updated_item
        return None

    mock_session.get = AsyncMock(side_effect=session_get)

    checkout_service = CheckoutService(mock_session, cart_repo=cart_repo)
    order = await checkout_service.checkout(mock_customer, valid_delivery_address)

    # Order must reflect fresh 250.00 price (total 500.00)
    assert order.items[0].unit_price == Decimal("250.00")
    assert order.items[0].line_total == Decimal("500.00")
    assert order.subtotal == Decimal("500.00")
    assert order.total == Decimal("500.00")


@pytest.mark.asyncio
async def test_checkout_rejects_unavailable_items_and_preserves_cart(
    mock_customer, mock_active_restaurant, valid_delivery_address
):
    """Verify checkout rejects when an item is unavailable and leaves the cart unchanged."""
    mock_session = AsyncMock()
    cart_repo = MagicMock(spec=CartRepository)

    item = MenuItem(
        id=uuid.uuid4(),
        restaurant_id=mock_active_restaurant.id,
        category_id=uuid.uuid4(),
        name="Sold Out Dessert",
        price=Decimal("150.00"),
        is_available=False,  # Unavailable!
    )

    cart = Cart(customer_id=mock_customer.id, restaurant_id=mock_active_restaurant.id)
    cart_item = CartItem(
        cart_id=cart.id,
        restaurant_id=mock_active_restaurant.id,
        menu_item_id=item.id,
        quantity=1,
    )
    cart.items = [cart_item]
    cart_repo.get_by_customer_id = AsyncMock(return_value=cart)
    cart_repo.clear_cart = AsyncMock()

    async def session_get(model, pk):
        if model is Restaurant:
            return mock_active_restaurant
        if model is MenuItem:
            return item
        return None

    mock_session.get = AsyncMock(side_effect=session_get)

    checkout_service = CheckoutService(mock_session, cart_repo=cart_repo)
    with pytest.raises(MenuItemUnavailableError):
        await checkout_service.checkout(mock_customer, valid_delivery_address)

    # Cart must NOT be cleared when validation fails
    cart_repo.clear_cart.assert_not_called()
    assert len(cart.items) == 1


@pytest.mark.asyncio
async def test_checkout_rejects_ineligible_restaurant_and_preserves_cart(
    mock_customer, mock_active_restaurant, valid_delivery_address
):
    """Verify checkout rejects when restaurant is inactive and leaves the cart intact."""
    mock_session = AsyncMock()
    cart_repo = MagicMock(spec=CartRepository)
    mock_active_restaurant.status = RestaurantStatus.INACTIVE

    cart = Cart(customer_id=mock_customer.id, restaurant_id=mock_active_restaurant.id)
    cart_item = CartItem(
        cart_id=cart.id,
        restaurant_id=mock_active_restaurant.id,
        menu_item_id=uuid.uuid4(),
        quantity=1,
    )
    cart.items = [cart_item]
    cart_repo.get_by_customer_id = AsyncMock(return_value=cart)
    cart_repo.clear_cart = AsyncMock()

    async def session_get(model, pk):
        if model is Restaurant:
            return mock_active_restaurant
        return None

    mock_session.get = AsyncMock(side_effect=session_get)

    checkout_service = CheckoutService(mock_session, cart_repo=cart_repo)
    with pytest.raises(RestaurantNotEligibleError):
        await checkout_service.checkout(mock_customer, valid_delivery_address)

    cart_repo.clear_cart.assert_not_called()
    assert len(cart.items) == 1


# ==============================================================================
# 6. ALEMBIC MIGRATION OFFLINE SQL GENERATION TEST
# ==============================================================================


def test_cart_migration_sql_generation(capsys):
    """Verify offline SQL generation for upgrade and downgrade of cart foundation (0006)."""
    alembic_ini_path = Path(__file__).resolve().parent.parent / "alembic.ini"
    alembic_cfg = Config(str(alembic_ini_path))

    # Test upgrade head --sql
    upgrade(alembic_cfg, "head", sql=True)
    out, _ = capsys.readouterr()

    # Tables
    assert "CREATE TABLE carts" in out
    assert "CREATE TABLE cart_items" in out

    # Constraints
    assert "CONSTRAINT pk_carts PRIMARY KEY (id)" in out
    assert "CONSTRAINT pk_cart_items PRIMARY KEY (id)" in out
    assert "CONSTRAINT uq_carts_customer_id UNIQUE (customer_id)" in out
    assert "CONSTRAINT uq_carts_id_restaurant_id UNIQUE (id, restaurant_id)" in out
    assert (
        "CONSTRAINT uq_cart_items_cart_id_menu_item_id UNIQUE (cart_id, menu_item_id)"
        in out
    )
    assert "CONSTRAINT ck_cart_items_quantity_positive CHECK (quantity > 0)" in out

    # Composite Foreign Keys
    assert (
        "CONSTRAINT fk_cart_items_cart_id_restaurant_id FOREIGN KEY(cart_id, restaurant_id) REFERENCES carts (id, restaurant_id) ON DELETE CASCADE"
        in out
    )
    assert (
        "CONSTRAINT fk_cart_items_menu_item_id_restaurant_id FOREIGN KEY(menu_item_id, restaurant_id) REFERENCES menu_items (id, restaurant_id) ON DELETE RESTRICT"
        in out
    )

    # Indexes
    assert "CREATE INDEX ix_carts_customer_id ON carts (customer_id)" in out
    assert "CREATE INDEX ix_carts_restaurant_id ON carts (restaurant_id)" in out
    assert "CREATE INDEX ix_cart_items_cart_id ON cart_items (cart_id)" in out
    assert "CREATE INDEX ix_cart_items_menu_item_id ON cart_items (menu_item_id)" in out

    # Version bump
    assert (
        "UPDATE alembic_version SET version_num='0006_create_cart' WHERE alembic_version.version_num = '0005_create_delivery'"
        in out
    )

    # Test downgrade 0006 -> 0005 --sql
    downgrade(alembic_cfg, "0006_create_cart:0005_create_delivery", sql=True)
    out_down, _ = capsys.readouterr()

    assert "DROP INDEX ix_cart_items_menu_item_id" in out_down
    assert "DROP INDEX ix_cart_items_cart_id" in out_down
    assert "DROP TABLE cart_items" in out_down
    assert "DROP INDEX ix_carts_restaurant_id" in out_down
    assert "DROP INDEX ix_carts_customer_id" in out_down
    assert "DROP TABLE carts" in out_down
    assert (
        "UPDATE alembic_version SET version_num='0005_create_delivery' WHERE alembic_version.version_num = '0006_create_cart'"
        in out_down
    )
