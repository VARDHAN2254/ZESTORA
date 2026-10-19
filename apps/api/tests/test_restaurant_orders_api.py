"""Comprehensive tests for Restaurant Order Management API:
- Role & Ownership Authentication/Authorization
- Cross-Restaurant Isolation & Tenant Boundary Protection
- Order Listing with Pagination & Status Filtering
- Single Order Retrieval with Historical Snapshots & Coordinate Privacy
- Order Lifecycle Transitions:
  - Accept: CONFIRMED -> ACCEPTED (Strict rejection of unpaid PENDING_PAYMENT orders)
  - Prepare: ACCEPTED -> PREPARING
  - Ready: PREPARING -> READY_FOR_PICKUP
  - Cancel: Allowed from CONFIRMED, ACCEPTED, PREPARING; Rejected for terminal/delivery states
- Invalid state transitions & conflict handling
- Service layer direct unit tests
"""

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import app.cart.models
import app.catalog.models
import app.delivery.models
import app.identity.models
import app.orders.models
import app.payments.models
import app.restaurants.models
from app.core.database import get_db
from app.identity.dependencies import require_restaurant
from app.identity.enums import UserRole, UserStatus
from app.identity.models import User
from app.main import app
from app.orders.enums import OrderStatus
from app.orders.exceptions import (
    InvalidOrderTransitionError,
    OrderNotEligibleError,
    OrderNotFoundError,
)
from app.orders.models import Order, OrderItem
from app.orders.repository import OrderRepository
from app.restaurant_orders.service import RestaurantOrderService
from app.restaurants.enums import RestaurantStatus
from app.restaurants.exceptions import (
    RestaurantNotFoundError,
    UnauthorizedRestaurantAccessError,
)
from app.restaurants.models import Restaurant

client = TestClient(app)


# ==============================================================================
# TEST FIXTURES & HELPERS
# ==============================================================================


def make_user(
    role: UserRole = UserRole.RESTAURANT,
    status: UserStatus = UserStatus.ACTIVE,
    user_id: uuid.UUID | None = None,
) -> User:
    """Helper to create User instances for test auth."""
    uid = user_id or uuid.uuid4()
    return User(
        id=uid,
        email=f"owner-{uid.hex[:8]}@example.com",
        password_hash="argon2id$mockhash",
        first_name="Ramesh",
        last_name="Chef",
        role=role,
        status=status,
    )


def make_restaurant(
    owner_id: uuid.UUID,
    restaurant_id: uuid.UUID | None = None,
    name: str = "Spice Kingdom",
    status: RestaurantStatus = RestaurantStatus.ACTIVE,
) -> Restaurant:
    """Helper to create Restaurant instances."""
    rid = restaurant_id or uuid.uuid4()
    return Restaurant(
        id=rid,
        owner_id=owner_id,
        name=name,
        slug=f"spice-{rid.hex[:8]}",
        phone="+919876543210",
        address_line1="42 Curry Lane",
        city="Bengaluru",
        state="Karnataka",
        postal_code="560001",
        status=status,
    )


def make_order(
    restaurant_id: uuid.UUID,
    customer_id: uuid.UUID | None = None,
    order_id: uuid.UUID | None = None,
    status: OrderStatus = OrderStatus.CONFIRMED,
    subtotal: Decimal = Decimal("450.00"),
    delivery_fee: Decimal = Decimal("40.00"),
    tax: Decimal = Decimal("22.50"),
    discount: Decimal = Decimal("0.00"),
    total: Decimal = Decimal("512.50"),
    with_items: bool = True,
) -> Order:
    """Helper to create Order instances with historical snapshots."""
    oid = order_id or uuid.uuid4()
    cid = customer_id or uuid.uuid4()
    order = Order(
        id=oid,
        customer_id=cid,
        restaurant_id=restaurant_id,
        status=status,
        subtotal=subtotal,
        delivery_fee=delivery_fee,
        tax=tax,
        discount=discount,
        total=total,
        currency="INR",
        delivery_address_line1="Flat 201, Green Heights",
        delivery_address_line2="MG Road",
        delivery_city="Bengaluru",
        delivery_state="Karnataka",
        delivery_postal_code="560001",
        delivery_latitude=Decimal("12.971598"),
        delivery_longitude=Decimal("77.594562"),
        notes="Please make it spicy and ring bell twice",
    )
    if with_items:
        item1 = OrderItem(
            id=uuid.uuid4(),
            order_id=oid,
            restaurant_id=restaurant_id,
            menu_item_id=uuid.uuid4(),
            item_name="Biryani Special",
            item_description="Dum biryani with raita",
            quantity=2,
            unit_price=Decimal("200.00"),
            line_total=Decimal("400.00"),
        )
        item2 = OrderItem(
            id=uuid.uuid4(),
            order_id=oid,
            restaurant_id=restaurant_id,
            menu_item_id=uuid.uuid4(),
            item_name="Garlic Naan",
            item_description="Crispy butter naan",
            quantity=1,
            unit_price=Decimal("50.00"),
            line_total=Decimal("50.00"),
        )
        order.items = [item1, item2]
    else:
        order.items = []
    return order


# ==============================================================================
# 1. AUTHENTICATION & ROLE AUTHORIZATION TESTS
# ==============================================================================


def test_unauthenticated_requests_return_401():
    """Unauthenticated requests to any restaurant orders endpoint must return 401."""
    rid = uuid.uuid4()
    oid = uuid.uuid4()
    base = f"/api/v1/restaurants/{rid}/orders"

    assert client.get(base).status_code == 401
    assert client.get(f"{base}/{oid}").status_code == 401
    assert client.post(f"{base}/{oid}/accept").status_code == 401
    assert client.post(f"{base}/{oid}/prepare").status_code == 401
    assert client.post(f"{base}/{oid}/ready").status_code == 401
    assert client.post(f"{base}/{oid}/cancel").status_code == 401


