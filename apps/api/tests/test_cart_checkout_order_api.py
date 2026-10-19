"""Comprehensive API tests for:
- Cart API (Add, Update, Remove, Clear, Invariants, Server pricing, Role enforcement)
- Checkout API (Transactional order creation, Address snapshot, Re-pricing, Atomic cart clear, Payment boundary)
- Customer Orders API (History list, Single order retrieval, Cross-customer isolation, Snapshot verification)
"""

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

import app.cart.models
import app.catalog.models
import app.delivery.models
import app.orders.models
import app.payments.models
import app.restaurants.models
from app.cart.pricing import PricedCart, PricedCartItem
from app.catalog.models import MenuItem
from app.checkout.exceptions import EmptyCartCheckoutError
from app.core.database import get_db
from app.identity.dependencies import require_customer
from app.identity.enums import UserRole, UserStatus
from app.identity.models import User
from app.main import app
from app.orders.enums import OrderStatus
from app.orders.models import Order, OrderItem
from app.restaurants.enums import RestaurantStatus
from app.restaurants.models import Restaurant

client = TestClient(app)


# ==============================================================================
# TEST FIXTURES & FACTORIES
# ==============================================================================


def make_user(
    role: UserRole = UserRole.CUSTOMER,
    status: UserStatus = UserStatus.ACTIVE,
    user_id: uuid.UUID | None = None,
) -> User:
    """Helper to create User instances for test auth."""
    uid = user_id or uuid.uuid4()
    return User(
        id=uid,
        email=f"customer-{uid.hex[:8]}@example.com",
        password_hash="argon2id$mockhash",
        first_name="Alice",
        last_name="Customer",
        role=role,
        status=status,
    )


def make_restaurant(
    restaurant_id: uuid.UUID | None = None,
    name: str = "Tandoor Treats",
    status: RestaurantStatus = RestaurantStatus.ACTIVE,
) -> Restaurant:
    """Helper to create Restaurant instances."""
    rid = restaurant_id or uuid.uuid4()
    return Restaurant(
        id=rid,
        owner_id=uuid.uuid4(),
        name=name,
        slug=f"rest-{rid.hex[:8]}",
        phone="+919876543210",
        address_line1="10 Food Plaza",
        city="Mumbai",
        state="Maharashtra",
        postal_code="400001",
        status=status,
    )


def make_menu_item(
    restaurant_id: uuid.UUID,
    name: str = "Butter Chicken",
    price: Decimal = Decimal("320.00"),
    is_available: bool = True,
    item_id: uuid.UUID | None = None,
) -> MenuItem:
    """Helper to create MenuItem instances."""
    return MenuItem(
        id=item_id or uuid.uuid4(),
        restaurant_id=restaurant_id,
        category_id=uuid.uuid4(),
        name=name,
        price=price,
        is_available=is_available,
    )


def make_priced_cart(
    customer_id: uuid.UUID,
    restaurant_id: uuid.UUID | None = None,
    items: list[PricedCartItem] | None = None,
) -> PricedCart:
    """Helper to create immutable PricedCart snapshots."""
    item_list = items or []
    subtotal = sum(i.line_total for i in item_list) if item_list else Decimal("0.00")
    item_count = sum(i.quantity for i in item_list) if item_list else 0
    return PricedCart(
        cart_id=uuid.uuid4(),
        customer_id=customer_id,
        restaurant_id=restaurant_id,
        items=item_list,
        item_count=item_count,
        subtotal=subtotal,
        currency="INR",
    )


# ==============================================================================
# 1. CART API TESTS
# ==============================================================================


def test_unauthenticated_cart_access_rejected():
    """Unauthenticated calls to /api/v1/cart return 401."""
    res1 = client.get("/api/v1/cart")
    assert res1.status_code == 401

    res2 = client.post(
        "/api/v1/cart/items", json={"menu_item_id": str(uuid.uuid4()), "quantity": 1}
    )
    assert res2.status_code == 401

    res3 = client.patch(f"/api/v1/cart/items/{uuid.uuid4()}", json={"quantity": 2})
    assert res3.status_code == 401

    res4 = client.delete(f"/api/v1/cart/items/{uuid.uuid4()}")
    assert res4.status_code == 401

    res5 = client.delete("/api/v1/cart")
    assert res5.status_code == 401


def test_non_customer_role_cannot_access_cart():
    """Users with RESTAURANT or DELIVERY_PARTNER role receive 403 Forbidden."""
    app.dependency_overrides[require_customer] = lambda: (_ for _ in ()).throw(
        pytest.importorskip("fastapi").HTTPException(
            status_code=403, detail="Insufficient permissions for this resource."
        )
    )
    try:
        res = client.get("/api/v1/cart")
        assert res.status_code == 403
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_empty_cart_success(monkeypatch):
    """GET /api/v1/cart returns an empty cart with server-side 0.00 subtotal."""
    customer = make_user()
    mock_session = AsyncMock()
    empty_priced = make_priced_cart(customer.id)

    app.dependency_overrides[require_customer] = lambda: customer
    app.dependency_overrides[get_db] = lambda: mock_session
    try:
        with monkeypatch.context() as mp:
            mock_service = MagicMock()
            mock_service.get_priced_cart = AsyncMock(return_value=empty_priced)
            mp.setattr("app.cart.router.CartService", lambda s: mock_service)

            response = client.get("/api/v1/cart")
            assert response.status_code == 200
            data = response.json()
            assert data["customer_id"] == str(customer.id)
            assert data["item_count"] == 0
            assert Decimal(data["subtotal"]) == Decimal("0.00")
            assert data["items"] == []
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_add_item_to_cart_success(monkeypatch):
    """POST /api/v1/cart/items adds an item and returns updated server pricing."""
    customer = make_user()
    rest_id = uuid.uuid4()
    item_id = uuid.uuid4()
    mock_session = AsyncMock()

    priced_item = PricedCartItem(
        menu_item_id=item_id,
        name="Butter Chicken",
        description="Rich curry",
        quantity=2,
        unit_price=Decimal("320.00"),
        line_total=Decimal("640.00"),
        is_available=True,
    )
    priced_cart = make_priced_cart(customer.id, rest_id, [priced_item])

    app.dependency_overrides[require_customer] = lambda: customer
    app.dependency_overrides[get_db] = lambda: mock_session
    try:
        with monkeypatch.context() as mp:
            mock_service = MagicMock()
            mock_service.add_item = AsyncMock(return_value=MagicMock())
            mock_service.get_priced_cart = AsyncMock(return_value=priced_cart)
            mp.setattr("app.cart.router.CartService", lambda s: mock_service)

            payload = {"menu_item_id": str(item_id), "quantity": 2}
            response = client.post("/api/v1/cart/items", json=payload)
            assert response.status_code == 200
            data = response.json()
            assert data["restaurant_id"] == str(rest_id)
            assert data["item_count"] == 2
            assert Decimal(data["subtotal"]) == Decimal("640.00")
            assert len(data["items"]) == 1
            assert data["items"][0]["name"] == "Butter Chicken"
            assert Decimal(data["items"][0]["line_total"]) == Decimal("640.00")
            mock_service.add_item.assert_called_once_with(
                user=customer, menu_item_id=item_id, quantity=2
            )
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_add_item_cross_restaurant_conflict_returns_409():
    """Attempting to add item from another restaurant returns 409 Conflict."""
    from app.cart.exceptions import CartRestaurantConflictError

    customer = make_user()
    mock_session = AsyncMock()

    app.dependency_overrides[require_customer] = lambda: customer
    app.dependency_overrides[get_db] = lambda: mock_session
    try:
        mock_service = MagicMock()
        mock_service.add_item = AsyncMock(
            side_effect=CartRestaurantConflictError(
                "Cannot add item from a different restaurant."
            )
        )
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("app.cart.router.CartService", lambda s: mock_service)

            res = client.post(
                "/api/v1/cart/items",
                json={"menu_item_id": str(uuid.uuid4()), "quantity": 1},
            )
            assert res.status_code == 409
            assert "different restaurant" in res.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_add_item_invalid_quantity_returns_422():
    """Quantities less than 1 are rejected with 422."""
    customer = make_user()
    app.dependency_overrides[require_customer] = lambda: customer
    try:
        res = client.post(
            "/api/v1/cart/items",
            json={"menu_item_id": str(uuid.uuid4()), "quantity": 0},
        )
        assert res.status_code == 422
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_update_item_quantity_success(monkeypatch):
    """PATCH /api/v1/cart/items/{id} updates line quantity and recalculates server pricing."""
    customer = make_user()
    item_id = uuid.uuid4()
    mock_session = AsyncMock()

    priced_item = PricedCartItem(
        menu_item_id=item_id,
        name="Naan",
        description="Fresh bread",
        quantity=4,
        unit_price=Decimal("40.00"),
        line_total=Decimal("160.00"),
        is_available=True,
    )
    priced_cart = make_priced_cart(customer.id, uuid.uuid4(), [priced_item])

    app.dependency_overrides[require_customer] = lambda: customer
    app.dependency_overrides[get_db] = lambda: mock_session
    try:
        with monkeypatch.context() as mp:
            mock_service = MagicMock()
            mock_service.update_item_quantity = AsyncMock(return_value=MagicMock())
            mock_service.get_priced_cart = AsyncMock(return_value=priced_cart)
            mp.setattr("app.cart.router.CartService", lambda s: mock_service)

            response = client.patch(
                f"/api/v1/cart/items/{item_id}",
                json={"quantity": 4},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["item_count"] == 4
            assert Decimal(data["subtotal"]) == Decimal("160.00")
            mock_service.update_item_quantity.assert_called_once_with(
                user=customer, menu_item_id=item_id, quantity=4
            )
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_remove_item_and_clear_cart(monkeypatch):
    """DELETE endpoints safely remove lines and clear the cart."""
    customer = make_user()
    item_id = uuid.uuid4()
    mock_session = AsyncMock()
    empty_cart = make_priced_cart(customer.id)

    app.dependency_overrides[require_customer] = lambda: customer
    app.dependency_overrides[get_db] = lambda: mock_session
    try:
        with monkeypatch.context() as mp:
            mock_service = MagicMock()
            mock_service.remove_item = AsyncMock(return_value=MagicMock())
            mock_service.clear_cart = AsyncMock(return_value=MagicMock())
            mock_service.get_priced_cart = AsyncMock(return_value=empty_cart)
            mp.setattr("app.cart.router.CartService", lambda s: mock_service)

            # 1. Remove individual item
            res1 = client.delete(f"/api/v1/cart/items/{item_id}")
            assert res1.status_code == 200
            assert res1.json()["item_count"] == 0
            mock_service.remove_item.assert_called_once_with(
                user=customer, menu_item_id=item_id
            )

            # 2. Clear entire cart
            res2 = client.delete("/api/v1/cart")
            assert res2.status_code == 200
            assert res2.json()["item_count"] == 0
            mock_service.clear_cart.assert_called_once_with(customer)
    finally:
        app.dependency_overrides.clear()


# ==============================================================================
# 2. CHECKOUT API TESTS
# ==============================================================================


@pytest.mark.asyncio
async def test_checkout_successful_creates_order_pending_payment(monkeypatch):
    """POST /api/v1/checkout creates order in PENDING_PAYMENT status and clears cart."""
    customer = make_user()
    rest = make_restaurant()
    item = make_menu_item(rest.id, "Biryani", Decimal("300.00"))
    mock_session = AsyncMock()

    order_id = uuid.uuid4()
    order = Order(
        id=order_id,
        customer_id=customer.id,
        restaurant_id=rest.id,
        status=OrderStatus.PENDING_PAYMENT,
        subtotal=Decimal("600.00"),
        delivery_fee=Decimal("0.00"),
        tax=Decimal("0.00"),
        discount=Decimal("0.00"),
        total=Decimal("600.00"),
        currency="INR",
        delivery_address_line1="Flat 4B, Lotus Apartments",
        delivery_city="Mumbai",
        delivery_state="Maharashtra",
        delivery_postal_code="400050",
    )
    order_item = OrderItem(
        order_id=order.id,
        restaurant_id=rest.id,
        menu_item_id=item.id,
        quantity=2,
        unit_price=Decimal("300.00"),
        line_total=Decimal("600.00"),
        item_name=item.name,
    )
    order.items.append(order_item)

    app.dependency_overrides[require_customer] = lambda: customer
    app.dependency_overrides[get_db] = lambda: mock_session
    try:
        with monkeypatch.context() as mp:
            mock_service = MagicMock()
            mock_service.checkout = AsyncMock(return_value=order)
            mp.setattr("app.checkout.router.CheckoutService", lambda s: mock_service)

            payload = {
                "delivery_address_line1": "Flat 4B, Lotus Apartments",
                "delivery_city": "Mumbai",
                "delivery_state": "Maharashtra",
                "delivery_postal_code": "400050",
                "notes": "Ring doorbell",
            }
            response = client.post("/api/v1/checkout", json=payload)
            assert response.status_code == 201
            data = response.json()
            assert data["id"] == str(order_id)
            assert data["customer_id"] == str(customer.id)
            assert data["restaurant_id"] == str(rest.id)
            # Crucial payment boundary: must be PENDING_PAYMENT
            assert data["status"] == "PENDING_PAYMENT"
            assert Decimal(data["total"]) == Decimal("600.00")
            assert len(data["items"]) == 1
            assert data["items"][0]["item_name"] == "Biryani"
            assert data["delivery_address"]["delivery_city"] == "Mumbai"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_checkout_empty_cart_returns_400(monkeypatch):
    """Attempting checkout with an empty cart returns 400 Bad Request."""
    customer = make_user()
    mock_session = AsyncMock()

    app.dependency_overrides[require_customer] = lambda: customer
    app.dependency_overrides[get_db] = lambda: mock_session
    try:
        with monkeypatch.context() as mp:
            mock_service = MagicMock()
            mock_service.checkout = AsyncMock(
                side_effect=EmptyCartCheckoutError(
                    "Cannot checkout with an empty cart."
                )
            )
            mp.setattr("app.checkout.router.CheckoutService", lambda s: mock_service)

            payload = {
                "delivery_address_line1": "Flat 4B",
                "delivery_city": "Mumbai",
                "delivery_state": "Maharashtra",
                "delivery_postal_code": "400050",
            }
            response = client.post("/api/v1/checkout", json=payload)
            assert response.status_code == 400
            assert "empty cart" in response.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_checkout_invalid_address_returns_422():
    """Missing mandatory delivery address fields return 422 Unprocessable Entity."""
    customer = make_user()
    app.dependency_overrides[require_customer] = lambda: customer
    try:
        # Missing delivery_postal_code
        payload = {
            "delivery_address_line1": "Flat 4B",
            "delivery_city": "Mumbai",
            "delivery_state": "Maharashtra",
        }
        response = client.post("/api/v1/checkout", json=payload)
        assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()


# ==============================================================================
# 3. CUSTOMER ORDERS API TESTS
# ==============================================================================


@pytest.mark.asyncio
async def test_list_customer_orders_success(monkeypatch):
    """GET /api/v1/orders lists orders belonging only to the authenticated customer."""
    customer = make_user()
    rest = make_restaurant()
    order1 = Order(
        customer_id=customer.id,
        restaurant_id=rest.id,
        status=OrderStatus.PENDING_PAYMENT,
        subtotal=Decimal("200.00"),
        delivery_fee=Decimal("0.00"),
        tax=Decimal("0.00"),
        discount=Decimal("0.00"),
        total=Decimal("200.00"),
        currency="INR",
        delivery_address_line1="Line 1",
        delivery_city="City",
        delivery_state="State",
        delivery_postal_code="123456",
    )
    mock_session = AsyncMock()

    app.dependency_overrides[require_customer] = lambda: customer
    app.dependency_overrides[get_db] = lambda: mock_session
    try:
        with monkeypatch.context() as mp:
            mock_service = MagicMock()
            mock_service.list_customer_orders = AsyncMock(return_value=([order1], 1))
            mp.setattr("app.orders.router.OrderService", lambda s: mock_service)

            response = client.get("/api/v1/orders?skip=0&limit=10")
            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 1
            assert data["skip"] == 0
            assert data["limit"] == 10
            assert len(data["items"]) == 1
            assert data["items"][0]["customer_id"] == str(customer.id)
            assert data["items"][0]["status"] == "PENDING_PAYMENT"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_customer_order_by_id_success(monkeypatch):
    """GET /api/v1/orders/{id} retrieves an order owned by the caller."""
    customer = make_user()
    rest = make_restaurant()
    order = Order(
        id=uuid.uuid4(),
        customer_id=customer.id,
        restaurant_id=rest.id,
        status=OrderStatus.PENDING_PAYMENT,
        subtotal=Decimal("450.00"),
        delivery_fee=Decimal("0.00"),
        tax=Decimal("0.00"),
        discount=Decimal("0.00"),
        total=Decimal("450.00"),
        currency="INR",
        delivery_address_line1="123 Road",
        delivery_city="Pune",
        delivery_state="Maharashtra",
        delivery_postal_code="411001",
    )
    mock_session = AsyncMock()

    app.dependency_overrides[require_customer] = lambda: customer
    app.dependency_overrides[get_db] = lambda: mock_session
    try:
        with monkeypatch.context() as mp:
            mock_service = MagicMock()
            mock_service.get_customer_order = AsyncMock(return_value=order)
            mp.setattr("app.orders.router.OrderService", lambda s: mock_service)

            response = client.get(f"/api/v1/orders/{order.id}")
            assert response.status_code == 200
            data = response.json()
            assert data["id"] == str(order.id)
            assert data["customer_id"] == str(customer.id)
            assert Decimal(data["total"]) == Decimal("450.00")
            assert data["delivery_address"]["delivery_city"] == "Pune"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_another_customers_order_returns_404(monkeypatch):
    """Attempting to access an order belonging to another customer returns 404 (no leak)."""
    from app.orders.exceptions import OrderNotFoundError

    customer = make_user()
    other_order_id = uuid.uuid4()
    mock_session = AsyncMock()

    app.dependency_overrides[require_customer] = lambda: customer
    app.dependency_overrides[get_db] = lambda: mock_session
    try:
        with monkeypatch.context() as mp:
            mock_service = MagicMock()
            mock_service.get_customer_order = AsyncMock(
                side_effect=OrderNotFoundError(f"Order '{other_order_id}' not found.")
            )
            mp.setattr("app.orders.router.OrderService", lambda s: mock_service)

            response = client.get(f"/api/v1/orders/{other_order_id}")
            assert response.status_code == 404
            assert "not found" in response.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()