def test_non_restaurant_role_returns_403():
    """Customers or delivery partners cannot access restaurant order management."""
    rid = uuid.uuid4()
    oid = uuid.uuid4()
    base = f"/api/v1/restaurants/{rid}/orders"

    app.dependency_overrides[require_restaurant] = lambda: (_ for _ in ()).throw(
        HTTPException(
            status_code=403, detail="Insufficient permissions for this resource."
        )
    )
    try:
        assert client.get(base).status_code == 403
        assert client.get(f"{base}/{oid}").status_code == 403
        assert client.post(f"{base}/{oid}/accept").status_code == 403
        assert client.post(f"{base}/{oid}/prepare").status_code == 403
        assert client.post(f"{base}/{oid}/ready").status_code == 403
        assert client.post(f"{base}/{oid}/cancel").status_code == 403
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_restaurant_ownership_verification_forbidden_if_not_owner(monkeypatch):
    """A user with RESTAURANT role cannot manage orders for a restaurant they do not own."""
    legit_owner = make_user()
    other_owner = make_user()
    rest = make_restaurant(owner_id=legit_owner.id)

    mock_session = AsyncMock()
    app.dependency_overrides[require_restaurant] = lambda: other_owner
    app.dependency_overrides[get_db] = lambda: mock_session

    try:
        with monkeypatch.context() as mp:
            mock_rest_repo = MagicMock()
            mock_rest_repo.get_by_id = AsyncMock(return_value=rest)
            mp.setattr(
                "app.restaurant_orders.service.RestaurantRepository",
                lambda s: mock_rest_repo,
            )

            # Attempt to list orders
            res = client.get(f"/api/v1/restaurants/{rest.id}/orders")
            assert res.status_code == 403
            assert "permission" in res.json()["detail"].lower()

            # Attempt to accept order
            res_accept = client.post(
                f"/api/v1/restaurants/{rest.id}/orders/{uuid.uuid4()}/accept"
            )
            assert res_accept.status_code == 403
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_non_existent_restaurant_returns_404(monkeypatch):
    """Accessing orders for a restaurant ID that does not exist returns 404."""
    owner = make_user()
    missing_rid = uuid.uuid4()
    mock_session = AsyncMock()

    app.dependency_overrides[require_restaurant] = lambda: owner
    app.dependency_overrides[get_db] = lambda: mock_session

    try:
        with monkeypatch.context() as mp:
            mock_rest_repo = MagicMock()
            mock_rest_repo.get_by_id = AsyncMock(return_value=None)
            mp.setattr(
                "app.restaurant_orders.service.RestaurantRepository",
                lambda s: mock_rest_repo,
            )

            res = client.get(f"/api/v1/restaurants/{missing_rid}/orders")
            assert res.status_code == 404
            assert "not found" in res.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


# ==============================================================================
# 2. LIST RESTAURANT ORDERS (PAGINATION & FILTERING)
# ==============================================================================


@pytest.mark.asyncio
async def test_list_restaurant_orders_success(monkeypatch):
    """Owner successfully lists orders for their restaurant with pagination and totals."""
    owner = make_user()
    rest = make_restaurant(owner_id=owner.id)
    order1 = make_order(restaurant_id=rest.id, status=OrderStatus.CONFIRMED)
    order2 = make_order(restaurant_id=rest.id, status=OrderStatus.ACCEPTED)

    mock_session = AsyncMock()
    app.dependency_overrides[require_restaurant] = lambda: owner
    app.dependency_overrides[get_db] = lambda: mock_session

    try:
        with monkeypatch.context() as mp:
            mock_service = MagicMock()
            mock_service.list_restaurant_orders = AsyncMock(
                return_value=([order1, order2], 2)
            )
            mp.setattr(
                "app.restaurant_orders.router.RestaurantOrderService",
                lambda s: mock_service,
            )

            res = client.get(f"/api/v1/restaurants/{rest.id}/orders?skip=0&limit=10")
            assert res.status_code == 200
            data = res.json()
            assert data["total"] == 2
            assert data["skip"] == 0
            assert data["limit"] == 10
            assert len(data["items"]) == 2
            assert data["items"][0]["id"] == str(order1.id)
            assert data["items"][0]["status"] == "CONFIRMED"
            assert len(data["items"][0]["items"]) == 2
            assert data["items"][0]["delivery_address"]["delivery_city"] == "Bengaluru"
            assert "delivery_latitude" not in data["items"][0]["delivery_address"]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_list_restaurant_orders_with_status_filter(monkeypatch):
    """Owner filters orders by status (e.g. status=CONFIRMED)."""
    owner = make_user()
    rest = make_restaurant(owner_id=owner.id)
    order1 = make_order(restaurant_id=rest.id, status=OrderStatus.CONFIRMED)

    mock_session = AsyncMock()
    app.dependency_overrides[require_restaurant] = lambda: owner
    app.dependency_overrides[get_db] = lambda: mock_session

    try:
        with monkeypatch.context() as mp:
            mock_service = MagicMock()
            mock_service.list_restaurant_orders = AsyncMock(return_value=([order1], 1))
            mp.setattr(
                "app.restaurant_orders.router.RestaurantOrderService",
                lambda s: mock_service,
            )

            res = client.get(f"/api/v1/restaurants/{rest.id}/orders?status=CONFIRMED")
            assert res.status_code == 200
            data = res.json()
            assert data["total"] == 1
            assert data["items"][0]["status"] == "CONFIRMED"
            mock_service.list_restaurant_orders.assert_called_once_with(
                user=owner,
                restaurant_id=rest.id,
                skip=0,
                limit=20,
                status=OrderStatus.CONFIRMED,
            )
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_list_restaurant_orders_invalid_status_filter():
    """Invalid status enum value returns 422 Unprocessable Entity."""
    owner = make_user()
    rest = make_restaurant(owner_id=owner.id)
    app.dependency_overrides[require_restaurant] = lambda: owner

    try:
        res = client.get(f"/api/v1/restaurants/{rest.id}/orders?status=INVALID_STATUS")
        assert res.status_code == 422
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_list_restaurant_orders_invalid_pagination():
    """Negative skip or limit > 100 returns 422."""
    owner = make_user()
    rest = make_restaurant(owner_id=owner.id)
    app.dependency_overrides[require_restaurant] = lambda: owner

    try:
        res1 = client.get(f"/api/v1/restaurants/{rest.id}/orders?skip=-1")
        assert res1.status_code == 422

        res2 = client.get(f"/api/v1/restaurants/{rest.id}/orders?limit=101")
        assert res2.status_code == 422
    finally:
        app.dependency_overrides.clear()


# ==============================================================================
# 3. GET ORDER BY ID & TENANT ISOLATION
# ==============================================================================


@pytest.mark.asyncio
async def test_get_restaurant_order_by_id_success(monkeypatch):
    """Retrieve full order details with address snapshot, line items, and notes."""
    owner = make_user()
    rest = make_restaurant(owner_id=owner.id)
    order = make_order(restaurant_id=rest.id, status=OrderStatus.CONFIRMED)

    mock_session = AsyncMock()
    app.dependency_overrides[require_restaurant] = lambda: owner
    app.dependency_overrides[get_db] = lambda: mock_session

    try:
        with monkeypatch.context() as mp:
            mock_service = MagicMock()
            mock_service.get_restaurant_order = AsyncMock(return_value=order)
            mp.setattr(
                "app.restaurant_orders.router.RestaurantOrderService",
                lambda s: mock_service,
            )

            res = client.get(f"/api/v1/restaurants/{rest.id}/orders/{order.id}")
            assert res.status_code == 200
            data = res.json()
            assert data["id"] == str(order.id)
            assert data["restaurant_id"] == str(rest.id)
            assert data["status"] == "CONFIRMED"
            assert Decimal(data["subtotal"]) == Decimal("450.00")
            assert Decimal(data["total"]) == Decimal("512.50")
            assert data["currency"] == "INR"
            assert data["notes"] == "Please make it spicy and ring bell twice"
            assert len(data["items"]) == 2
            assert (
                data["delivery_address"]["delivery_address_line1"]
                == "Flat 201, Green Heights"
            )
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_restaurant_order_cross_restaurant_isolation(monkeypatch):
    """Order belonging to another restaurant returns 404 even if caller is an owner."""
    owner = make_user()
    rest1 = make_restaurant(owner_id=owner.id)
    other_order_id = uuid.uuid4()

    mock_session = AsyncMock()
    app.dependency_overrides[require_restaurant] = lambda: owner
    app.dependency_overrides[get_db] = lambda: mock_session

    try:
        with monkeypatch.context() as mp:
            mock_service = MagicMock()
            mock_service.get_restaurant_order = AsyncMock(
                side_effect=OrderNotFoundError(f"Order '{other_order_id}' not found.")
            )
            mp.setattr(
                "app.restaurant_orders.router.RestaurantOrderService",
                lambda s: mock_service,
            )

            res = client.get(f"/api/v1/restaurants/{rest1.id}/orders/{other_order_id}")
            assert res.status_code == 404
            assert "not found" in res.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


# ==============================================================================
# 4. ORDER ACCEPTANCE & PAYMENT BOUNDARY ENFORCEMENT
# ==============================================================================


@pytest.mark.asyncio
async def test_accept_confirmed_order_success(monkeypatch):
    """Accepting a CONFIRMED order successfully transitions to ACCEPTED."""
    owner = make_user()
    rest = make_restaurant(owner_id=owner.id)
    order = make_order(restaurant_id=rest.id, status=OrderStatus.CONFIRMED)
    accepted_order = make_order(
        restaurant_id=rest.id, order_id=order.id, status=OrderStatus.ACCEPTED
    )

    mock_session = AsyncMock()
    app.dependency_overrides[require_restaurant] = lambda: owner
    app.dependency_overrides[get_db] = lambda: mock_session

    try:
        with monkeypatch.context() as mp:
            mock_service = MagicMock()
            mock_service.accept_order = AsyncMock(return_value=accepted_order)
            mp.setattr(
                "app.restaurant_orders.router.RestaurantOrderService",
                lambda s: mock_service,
            )

            res = client.post(f"/api/v1/restaurants/{rest.id}/orders/{order.id}/accept")
            assert res.status_code == 200
            data = res.json()
            assert data["id"] == str(order.id)
            assert data["status"] == "ACCEPTED"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_accept_unpaid_order_fails_409_conflict(monkeypatch):
    """RESTAURANT CANNOT ACCEPT UNPAID (PENDING_PAYMENT) ORDERS. Must return 409 Conflict."""
    owner = make_user()
    rest = make_restaurant(owner_id=owner.id)
    order = make_order(restaurant_id=rest.id, status=OrderStatus.PENDING_PAYMENT)

    mock_session = AsyncMock()
    app.dependency_overrides[require_restaurant] = lambda: owner
    app.dependency_overrides[get_db] = lambda: mock_session

    try:
        with monkeypatch.context() as mp:
            mock_service = MagicMock()
            mock_service.accept_order = AsyncMock(
                side_effect=OrderNotEligibleError(
                    "Cannot accept order: payment has not been completed."
                )
            )
            mp.setattr(
                "app.restaurant_orders.router.RestaurantOrderService",
                lambda s: mock_service,
            )

            res = client.post(f"/api/v1/restaurants/{rest.id}/orders/{order.id}/accept")
            assert res.status_code == 409
            assert "payment has not been completed" in res.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_accept_already_accepted_order_fails_409(monkeypatch):
    """Accepting an order that is already ACCEPTED or beyond returns 409 Conflict."""
    owner = make_user()
    rest = make_restaurant(owner_id=owner.id)
    order = make_order(restaurant_id=rest.id, status=OrderStatus.ACCEPTED)

    mock_session = AsyncMock()
    app.dependency_overrides[require_restaurant] = lambda: owner
    app.dependency_overrides[get_db] = lambda: mock_session

    try:
        with monkeypatch.context() as mp:
            mock_service = MagicMock()
            mock_service.accept_order = AsyncMock(
                side_effect=InvalidOrderTransitionError(
                    "Cannot accept order in 'ACCEPTED' status. Only CONFIRMED orders can be accepted."
                )
            )
            mp.setattr(
                "app.restaurant_orders.router.RestaurantOrderService",
                lambda s: mock_service,
            )

            res = client.post(f"/api/v1/restaurants/{rest.id}/orders/{order.id}/accept")
            assert res.status_code == 409
            assert (
                "only confirmed orders can be accepted" in res.json()["detail"].lower()
            )
    finally:
        app.dependency_overrides.clear()


# ==============================================================================
# 5. ORDER PREPARATION (POST /{order_id}/prepare)
# ==============================================================================


@pytest.mark.asyncio
async def test_start_preparing_order_success(monkeypatch):
    """Transition ACCEPTED -> PREPARING returns updated order with status=PREPARING."""
    owner = make_user()
    rest = make_restaurant(owner_id=owner.id)
    order = make_order(restaurant_id=rest.id, status=OrderStatus.ACCEPTED)
    prep_order = make_order(
        restaurant_id=rest.id, order_id=order.id, status=OrderStatus.PREPARING
    )

    mock_session = AsyncMock()
    app.dependency_overrides[require_restaurant] = lambda: owner
    app.dependency_overrides[get_db] = lambda: mock_session

    try:
        with monkeypatch.context() as mp:
            mock_service = MagicMock()
            mock_service.start_preparing = AsyncMock(return_value=prep_order)
            mp.setattr(
                "app.restaurant_orders.router.RestaurantOrderService",
                lambda s: mock_service,
            )

            res = client.post(
                f"/api/v1/restaurants/{rest.id}/orders/{order.id}/prepare"
            )
            assert res.status_code == 200
            data = res.json()
            assert data["status"] == "PREPARING"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_start_preparing_unaccepted_order_fails_409(monkeypatch):
    """Cannot start preparing an order that has not been accepted yet (e.g. CONFIRMED)."""
    owner = make_user()
    rest = make_restaurant(owner_id=owner.id)
    order = make_order(restaurant_id=rest.id, status=OrderStatus.CONFIRMED)

    mock_session = AsyncMock()
    app.dependency_overrides[require_restaurant] = lambda: owner
    app.dependency_overrides[get_db] = lambda: mock_session

    try:
        with monkeypatch.context() as mp:
            mock_service = MagicMock()
            mock_service.start_preparing = AsyncMock(
                side_effect=InvalidOrderTransitionError(
                    "Cannot perform 'start_preparing' on order in 'CONFIRMED' status. Expected status: 'ACCEPTED'."
                )
            )
            mp.setattr(
                "app.restaurant_orders.router.RestaurantOrderService",
                lambda s: mock_service,
            )

            res = client.post(
                f"/api/v1/restaurants/{rest.id}/orders/{order.id}/prepare"
            )
            assert res.status_code == 409
            assert "expected status: 'accepted'" in res.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


# ==============================================================================
# 6. MARK READY FOR PICKUP (POST /{order_id}/ready)
# ==============================================================================


@pytest.mark.asyncio
async def test_mark_ready_for_pickup_success(monkeypatch):
    """Transition PREPARING -> READY_FOR_PICKUP returns status=READY_FOR_PICKUP."""
    owner = make_user()
    rest = make_restaurant(owner_id=owner.id)
    order = make_order(restaurant_id=rest.id, status=OrderStatus.PREPARING)
    ready_order = make_order(
        restaurant_id=rest.id, order_id=order.id, status=OrderStatus.READY_FOR_PICKUP
    )

    mock_session = AsyncMock()
    app.dependency_overrides[require_restaurant] = lambda: owner
    app.dependency_overrides[get_db] = lambda: mock_session

    try:
        with monkeypatch.context() as mp:
            mock_service = MagicMock()
            mock_service.mark_ready_for_pickup = AsyncMock(return_value=ready_order)
            mp.setattr(
                "app.restaurant_orders.router.RestaurantOrderService",
                lambda s: mock_service,
            )

            res = client.post(f"/api/v1/restaurants/{rest.id}/orders/{order.id}/ready")
            assert res.status_code == 200
            data = res.json()
            assert data["status"] == "READY_FOR_PICKUP"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_mark_ready_from_invalid_status_fails_409(monkeypatch):
    """Cannot mark order ready directly from CONFIRMED or ACCEPTED."""
    owner = make_user()
    rest = make_restaurant(owner_id=owner.id)
    order = make_order(restaurant_id=rest.id, status=OrderStatus.ACCEPTED)

    mock_session = AsyncMock()
    app.dependency_overrides[require_restaurant] = lambda: owner
    app.dependency_overrides[get_db] = lambda: mock_session

    try:
        with monkeypatch.context() as mp:
            mock_service = MagicMock()
            mock_service.mark_ready_for_pickup = AsyncMock(
                side_effect=InvalidOrderTransitionError(
                    "Cannot perform 'mark_ready' on order in 'ACCEPTED' status. Expected status: 'PREPARING'."
                )
            )
            mp.setattr(
                "app.restaurant_orders.router.RestaurantOrderService",
                lambda s: mock_service,
            )

            res = client.post(f"/api/v1/restaurants/{rest.id}/orders/{order.id}/ready")
            assert res.status_code == 409
            assert "expected status: 'preparing'" in res.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


# ==============================================================================
# 7. ORDER CANCELLATION (POST /{order_id}/cancel)
# ==============================================================================


@pytest.mark.asyncio
async def test_cancel_order_from_confirmed_success(monkeypatch):
    """Restaurant can cancel a CONFIRMED order before preparing."""
    owner = make_user()
    rest = make_restaurant(owner_id=owner.id)
    order = make_order(restaurant_id=rest.id, status=OrderStatus.CONFIRMED)
    cancelled_order = make_order(
        restaurant_id=rest.id, order_id=order.id, status=OrderStatus.CANCELLED
    )

    mock_session = AsyncMock()
    app.dependency_overrides[require_restaurant] = lambda: owner
    app.dependency_overrides[get_db] = lambda: mock_session

    try:
        with monkeypatch.context() as mp:
            mock_service = MagicMock()
            mock_service.cancel_order = AsyncMock(return_value=cancelled_order)
            mp.setattr(
                "app.restaurant_orders.router.RestaurantOrderService",
                lambda s: mock_service,
            )

            res = client.post(f"/api/v1/restaurants/{rest.id}/orders/{order.id}/cancel")
            assert res.status_code == 200
            data = res.json()
            assert data["status"] == "CANCELLED"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_cancel_order_from_preparing_success(monkeypatch):
    """Restaurant can cancel an order in PREPARING status (e.g. kitchen issue)."""
    owner = make_user()
    rest = make_restaurant(owner_id=owner.id)
    order = make_order(restaurant_id=rest.id, status=OrderStatus.PREPARING)
    cancelled_order = make_order(
        restaurant_id=rest.id, order_id=order.id, status=OrderStatus.CANCELLED
    )

    mock_session = AsyncMock()
    app.dependency_overrides[require_restaurant] = lambda: owner
    app.dependency_overrides[get_db] = lambda: mock_session

    try:
        with monkeypatch.context() as mp:
            mock_service = MagicMock()
            mock_service.cancel_order = AsyncMock(return_value=cancelled_order)
            mp.setattr(
                "app.restaurant_orders.router.RestaurantOrderService",
                lambda s: mock_service,
            )

            res = client.post(f"/api/v1/restaurants/{rest.id}/orders/{order.id}/cancel")
            assert res.status_code == 200
            assert res.json()["status"] == "CANCELLED"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_cancel_order_rejected_for_disallowed_statuses(monkeypatch):
    """Restaurant cannot cancel order once READY_FOR_PICKUP, DELIVERED, or already CANCELLED."""
    owner = make_user()
    rest = make_restaurant(owner_id=owner.id)
    oid = uuid.uuid4()

    mock_session = AsyncMock()
    app.dependency_overrides[require_restaurant] = lambda: owner
    app.dependency_overrides[get_db] = lambda: mock_session

    try:
        with monkeypatch.context() as mp:
            mock_service = MagicMock()
            mock_service.cancel_order = AsyncMock(
                side_effect=InvalidOrderTransitionError(
                    "Cannot cancel order in 'READY_FOR_PICKUP' status."
                )
            )
            mp.setattr(
                "app.restaurant_orders.router.RestaurantOrderService",
                lambda s: mock_service,
            )

            res = client.post(f"/api/v1/restaurants/{rest.id}/orders/{oid}/cancel")
            assert res.status_code == 409
            assert (
                "cannot cancel order in 'ready_for_pickup' status"
                in res.json()["detail"].lower()
            )
    finally:
        app.dependency_overrides.clear()


# ==============================================================================
# 8. DIRECT SERVICE LAYER UNIT TESTS
# ==============================================================================


@pytest.mark.asyncio
async def test_service_verify_ownership_role_mismatch():
    """Service raises UnauthorizedRestaurantAccessError when user role is not RESTAURANT."""
    customer = make_user(role=UserRole.CUSTOMER)
    mock_session = AsyncMock()
    service = RestaurantOrderService(mock_session)

    with pytest.raises(UnauthorizedRestaurantAccessError, match="RESTAURANT role"):
        await service.list_restaurant_orders(customer, uuid.uuid4())


@pytest.mark.asyncio
async def test_service_verify_ownership_restaurant_not_found():
    """Service raises RestaurantNotFoundError when restaurant does not exist."""
    owner = make_user(role=UserRole.RESTAURANT)
    mock_session = AsyncMock()
    mock_rest_repo = MagicMock()
    mock_rest_repo.get_by_id = AsyncMock(return_value=None)
    service = RestaurantOrderService(mock_session, restaurant_repo=mock_rest_repo)

    with pytest.raises(RestaurantNotFoundError):
        await service.list_restaurant_orders(owner, uuid.uuid4())


@pytest.mark.asyncio
async def test_service_verify_ownership_not_owner():
    """Service raises UnauthorizedRestaurantAccessError when restaurant belongs to someone else."""
    owner = make_user(role=UserRole.RESTAURANT)
    diff_owner_id = uuid.uuid4()
    rest = make_restaurant(owner_id=diff_owner_id)

    mock_session = AsyncMock()
    mock_rest_repo = MagicMock()
    mock_rest_repo.get_by_id = AsyncMock(return_value=rest)
    service = RestaurantOrderService(mock_session, restaurant_repo=mock_rest_repo)

    with pytest.raises(UnauthorizedRestaurantAccessError, match="permission"):
        await service.list_restaurant_orders(owner, rest.id)


@pytest.mark.asyncio
async def test_service_accept_order_unpaid_raises_order_not_eligible():
    """Service strictly prevents accepting PENDING_PAYMENT orders."""
    owner = make_user()
    rest = make_restaurant(owner_id=owner.id)
    order = make_order(restaurant_id=rest.id, status=OrderStatus.PENDING_PAYMENT)

    mock_session = AsyncMock()
    mock_rest_repo = MagicMock()
    mock_rest_repo.get_by_id = AsyncMock(return_value=rest)

    mock_order_repo = MagicMock()
    mock_order_repo.get_by_id_and_restaurant = AsyncMock(return_value=order)

    service = RestaurantOrderService(
        mock_session, order_repo=mock_order_repo, restaurant_repo=mock_rest_repo
    )

    with pytest.raises(OrderNotEligibleError, match="payment has not been completed"):
        await service.accept_order(owner, rest.id, order.id)


@pytest.mark.asyncio
async def test_service_accept_order_confirmed_success():
    """Service successfully accepts a CONFIRMED order."""
    owner = make_user()
    rest = make_restaurant(owner_id=owner.id)
    order = make_order(restaurant_id=rest.id, status=OrderStatus.CONFIRMED)

    mock_session = AsyncMock()
    mock_rest_repo = MagicMock()
    mock_rest_repo.get_by_id = AsyncMock(return_value=rest)

    mock_order_repo = MagicMock()
    mock_order_repo.get_by_id_and_restaurant = AsyncMock(return_value=order)
    mock_order_repo.update_status = AsyncMock(
        return_value=make_order(
            restaurant_id=rest.id, order_id=order.id, status=OrderStatus.ACCEPTED
        )
    )

    service = RestaurantOrderService(
        mock_session, order_repo=mock_order_repo, restaurant_repo=mock_rest_repo
    )

    result = await service.accept_order(owner, rest.id, order.id)
    assert result.status == OrderStatus.ACCEPTED
    mock_order_repo.update_status.assert_called_once_with(
        order, OrderStatus.ACCEPTED, expected_status=OrderStatus.CONFIRMED
    )


@pytest.mark.asyncio
async def test_service_start_preparing_order_success():
    """Service transitions ACCEPTED -> PREPARING."""
    owner = make_user()
    rest = make_restaurant(owner_id=owner.id)
    order = make_order(restaurant_id=rest.id, status=OrderStatus.ACCEPTED)

    mock_session = AsyncMock()
    mock_rest_repo = MagicMock()
    mock_rest_repo.get_by_id = AsyncMock(return_value=rest)

    mock_order_repo = MagicMock()
    mock_order_repo.get_by_id_and_restaurant = AsyncMock(return_value=order)
    mock_order_repo.update_status = AsyncMock(
        return_value=make_order(
            restaurant_id=rest.id, order_id=order.id, status=OrderStatus.PREPARING
        )
    )

    service = RestaurantOrderService(
        mock_session, order_repo=mock_order_repo, restaurant_repo=mock_rest_repo
    )

    result = await service.start_preparing(owner, rest.id, order.id)
    assert result.status == OrderStatus.PREPARING
    mock_order_repo.update_status.assert_called_once_with(
        order, OrderStatus.PREPARING, expected_status=OrderStatus.ACCEPTED
    )


@pytest.mark.asyncio
async def test_service_mark_ready_for_pickup_success():
    """Service transitions PREPARING -> READY_FOR_PICKUP."""
    owner = make_user()
    rest = make_restaurant(owner_id=owner.id)
    order = make_order(restaurant_id=rest.id, status=OrderStatus.PREPARING)

    mock_session = AsyncMock()
    mock_rest_repo = MagicMock()
    mock_rest_repo.get_by_id = AsyncMock(return_value=rest)

    mock_order_repo = MagicMock()
    mock_order_repo.get_by_id_and_restaurant = AsyncMock(return_value=order)
    mock_order_repo.update_status = AsyncMock(
        return_value=make_order(
            restaurant_id=rest.id,
            order_id=order.id,
            status=OrderStatus.READY_FOR_PICKUP,
        )
    )

    service = RestaurantOrderService(
        mock_session, order_repo=mock_order_repo, restaurant_repo=mock_rest_repo
    )

    result = await service.mark_ready_for_pickup(owner, rest.id, order.id)
    assert result.status == OrderStatus.READY_FOR_PICKUP
    mock_order_repo.update_status.assert_called_once_with(
        order, OrderStatus.READY_FOR_PICKUP, expected_status=OrderStatus.PREPARING
    )


@pytest.mark.asyncio
async def test_service_cancel_order_success():
    """Service cancels order from PREPARING status."""
    owner = make_user()
    rest = make_restaurant(owner_id=owner.id)
    order = make_order(restaurant_id=rest.id, status=OrderStatus.PREPARING)

    mock_session = AsyncMock()
    mock_rest_repo = MagicMock()
    mock_rest_repo.get_by_id = AsyncMock(return_value=rest)

    mock_order_repo = MagicMock()
    mock_order_repo.get_by_id_and_restaurant = AsyncMock(return_value=order)
    mock_order_repo.update_status = AsyncMock(
        return_value=make_order(
            restaurant_id=rest.id, order_id=order.id, status=OrderStatus.CANCELLED
        )
    )

    service = RestaurantOrderService(
        mock_session, order_repo=mock_order_repo, restaurant_repo=mock_rest_repo
    )

    result = await service.cancel_order(owner, rest.id, order.id)
    assert result.status == OrderStatus.CANCELLED
    mock_order_repo.update_status.assert_called_once_with(
        order, OrderStatus.CANCELLED, expected_status=OrderStatus.PREPARING
    )


@pytest.mark.asyncio
async def test_service_cancel_order_disallowed_status():
    """Service raises InvalidOrderTransitionError when order cannot be cancelled by restaurant."""
    owner = make_user()
    rest = make_restaurant(owner_id=owner.id)
    order = make_order(restaurant_id=rest.id, status=OrderStatus.DELIVERED)

    mock_session = AsyncMock()
    mock_rest_repo = MagicMock()
    mock_rest_repo.get_by_id = AsyncMock(return_value=rest)

    mock_order_repo = MagicMock()
    mock_order_repo.get_by_id_and_restaurant = AsyncMock(return_value=order)

    service = RestaurantOrderService(
        mock_session, order_repo=mock_order_repo, restaurant_repo=mock_rest_repo
    )

    with pytest.raises(
        InvalidOrderTransitionError, match="Cannot cancel order in 'DELIVERED' status"
    ):
        await service.cancel_order(owner, rest.id, order.id)


# ==============================================================================
# 9. REPOSITORY SCOPED METHODS
# ==============================================================================


@pytest.mark.asyncio
async def test_repository_scoped_query_methods():
    """Verify OrderRepository scoped queries pass correct filters to SQL execution."""
    mock_session = AsyncMock()
    repo = OrderRepository(mock_session)
    rest_id = uuid.uuid4()
    order_id = uuid.uuid4()

    mock_order = make_order(restaurant_id=rest_id, order_id=order_id)

    # get_by_id_and_restaurant
    mock_res_single = MagicMock()
    mock_res_single.scalar_one_or_none.return_value = mock_order
    mock_session.execute.return_value = mock_res_single

    res = await repo.get_by_id_and_restaurant(order_id, rest_id)
    assert res is mock_order

    # list_by_restaurant_paginated
    mock_res_list = MagicMock()
    mock_res_list.scalars.return_value.all.return_value = [mock_order]
    mock_session.execute.return_value = mock_res_list

    orders = await repo.list_by_restaurant_paginated(
        restaurant_id=rest_id, skip=10, limit=20, status=OrderStatus.CONFIRMED
    )
    assert orders == [mock_order]

    # count_by_restaurant
    mock_res_count = MagicMock()
    mock_res_count.scalar_one.return_value = 5
    mock_session.execute.return_value = mock_res_count

    count = await repo.count_by_restaurant(rest_id, status=OrderStatus.CONFIRMED)
    assert count == 5


# ==============================================================================
# 10. CONCURRENCY SAFETY & CONFLICTING TRANSITIONS
# ==============================================================================


@pytest.mark.asyncio
async def test_service_for_update_locking_on_mutating_actions():
    """Verify that all mutating operations acquire a row-level lock (for_update=True),
    while read-only operations do not acquire a lock (for_update=False).
    """
    owner = make_user()
    rest = make_restaurant(owner_id=owner.id)
    order_id = uuid.uuid4()

    mock_session = AsyncMock()
    mock_rest_repo = MagicMock()
    mock_rest_repo.get_by_id = AsyncMock(return_value=rest)

    # 1. Read-only operation: get_restaurant_order should use for_update=False
    mock_order_repo = MagicMock()
    read_order = make_order(restaurant_id=rest.id, order_id=order_id)
    mock_order_repo.get_by_id_and_restaurant = AsyncMock(return_value=read_order)

    service = RestaurantOrderService(
        mock_session, order_repo=mock_order_repo, restaurant_repo=mock_rest_repo
    )
    await service.get_restaurant_order(owner, rest.id, order_id)
    mock_order_repo.get_by_id_and_restaurant.assert_called_once_with(
        order_id=order_id,
        restaurant_id=rest.id,
        include_items=True,
    )

    # 2. Mutating operation: accept_order should use for_update=True
    mock_order_repo.reset_mock()
    conf_order = make_order(
        restaurant_id=rest.id, order_id=order_id, status=OrderStatus.CONFIRMED
    )
    mock_order_repo.get_by_id_and_restaurant = AsyncMock(return_value=conf_order)
    mock_order_repo.update_status = AsyncMock(return_value=conf_order)

    await service.accept_order(owner, rest.id, order_id)
    mock_order_repo.get_by_id_and_restaurant.assert_called_once_with(
        order_id=order_id,
        restaurant_id=rest.id,
        include_items=True,
        for_update=True,
    )

    # 3. Mutating operation: start_preparing should use for_update=True
    mock_order_repo.reset_mock()
    accepted_order = make_order(
        restaurant_id=rest.id, order_id=order_id, status=OrderStatus.ACCEPTED
    )
    mock_order_repo.get_by_id_and_restaurant = AsyncMock(return_value=accepted_order)
    mock_order_repo.update_status = AsyncMock(return_value=accepted_order)

    await service.start_preparing(owner, rest.id, order_id)
    mock_order_repo.get_by_id_and_restaurant.assert_called_once_with(
        order_id=order_id,
        restaurant_id=rest.id,
        include_items=True,
        for_update=True,
    )

    # 4. Mutating operation: mark_ready_for_pickup should use for_update=True
    mock_order_repo.reset_mock()
    prep_order = make_order(
        restaurant_id=rest.id, order_id=order_id, status=OrderStatus.PREPARING
    )
    mock_order_repo.get_by_id_and_restaurant = AsyncMock(return_value=prep_order)
    mock_order_repo.update_status = AsyncMock(return_value=prep_order)

    await service.mark_ready_for_pickup(owner, rest.id, order_id)
    mock_order_repo.get_by_id_and_restaurant.assert_called_once_with(
        order_id=order_id,
        restaurant_id=rest.id,
        include_items=True,
        for_update=True,
    )

    # 5. Mutating operation: cancel_order should use for_update=True
    mock_order_repo.reset_mock()
    mock_order_repo.get_by_id_and_restaurant = AsyncMock(return_value=prep_order)
    mock_order_repo.update_status = AsyncMock(return_value=prep_order)

    await service.cancel_order(owner, rest.id, order_id)
    mock_order_repo.get_by_id_and_restaurant.assert_called_once_with(
        order_id=order_id,
        restaurant_id=rest.id,
        include_items=True,
        for_update=True,
    )


@pytest.mark.asyncio
async def test_repository_get_by_id_and_restaurant_with_for_update_sql():
    """Verify that get_by_id_and_restaurant executes a query with FOR UPDATE
    when for_update=True, and without FOR UPDATE when for_update=False.
    """
    from sqlalchemy.dialects import postgresql

    mock_session = AsyncMock()
    repo = OrderRepository(mock_session)
    rest_id = uuid.uuid4()
    order_id = uuid.uuid4()

    mock_session.execute.return_value = MagicMock(
        scalar_one_or_none=MagicMock(return_value=None)
    )

    # Test with for_update=True
    await repo.get_by_id_and_restaurant(order_id, rest_id, for_update=True)
    called_query = mock_session.execute.call_args[0][0]
    compiled_sql = str(called_query.compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE" in compiled_sql

    # Test with for_update=False
    mock_session.reset_mock()
    await repo.get_by_id_and_restaurant(order_id, rest_id, for_update=False)
    called_query_no_lock = mock_session.execute.call_args[0][0]
    compiled_sql_no_lock = str(
        called_query_no_lock.compile(dialect=postgresql.dialect())
    )
    assert "FOR UPDATE" not in compiled_sql_no_lock


@pytest.mark.asyncio
async def test_repository_update_status_expected_status_atomic_check():
    """Verify that update_status checks expected_status atomically and raises
    InvalidOrderStateTransitionError if the current status does not match.
    """
    from app.orders.state_machine import InvalidOrderStateTransitionError

    mock_session = AsyncMock()
    repo = OrderRepository(mock_session)
    order = make_order(restaurant_id=uuid.uuid4(), status=OrderStatus.CONFIRMED)

    # 1. Matching expected_status succeeds
    updated = await repo.update_status(
        order, OrderStatus.ACCEPTED, expected_status=OrderStatus.CONFIRMED
    )
    assert updated.status == OrderStatus.ACCEPTED
    mock_session.flush.assert_awaited_once()

    # 2. Mismatched expected_status (stale read) raises InvalidOrderStateTransitionError
    with pytest.raises(InvalidOrderStateTransitionError):
        await repo.update_status(
            order, OrderStatus.PREPARING, expected_status=OrderStatus.CONFIRMED
        )


@pytest.mark.asyncio
async def test_concurrent_accept_races_rejected(monkeypatch):
    """Simulate two concurrent requests attempting to accept the same CONFIRMED order.
    The second request observes the order in ACCEPTED status (after lock release)
    and fails predictably with a 409 Conflict.
    """
    owner = make_user()
    rest = make_restaurant(owner_id=owner.id)
    order_id = uuid.uuid4()

    # State evolution: starts as CONFIRMED, updated to ACCEPTED by Request 1
    order_state = make_order(
        restaurant_id=rest.id, order_id=order_id, status=OrderStatus.CONFIRMED
    )

    mock_session = AsyncMock()
    app.dependency_overrides[require_restaurant] = lambda: owner
    app.dependency_overrides[get_db] = lambda: mock_session

    try:
        mock_rest_repo = MagicMock()
        mock_rest_repo.get_by_id = AsyncMock(return_value=rest)

        # Real service with a mock repository that updates state
        mock_order_repo = MagicMock()

        async def fake_get_by_id(*args, **kwargs):
            return order_state

        async def fake_update_status(order, new_status, expected_status=None):
            if expected_status is not None and order.status != expected_status:
                from app.orders.state_machine import InvalidOrderStateTransitionError

                raise InvalidOrderStateTransitionError(order.status, new_status)
            order.status = new_status
            return order

        mock_order_repo.get_by_id_and_restaurant = AsyncMock(side_effect=fake_get_by_id)
        mock_order_repo.update_status = AsyncMock(side_effect=fake_update_status)

        with monkeypatch.context() as mp:
            mp.setattr(
                "app.restaurant_orders.router.RestaurantOrderService",
                lambda s: RestaurantOrderService(
                    s, order_repo=mock_order_repo, restaurant_repo=mock_rest_repo
                ),
            )

            # Request 1: succeeds (CONFIRMED -> ACCEPTED)
            res1 = client.post(
                f"/api/v1/restaurants/{rest.id}/orders/{order_id}/accept"
            )
            assert res1.status_code == 200
            assert res1.json()["status"] == "ACCEPTED"
            assert order_state.status == OrderStatus.ACCEPTED

            # Request 2 (concurrent race on stale assumption):
            # Sees order already in ACCEPTED status, fails with 409 Conflict
            res2 = client.post(
                f"/api/v1/restaurants/{rest.id}/orders/{order_id}/accept"
            )
            assert res2.status_code == 409
            assert (
                "only confirmed orders can be accepted" in res2.json()["detail"].lower()
            )
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_concurrent_accept_and_cancel_race_rejected(monkeypatch):
    """Simulate an accept request racing with a cancellation request.
    When cancellation finishes first, the accept request observes CANCELLED status
    and is rejected with 409 Conflict.
    """
    owner = make_user()
    rest = make_restaurant(owner_id=owner.id)
    order_id = uuid.uuid4()

    # Starts as CONFIRMED, cancelled by Request 1
    order_state = make_order(
        restaurant_id=rest.id, order_id=order_id, status=OrderStatus.CONFIRMED
    )

    mock_session = AsyncMock()
    app.dependency_overrides[require_restaurant] = lambda: owner
    app.dependency_overrides[get_db] = lambda: mock_session

    try:
        mock_rest_repo = MagicMock()
        mock_rest_repo.get_by_id = AsyncMock(return_value=rest)

        mock_order_repo = MagicMock()

        async def fake_get_by_id(*args, **kwargs):
            return order_state

        async def fake_update_status(order, new_status, expected_status=None):
            if expected_status is not None and order.status != expected_status:
                from app.orders.state_machine import InvalidOrderStateTransitionError

                raise InvalidOrderStateTransitionError(order.status, new_status)
            order.status = new_status
            return order

        mock_order_repo.get_by_id_and_restaurant = AsyncMock(side_effect=fake_get_by_id)
        mock_order_repo.update_status = AsyncMock(side_effect=fake_update_status)

        with monkeypatch.context() as mp:
            mp.setattr(
                "app.restaurant_orders.router.RestaurantOrderService",
                lambda s: RestaurantOrderService(
                    s, order_repo=mock_order_repo, restaurant_repo=mock_rest_repo
                ),
            )

            # Request 1: cancels the order (CONFIRMED -> CANCELLED)
            res1 = client.post(
                f"/api/v1/restaurants/{rest.id}/orders/{order_id}/cancel"
            )
            assert res1.status_code == 200
            assert res1.json()["status"] == "CANCELLED"
            assert order_state.status == OrderStatus.CANCELLED

            # Request 2: racing accept request receives CANCELLED status under lock and fails
            res2 = client.post(
                f"/api/v1/restaurants/{rest.id}/orders/{order_id}/accept"
            )
            assert res2.status_code == 409
            assert (
                "only confirmed orders can be accepted" in res2.json()["detail"].lower()
            )
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_concurrent_ready_and_cancel_race_rejected(monkeypatch):
    """Simulate mark_ready racing with cancel:
    When mark_ready transitions PREPARING -> READY_FOR_PICKUP,
    the racing cancel request fails with 409 Conflict because READY_FOR_PICKUP
    cannot be cancelled by the restaurant.
    """
    owner = make_user()
    rest = make_restaurant(owner_id=owner.id)
    order_id = uuid.uuid4()

    # Starts as PREPARING
    order_state = make_order(
        restaurant_id=rest.id, order_id=order_id, status=OrderStatus.PREPARING
    )

    mock_session = AsyncMock()
    app.dependency_overrides[require_restaurant] = lambda: owner
    app.dependency_overrides[get_db] = lambda: mock_session

    try:
        mock_rest_repo = MagicMock()
        mock_rest_repo.get_by_id = AsyncMock(return_value=rest)

        mock_order_repo = MagicMock()

        async def fake_get_by_id(*args, **kwargs):
            return order_state

        async def fake_update_status(order, new_status, expected_status=None):
            if expected_status is not None and order.status != expected_status:
                from app.orders.state_machine import InvalidOrderStateTransitionError

                raise InvalidOrderStateTransitionError(order.status, new_status)
            order.status = new_status
            return order

        mock_order_repo.get_by_id_and_restaurant = AsyncMock(side_effect=fake_get_by_id)
        mock_order_repo.update_status = AsyncMock(side_effect=fake_update_status)

        with monkeypatch.context() as mp:
            mp.setattr(
                "app.restaurant_orders.router.RestaurantOrderService",
                lambda s: RestaurantOrderService(
                    s, order_repo=mock_order_repo, restaurant_repo=mock_rest_repo
                ),
            )

            # Request 1: marks order ready (PREPARING -> READY_FOR_PICKUP)
            res1 = client.post(f"/api/v1/restaurants/{rest.id}/orders/{order_id}/ready")
            assert res1.status_code == 200
            assert res1.json()["status"] == "READY_FOR_PICKUP"
            assert order_state.status == OrderStatus.READY_FOR_PICKUP

            # Request 2: racing cancel request unblocks and attempts to cancel READY_FOR_PICKUP
            res2 = client.post(
                f"/api/v1/restaurants/{rest.id}/orders/{order_id}/cancel"
            )
            assert res2.status_code == 409
            assert (
                "cannot cancel order in 'ready_for_pickup' status"
                in res2.json()["detail"].lower()
            )
    finally:
        app.dependency_overrides.clear()
