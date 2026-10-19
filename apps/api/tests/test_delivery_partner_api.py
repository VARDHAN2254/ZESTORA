"""Comprehensive tests for Delivery Partner API:
- Role & Profile Authentication/Authorization
- Cross-Partner Isolation & Tenant Boundary Protection
- Discovery of Available Delivery Jobs with Eligibility Filtering & Privacy
- Atomic Job Acceptance under Row-Level Lock & Concurrency Safeguards
- Synchronized Delivery & Order Lifecycle Progressions:
  - Pickup: Delivery ASSIGNED -> PICKED_UP, Order READY_FOR_PICKUP -> PICKED_UP
  - Out for Delivery: Delivery PICKED_UP -> OUT_FOR_DELIVERY, Order PICKED_UP -> OUT_FOR_DELIVERY
  - Delivered: Delivery OUT_FOR_DELIVERY -> DELIVERED, Order OUT_FOR_DELIVERY -> DELIVERED
- Terminal State and Transition Immutability
- Active Delivery & History Retrieval
- Automatic Delivery Job Creation on Restaurant mark_ready
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
from app.delivery.enums import (
    DeliveryPartnerAvailability,
    DeliveryPartnerStatus,
    DeliveryStatus,
    VehicleType,
)
from app.delivery.models import Delivery, DeliveryPartner
from app.delivery.repository import DeliveryRepository
from app.identity.dependencies import require_delivery_partner
from app.identity.enums import UserRole, UserStatus
from app.identity.models import User
from app.main import app
from app.orders.enums import OrderStatus
from app.orders.models import Order, OrderItem
from app.restaurant_orders.service import RestaurantOrderService
from app.restaurants.enums import RestaurantStatus
from app.restaurants.models import Restaurant

client = TestClient(app)


# ==============================================================================
# TEST FIXTURES & BUILDERS
# ==============================================================================


def make_user(
    role: UserRole = UserRole.DELIVERY_PARTNER,
    status: UserStatus = UserStatus.ACTIVE,
    user_id: uuid.UUID | None = None,
) -> User:
    """Helper to create User instances for test auth."""
    uid = user_id or uuid.uuid4()
    return User(
        id=uid,
        email=f"partner-{uid.hex[:8]}@example.com",
        password_hash="argon2id$mockhash",
        first_name="Vikram",
        last_name="Rider",
        role=role,
        status=status,
    )


def make_delivery_partner(
    user_id: uuid.UUID,
    partner_id: uuid.UUID | None = None,
    status: DeliveryPartnerStatus = DeliveryPartnerStatus.ACTIVE,
    availability: DeliveryPartnerAvailability = DeliveryPartnerAvailability.AVAILABLE,
    vehicle_type: VehicleType = VehicleType.MOTORCYCLE,
    vehicle_identifier: str = "KA-01-AB-1234",
) -> DeliveryPartner:
    """Helper to create DeliveryPartner profile instances."""
    pid = partner_id or uuid.uuid4()
    return DeliveryPartner(
        id=pid,
        user_id=user_id,
        status=status,
        availability=availability,
        vehicle_type=vehicle_type,
        vehicle_identifier=vehicle_identifier,
    )


def make_restaurant(
    owner_id: uuid.UUID | None = None,
    restaurant_id: uuid.UUID | None = None,
    name: str = "Biryani Central",
) -> Restaurant:
    """Helper to create Restaurant instances."""
    rid = restaurant_id or uuid.uuid4()
    oid = owner_id or uuid.uuid4()
    return Restaurant(
        id=rid,
        owner_id=oid,
        name=name,
        slug=f"biryani-{rid.hex[:8]}",
        phone="+919876543210",
        address_line1="100 Feet Road, Indiranagar",
        city="Bengaluru",
        state="Karnataka",
        postal_code="560038",
        status=RestaurantStatus.ACTIVE,
    )


def make_order(
    restaurant_id: uuid.UUID,
    customer_id: uuid.UUID | None = None,
    order_id: uuid.UUID | None = None,
    status: OrderStatus = OrderStatus.READY_FOR_PICKUP,
    restaurant: Restaurant | None = None,
) -> Order:
    """Helper to create Order instances."""
    oid = order_id or uuid.uuid4()
    cid = customer_id or uuid.uuid4()
    order = Order(
        id=oid,
        customer_id=cid,
        restaurant_id=restaurant_id,
        status=status,
        subtotal=Decimal("350.00"),
        delivery_fee=Decimal("40.00"),
        tax=Decimal("17.50"),
        discount=Decimal("0.00"),
        total=Decimal("407.50"),
        currency="INR",
        delivery_address_line1="Apartment 4B, Palm Grove",
        delivery_address_line2="Koramangala 4th Block",
        delivery_city="Bengaluru",
        delivery_state="Karnataka",
        delivery_postal_code="560034",
        delivery_latitude=Decimal("12.9352"),
        delivery_longitude=Decimal("77.6245"),
        notes="Ring doorbell",
    )
    item = OrderItem(
        id=uuid.uuid4(),
        order_id=oid,
        restaurant_id=restaurant_id,
        menu_item_id=uuid.uuid4(),
        item_name="Chicken Dum Biryani",
        item_description="Traditional spiced dum biryani",
        quantity=1,
        unit_price=Decimal("350.00"),
        line_total=Decimal("350.00"),
    )
    order.items = [item]
    if restaurant is not None:
        order.restaurant = restaurant
    return order


def make_delivery(
    order: Order,
    partner_id: uuid.UUID | None = None,
    delivery_id: uuid.UUID | None = None,
    status: DeliveryStatus = DeliveryStatus.UNASSIGNED,
) -> Delivery:
    """Helper to create Delivery instances."""
    did = delivery_id or uuid.uuid4()
    delivery = Delivery(
        id=did,
        order_id=order.id,
        delivery_partner_id=partner_id,
        status=status,
    )
    delivery.order = order
    return delivery


# ==============================================================================
# 1. AUTHENTICATION & ROLE AUTHORIZATION TESTS
# ==============================================================================


def test_unauthenticated_requests_return_401():
    """Unauthenticated requests to any delivery partner endpoint must return 401."""
    did = uuid.uuid4()
    base = "/api/v1/delivery-partner"

    assert client.get(f"{base}/profile").status_code == 401
    assert client.post(f"{base}/profile", json={}).status_code == 401
    assert (
        client.patch(
            f"{base}/availability", json={"availability": "AVAILABLE"}
        ).status_code
        == 401
    )
    assert client.get(f"{base}/available-deliveries").status_code == 401
    assert client.get(f"{base}/current-delivery").status_code == 401
    assert client.get(f"{base}/deliveries").status_code == 401
    assert client.get(f"{base}/deliveries/{did}").status_code == 401
    assert client.post(f"{base}/deliveries/{did}/accept").status_code == 401
    assert client.post(f"{base}/deliveries/{did}/pickup").status_code == 401
    assert client.post(f"{base}/deliveries/{did}/out-for-delivery").status_code == 401
    assert client.post(f"{base}/deliveries/{did}/deliver").status_code == 401


def test_non_delivery_partner_role_returns_403():
    """Customers or restaurant owners cannot access delivery partner endpoints."""
    did = uuid.uuid4()
    base = "/api/v1/delivery-partner"

    app.dependency_overrides[require_delivery_partner] = lambda: (_ for _ in ()).throw(
        HTTPException(
            status_code=403, detail="Insufficient permissions for this resource."
        )
    )
    try:
        assert client.get(f"{base}/profile").status_code == 403
        assert (
            client.post(
                f"{base}/profile",
                json={
                    "vehicle_type": "MOTORCYCLE",
                    "vehicle_identifier": "KA-01-AB-1234",
                },
            ).status_code
            == 403
        )
        assert client.get(f"{base}/available-deliveries").status_code == 403
        assert client.post(f"{base}/deliveries/{did}/accept").status_code == 403
        assert client.post(f"{base}/deliveries/{did}/pickup").status_code == 403
        assert (
            client.post(f"{base}/deliveries/{did}/out-for-delivery").status_code == 403
        )
        assert client.post(f"{base}/deliveries/{did}/deliver").status_code == 403
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_cannot_access_other_partner_private_delivery(monkeypatch):
    """A delivery partner cannot view details of a delivery assigned to someone else."""
    user_partner_a = make_user()
    user_partner_b = make_user()

    partner_a = make_delivery_partner(user_id=user_partner_a.id)
    partner_b = make_delivery_partner(user_id=user_partner_b.id)

    rest = make_restaurant()
    order = make_order(restaurant_id=rest.id, restaurant=rest)
    delivery = make_delivery(
        order=order, partner_id=partner_a.id, status=DeliveryStatus.ASSIGNED
    )

    mock_session = AsyncMock()
    app.dependency_overrides[require_delivery_partner] = lambda: user_partner_b
    app.dependency_overrides[get_db] = lambda: mock_session

    try:
        with monkeypatch.context() as mp:
            mock_deliv_repo = MagicMock()
            mock_deliv_repo.get_partner_by_user_id = AsyncMock(return_value=partner_b)
            mock_deliv_repo.get_by_id_with_details = AsyncMock(return_value=delivery)
            mp.setattr(
                "app.delivery.service.DeliveryRepository", lambda s: mock_deliv_repo
            )

            resp = client.get(f"/api/v1/delivery-partner/deliveries/{delivery.id}")
            assert resp.status_code == 403
            assert "permission" in resp.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


# ==============================================================================
# 2. PROFILE & AVAILABILITY MANAGEMENT
# ==============================================================================


@pytest.mark.asyncio
async def test_get_profile_success(monkeypatch):
    """Authenticated delivery partner can retrieve their own profile."""
    user = make_user()
    partner = make_delivery_partner(user_id=user.id)

    mock_session = AsyncMock()
    app.dependency_overrides[require_delivery_partner] = lambda: user
    app.dependency_overrides[get_db] = lambda: mock_session

    try:
        with monkeypatch.context() as mp:
            mock_deliv_repo = MagicMock()
            mock_deliv_repo.get_partner_by_user_id = AsyncMock(return_value=partner)
            mp.setattr(
                "app.delivery.service.DeliveryRepository", lambda s: mock_deliv_repo
            )

            resp = client.get("/api/v1/delivery-partner/profile")
            assert resp.status_code == 200
            data = resp.json()
            assert data["id"] == str(partner.id)
            assert data["user_id"] == str(user.id)
            assert data["status"] == "ACTIVE"
            assert data["availability"] == "AVAILABLE"
            assert data["vehicle_type"] == "MOTORCYCLE"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_profile_not_found(monkeypatch):
    """404 returned if user does not have a delivery partner profile."""
    user = make_user()

    mock_session = AsyncMock()
    app.dependency_overrides[require_delivery_partner] = lambda: user
    app.dependency_overrides[get_db] = lambda: mock_session

    try:
        with monkeypatch.context() as mp:
            mock_deliv_repo = MagicMock()
            mock_deliv_repo.get_partner_by_user_id = AsyncMock(return_value=None)
            mp.setattr(
                "app.delivery.service.DeliveryRepository", lambda s: mock_deliv_repo
            )

            resp = client.get("/api/v1/delivery-partner/profile")
            assert resp.status_code == 404
            assert "profile not found" in resp.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_profile_success(monkeypatch):
    """Delivery partner can onboard their profile."""
    user = make_user()
    partner = make_delivery_partner(user_id=user.id)

    mock_session = AsyncMock()
    app.dependency_overrides[require_delivery_partner] = lambda: user
    app.dependency_overrides[get_db] = lambda: mock_session

    try:
        with monkeypatch.context() as mp:
            mock_deliv_repo = MagicMock()
            mock_deliv_repo.get_partner_by_user_id = AsyncMock(return_value=None)
            mock_deliv_repo.create_partner = AsyncMock(return_value=partner)
            mp.setattr(
                "app.delivery.service.DeliveryRepository", lambda s: mock_deliv_repo
            )

            payload = {
                "vehicle_type": "MOTORCYCLE",
                "vehicle_identifier": "KA-01-AB-1234",
                "availability": "AVAILABLE",
            }
            resp = client.post("/api/v1/delivery-partner/profile", json=payload)
            assert resp.status_code == 201
            data = resp.json()
            assert data["id"] == str(partner.id)
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_profile_duplicate_conflict(monkeypatch):
    """Attempting to create a profile when one already exists returns 409 Conflict."""
    user = make_user()
    partner = make_delivery_partner(user_id=user.id)

    mock_session = AsyncMock()
    app.dependency_overrides[require_delivery_partner] = lambda: user
    app.dependency_overrides[get_db] = lambda: mock_session

    try:
        with monkeypatch.context() as mp:
            mock_deliv_repo = MagicMock()
            mock_deliv_repo.get_partner_by_user_id = AsyncMock(return_value=partner)
            mp.setattr(
                "app.delivery.service.DeliveryRepository", lambda s: mock_deliv_repo
            )

            payload = {"vehicle_type": "MOTORCYCLE"}
            resp = client.post("/api/v1/delivery-partner/profile", json=payload)
            assert resp.status_code == 409
            assert "already exists" in resp.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_update_availability_success(monkeypatch):
    """Delivery partner can update their availability."""
    user = make_user()
    partner = make_delivery_partner(
        user_id=user.id, availability=DeliveryPartnerAvailability.AVAILABLE
    )

    mock_session = AsyncMock()
    app.dependency_overrides[require_delivery_partner] = lambda: user
    app.dependency_overrides[get_db] = lambda: mock_session

    try:
        with monkeypatch.context() as mp:
            mock_deliv_repo = MagicMock()
            mock_deliv_repo.get_partner_by_user_id = AsyncMock(return_value=partner)

            async def mock_update(p, avail):
                p.availability = avail
                return p

            mock_deliv_repo.update_partner_availability = AsyncMock(
                side_effect=mock_update
            )
            mp.setattr(
                "app.delivery.service.DeliveryRepository", lambda s: mock_deliv_repo
            )

            resp = client.patch(
                "/api/v1/delivery-partner/availability",
                json={"availability": "UNAVAILABLE"},
            )
            assert resp.status_code == 200
            assert resp.json()["availability"] == "UNAVAILABLE"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_update_availability_suspended_partner_forbidden(monkeypatch):
    """Suspended or inactive partner cannot update availability."""
    user = make_user()
    partner = make_delivery_partner(
        user_id=user.id, status=DeliveryPartnerStatus.SUSPENDED
    )

    mock_session = AsyncMock()
    app.dependency_overrides[require_delivery_partner] = lambda: user
    app.dependency_overrides[get_db] = lambda: mock_session

    try:
        with monkeypatch.context() as mp:
            mock_deliv_repo = MagicMock()
            mock_deliv_repo.get_partner_by_user_id = AsyncMock(return_value=partner)
            mp.setattr(
                "app.delivery.service.DeliveryRepository", lambda s: mock_deliv_repo
            )

            resp = client.patch(
                "/api/v1/delivery-partner/availability",
                json={"availability": "AVAILABLE"},
            )
            assert resp.status_code == 403
            assert "suspended" in resp.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


# ==============================================================================
# 3. DISCOVERY OF AVAILABLE DELIVERY JOBS
# ==============================================================================


@pytest.mark.asyncio
async def test_list_available_deliveries_success(monkeypatch):
    """List available eligible deliveries where order is READY_FOR_PICKUP and delivery is UNASSIGNED."""
    user = make_user()
    partner = make_delivery_partner(user_id=user.id)
    rest = make_restaurant()
    order = make_order(restaurant_id=rest.id, restaurant=rest)
    delivery = make_delivery(order=order, status=DeliveryStatus.UNASSIGNED)

    mock_session = AsyncMock()
    app.dependency_overrides[require_delivery_partner] = lambda: user
    app.dependency_overrides[get_db] = lambda: mock_session

    try:
        with monkeypatch.context() as mp:
            mock_deliv_repo = MagicMock()
            mock_deliv_repo.get_partner_by_user_id = AsyncMock(return_value=partner)
            mock_deliv_repo.list_available_deliveries = AsyncMock(
                return_value=[delivery]
            )
            mock_deliv_repo.count_available_deliveries = AsyncMock(return_value=1)
            mp.setattr(
                "app.delivery.service.DeliveryRepository", lambda s: mock_deliv_repo
            )

            resp = client.get("/api/v1/delivery-partner/available-deliveries")
            assert resp.status_code == 200
            data = resp.json()
            assert data["total"] == 1
            assert len(data["items"]) == 1
            item = data["items"][0]
            assert item["id"] == str(delivery.id)
            assert item["status"] == "UNASSIGNED"
            assert item["order_id"] == str(order.id)
            assert item["restaurant"]["name"] == "Biryani Central"
            assert len(item["items"]) == 1
            assert item["items"][0]["item_name"] == "Chicken Dum Biryani"
            # Ensure sensitive payment payload is absent
            assert "stripe" not in resp.text.lower()
            assert "password" not in resp.text.lower()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_list_available_deliveries_pagination(monkeypatch):
    """Verify pagination parameters (skip, limit, total)."""
    user = make_user()
    partner = make_delivery_partner(user_id=user.id)

    mock_session = AsyncMock()
    app.dependency_overrides[require_delivery_partner] = lambda: user
    app.dependency_overrides[get_db] = lambda: mock_session

    try:
        with monkeypatch.context() as mp:
            mock_deliv_repo = MagicMock()
            mock_deliv_repo.get_partner_by_user_id = AsyncMock(return_value=partner)
            mock_deliv_repo.list_available_deliveries = AsyncMock(return_value=[])
            mock_deliv_repo.count_available_deliveries = AsyncMock(return_value=42)
            mp.setattr(
                "app.delivery.service.DeliveryRepository", lambda s: mock_deliv_repo
            )

            resp = client.get(
                "/api/v1/delivery-partner/available-deliveries?skip=10&limit=5"
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["total"] == 42
            assert data["skip"] == 10
            assert data["limit"] == 5
            mock_deliv_repo.list_available_deliveries.assert_awaited_once_with(
                skip=10, limit=5
            )
    finally:
        app.dependency_overrides.clear()


# ==============================================================================
# 4. ATOMIC ACCEPTANCE & CONCURRENCY SAFEGUARDS
# ==============================================================================


@pytest.mark.asyncio
async def test_accept_delivery_success(monkeypatch):
    """Eligible partner can accept an available unassigned delivery job."""
    user = make_user()
    partner = make_delivery_partner(user_id=user.id)
    rest = make_restaurant()
    order = make_order(restaurant_id=rest.id, restaurant=rest)
    delivery = make_delivery(order=order, status=DeliveryStatus.UNASSIGNED)

    mock_session = AsyncMock()
    app.dependency_overrides[require_delivery_partner] = lambda: user
    app.dependency_overrides[get_db] = lambda: mock_session

    try:
        with monkeypatch.context() as mp:
            mock_deliv_repo = MagicMock()
            mock_deliv_repo.get_partner_by_user_id = AsyncMock(return_value=partner)
            mock_deliv_repo.get_active_delivery_for_partner = AsyncMock(
                return_value=None
            )
            mock_deliv_repo.get_by_id_with_details = AsyncMock(return_value=delivery)

            async def mock_assign(deliv, pid, **kwargs):
                deliv.status = DeliveryStatus.ASSIGNED
                deliv.delivery_partner_id = pid
                return deliv

            mock_deliv_repo.assign_partner_atomic = AsyncMock(side_effect=mock_assign)
            mp.setattr(
                "app.delivery.service.DeliveryRepository", lambda s: mock_deliv_repo
            )

            resp = client.post(
                f"/api/v1/delivery-partner/deliveries/{delivery.id}/accept"
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ASSIGNED"
            assert data["delivery_partner_id"] == str(partner.id)
            # Verify row-level lock was requested
            mock_deliv_repo.get_by_id_with_details.assert_awaited_once_with(
                delivery.id, for_update=True
            )
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_accept_delivery_already_assigned_returns_409(monkeypatch):
    """Attempting to accept a delivery that has already been claimed returns 409 Conflict."""
    user = make_user()
    partner = make_delivery_partner(user_id=user.id)
    rest = make_restaurant()
    order = make_order(restaurant_id=rest.id, restaurant=rest)
    # Already assigned to another partner
    other_partner_id = uuid.uuid4()
    delivery = make_delivery(
        order=order, partner_id=other_partner_id, status=DeliveryStatus.ASSIGNED
    )

    mock_session = AsyncMock()
    app.dependency_overrides[require_delivery_partner] = lambda: user
    app.dependency_overrides[get_db] = lambda: mock_session

    try:
        with monkeypatch.context() as mp:
            mock_deliv_repo = MagicMock()
            mock_deliv_repo.get_partner_by_user_id = AsyncMock(return_value=partner)
            mock_deliv_repo.get_active_delivery_for_partner = AsyncMock(
                return_value=None
            )
            mock_deliv_repo.get_by_id_with_details = AsyncMock(return_value=delivery)
            mp.setattr(
                "app.delivery.service.DeliveryRepository", lambda s: mock_deliv_repo
            )

            resp = client.post(
                f"/api/v1/delivery-partner/deliveries/{delivery.id}/accept"
            )
            assert resp.status_code == 409
            assert "already been assigned" in resp.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_accept_delivery_unavailable_partner_rejected(monkeypatch):
    """A delivery partner marked UNAVAILABLE cannot accept assignments."""
    user = make_user()
    partner = make_delivery_partner(
        user_id=user.id, availability=DeliveryPartnerAvailability.UNAVAILABLE
    )
    did = uuid.uuid4()

    mock_session = AsyncMock()
    app.dependency_overrides[require_delivery_partner] = lambda: user
    app.dependency_overrides[get_db] = lambda: mock_session

    try:
        with monkeypatch.context() as mp:
            mock_deliv_repo = MagicMock()
            mock_deliv_repo.get_partner_by_user_id = AsyncMock(return_value=partner)
            mp.setattr(
                "app.delivery.service.DeliveryRepository", lambda s: mock_deliv_repo
            )

            resp = client.post(f"/api/v1/delivery-partner/deliveries/{did}/accept")
            assert resp.status_code == 409
            assert "available" in resp.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_accept_delivery_active_delivery_limit_rejected(monkeypatch):
    """A delivery partner who already has an active delivery cannot accept another."""
    user = make_user()
    partner = make_delivery_partner(user_id=user.id)
    rest = make_restaurant()
    order1 = make_order(restaurant_id=rest.id)
    existing_active = make_delivery(
        order=order1, partner_id=partner.id, status=DeliveryStatus.PICKED_UP
    )

    mock_session = AsyncMock()
    app.dependency_overrides[require_delivery_partner] = lambda: user
    app.dependency_overrides[get_db] = lambda: mock_session

    try:
        with monkeypatch.context() as mp:
            mock_deliv_repo = MagicMock()
            mock_deliv_repo.get_partner_by_user_id = AsyncMock(return_value=partner)
            mock_deliv_repo.get_active_delivery_for_partner = AsyncMock(
                return_value=existing_active
            )
            mp.setattr(
                "app.delivery.service.DeliveryRepository", lambda s: mock_deliv_repo
            )

            resp = client.post(
                f"/api/v1/delivery-partner/deliveries/{uuid.uuid4()}/accept"
            )
            assert resp.status_code == 409
            assert "active delivery" in resp.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_accept_delivery_order_not_ready_rejected(monkeypatch):
    """Cannot accept a delivery if corresponding order is not READY_FOR_PICKUP."""
    user = make_user()
    partner = make_delivery_partner(user_id=user.id)
    rest = make_restaurant()
    order = make_order(
        restaurant_id=rest.id, restaurant=rest, status=OrderStatus.PREPARING
    )
    delivery = make_delivery(order=order, status=DeliveryStatus.UNASSIGNED)

    mock_session = AsyncMock()
    app.dependency_overrides[require_delivery_partner] = lambda: user
    app.dependency_overrides[get_db] = lambda: mock_session

    try:
        with monkeypatch.context() as mp:
            mock_deliv_repo = MagicMock()
            mock_deliv_repo.get_partner_by_user_id = AsyncMock(return_value=partner)
            mock_deliv_repo.get_active_delivery_for_partner = AsyncMock(
                return_value=None
            )
            mock_deliv_repo.get_by_id_with_details = AsyncMock(return_value=delivery)
            mp.setattr(
                "app.delivery.service.DeliveryRepository", lambda s: mock_deliv_repo
            )

            resp = client.post(
                f"/api/v1/delivery-partner/deliveries/{delivery.id}/accept"
            )
            assert resp.status_code == 409
            assert "not ready" in resp.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


def test_repository_select_for_update_ast():
    """Verify that DeliveryRepository.get_by_id_with_details with for_update=True
    compiles to SQL containing FOR UPDATE.
    """
    mock_session = AsyncMock()
    repo = DeliveryRepository(mock_session)

    did = uuid.uuid4()

    # Call method and inspect the statement executed
    captured_statements = []

    async def mock_execute(stmt):
        captured_statements.append(stmt)
        res = MagicMock()
        res.scalar_one_or_none.return_value = None
        return res

    mock_session.execute = AsyncMock(side_effect=mock_execute)

    import asyncio

    asyncio.run(repo.get_by_id_with_details(did, for_update=True))

    assert len(captured_statements) == 1
    compiled = str(
        captured_statements[0].compile(compile_kwargs={"literal_binds": True})
    )
    assert "FOR UPDATE" in compiled.upper()


# ==============================================================================
# 5. PICKUP AND DELIVERY PROGRESS (SYNCHRONIZED STATE TRANSITIONS)
# ==============================================================================


@pytest.mark.asyncio
async def test_pickup_delivery_success(monkeypatch):
    """Assigned delivery partner successfully transitions delivery and order to PICKED_UP."""
    user = make_user()
    partner = make_delivery_partner(user_id=user.id)
    rest = make_restaurant()
    order = make_order(
        restaurant_id=rest.id, restaurant=rest, status=OrderStatus.READY_FOR_PICKUP
    )
    delivery = make_delivery(
        order=order, partner_id=partner.id, status=DeliveryStatus.ASSIGNED
    )

    mock_session = AsyncMock()
    app.dependency_overrides[require_delivery_partner] = lambda: user
    app.dependency_overrides[get_db] = lambda: mock_session

    try:
        with monkeypatch.context() as mp:
            mock_deliv_repo = MagicMock()
            mock_deliv_repo.get_partner_by_user_id = AsyncMock(return_value=partner)
            mock_deliv_repo.get_by_id_with_details = AsyncMock(return_value=delivery)

            async def mock_update_deliv(d, new_stat, **kwargs):
                d.status = new_stat
                return d

            mock_deliv_repo.update_status = AsyncMock(side_effect=mock_update_deliv)

            mock_order_repo = MagicMock()

            async def mock_update_order(o, new_stat, **kwargs):
                o.status = new_stat
                return o

            mock_order_repo.update_status = AsyncMock(side_effect=mock_update_order)

            mp.setattr(
                "app.delivery.service.DeliveryRepository", lambda s: mock_deliv_repo
            )
            mp.setattr(
                "app.delivery.service.OrderRepository", lambda s: mock_order_repo
            )

            resp = client.post(
                f"/api/v1/delivery-partner/deliveries/{delivery.id}/pickup"
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "PICKED_UP"
            assert order.status == OrderStatus.PICKED_UP
            mock_deliv_repo.update_status.assert_awaited_once_with(
                delivery,
                DeliveryStatus.PICKED_UP,
                expected_status=DeliveryStatus.ASSIGNED,
            )
            mock_order_repo.update_status.assert_awaited_once_with(
                order,
                OrderStatus.PICKED_UP,
                expected_status=OrderStatus.READY_FOR_PICKUP,
            )
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_pickup_delivery_wrong_partner_forbidden(monkeypatch):
    """A partner cannot perform pickup on another partner's assigned delivery."""
    user_caller = make_user()
    user_owner = make_user()

    partner_caller = make_delivery_partner(user_id=user_caller.id)
    partner_owner = make_delivery_partner(user_id=user_owner.id)

    rest = make_restaurant()
    order = make_order(restaurant_id=rest.id, restaurant=rest)
    delivery = make_delivery(
        order=order, partner_id=partner_owner.id, status=DeliveryStatus.ASSIGNED
    )

    mock_session = AsyncMock()
    app.dependency_overrides[require_delivery_partner] = lambda: user_caller
    app.dependency_overrides[get_db] = lambda: mock_session

    try:
        with monkeypatch.context() as mp:
            mock_deliv_repo = MagicMock()
            mock_deliv_repo.get_partner_by_user_id = AsyncMock(
                return_value=partner_caller
            )
            mock_deliv_repo.get_by_id_with_details = AsyncMock(return_value=delivery)
            mp.setattr(
                "app.delivery.service.DeliveryRepository", lambda s: mock_deliv_repo
            )

            resp = client.post(
                f"/api/v1/delivery-partner/deliveries/{delivery.id}/pickup"
            )
            assert resp.status_code == 403
            assert "not the delivery partner assigned" in resp.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_pickup_delivery_before_ready_rejected(monkeypatch):
    """Reject pickup if order has not yet been marked READY_FOR_PICKUP."""
    user = make_user()
    partner = make_delivery_partner(user_id=user.id)
    rest = make_restaurant()
    order = make_order(
        restaurant_id=rest.id, restaurant=rest, status=OrderStatus.PREPARING
    )
    delivery = make_delivery(
        order=order, partner_id=partner.id, status=DeliveryStatus.ASSIGNED
    )

    mock_session = AsyncMock()
    app.dependency_overrides[require_delivery_partner] = lambda: user
    app.dependency_overrides[get_db] = lambda: mock_session

    try:
        with monkeypatch.context() as mp:
            mock_deliv_repo = MagicMock()
            mock_deliv_repo.get_partner_by_user_id = AsyncMock(return_value=partner)
            mock_deliv_repo.get_by_id_with_details = AsyncMock(return_value=delivery)
            mp.setattr(
                "app.delivery.service.DeliveryRepository", lambda s: mock_deliv_repo
            )

            resp = client.post(
                f"/api/v1/delivery-partner/deliveries/{delivery.id}/pickup"
            )
            assert resp.status_code == 409
            assert "ready_for_pickup" in resp.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_out_for_delivery_success(monkeypatch):
    """Assigned delivery partner transitions delivery and order to OUT_FOR_DELIVERY."""
    user = make_user()
    partner = make_delivery_partner(user_id=user.id)
    rest = make_restaurant()
    order = make_order(
        restaurant_id=rest.id, restaurant=rest, status=OrderStatus.PICKED_UP
    )
    delivery = make_delivery(
        order=order, partner_id=partner.id, status=DeliveryStatus.PICKED_UP
    )

    mock_session = AsyncMock()
    app.dependency_overrides[require_delivery_partner] = lambda: user
    app.dependency_overrides[get_db] = lambda: mock_session

    try:
        with monkeypatch.context() as mp:
            mock_deliv_repo = MagicMock()
            mock_deliv_repo.get_partner_by_user_id = AsyncMock(return_value=partner)
            mock_deliv_repo.get_by_id_with_details = AsyncMock(return_value=delivery)

            async def mock_update_deliv(d, new_stat, **kwargs):
                d.status = new_stat
                return d

            mock_deliv_repo.update_status = AsyncMock(side_effect=mock_update_deliv)

            mock_order_repo = MagicMock()

            async def mock_update_order(o, new_stat, **kwargs):
                o.status = new_stat
                return o

            mock_order_repo.update_status = AsyncMock(side_effect=mock_update_order)

            mp.setattr(
                "app.delivery.service.DeliveryRepository", lambda s: mock_deliv_repo
            )
            mp.setattr(
                "app.delivery.service.OrderRepository", lambda s: mock_order_repo
            )

            resp = client.post(
                f"/api/v1/delivery-partner/deliveries/{delivery.id}/out-for-delivery"
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "OUT_FOR_DELIVERY"
            assert order.status == OrderStatus.OUT_FOR_DELIVERY
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_out_for_delivery_invalid_initial_state_rejected(monkeypatch):
    """Cannot mark OUT_FOR_DELIVERY if status is ASSIGNED (must be PICKED_UP first)."""
    user = make_user()
    partner = make_delivery_partner(user_id=user.id)
    rest = make_restaurant()
    order = make_order(
        restaurant_id=rest.id, restaurant=rest, status=OrderStatus.READY_FOR_PICKUP
    )
    delivery = make_delivery(
        order=order, partner_id=partner.id, status=DeliveryStatus.ASSIGNED
    )

    mock_session = AsyncMock()
    app.dependency_overrides[require_delivery_partner] = lambda: user
    app.dependency_overrides[get_db] = lambda: mock_session

    try:
        with monkeypatch.context() as mp:
            mock_deliv_repo = MagicMock()
            mock_deliv_repo.get_partner_by_user_id = AsyncMock(return_value=partner)
            mock_deliv_repo.get_by_id_with_details = AsyncMock(return_value=delivery)
            mp.setattr(
                "app.delivery.service.DeliveryRepository", lambda s: mock_deliv_repo
            )

            resp = client.post(
                f"/api/v1/delivery-partner/deliveries/{delivery.id}/out-for-delivery"
            )
            assert resp.status_code == 409
            assert "expected status: 'picked_up'" in resp.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_complete_delivery_success(monkeypatch):
    """Assigned delivery partner successfully completes delivery (DELIVERED)."""
    user = make_user()
    partner = make_delivery_partner(user_id=user.id)
    rest = make_restaurant()
    order = make_order(
        restaurant_id=rest.id, restaurant=rest, status=OrderStatus.OUT_FOR_DELIVERY
    )
    delivery = make_delivery(
        order=order, partner_id=partner.id, status=DeliveryStatus.OUT_FOR_DELIVERY
    )

    mock_session = AsyncMock()
    app.dependency_overrides[require_delivery_partner] = lambda: user
    app.dependency_overrides[get_db] = lambda: mock_session

    try:
        with monkeypatch.context() as mp:
            mock_deliv_repo = MagicMock()
            mock_deliv_repo.get_partner_by_user_id = AsyncMock(return_value=partner)
            mock_deliv_repo.get_by_id_with_details = AsyncMock(return_value=delivery)

            async def mock_update_deliv(d, new_stat, **kwargs):
                d.status = new_stat
                return d

            mock_deliv_repo.update_status = AsyncMock(side_effect=mock_update_deliv)

            mock_order_repo = MagicMock()

            async def mock_update_order(o, new_stat, **kwargs):
                o.status = new_stat
                return o

            mock_order_repo.update_status = AsyncMock(side_effect=mock_update_order)

            mp.setattr(
                "app.delivery.service.DeliveryRepository", lambda s: mock_deliv_repo
            )
            mp.setattr(
                "app.delivery.service.OrderRepository", lambda s: mock_order_repo
            )

            resp = client.post(
                f"/api/v1/delivery-partner/deliveries/{delivery.id}/deliver"
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "DELIVERED"
            assert order.status == OrderStatus.DELIVERED
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_complete_delivery_invalid_status_rejected(monkeypatch):
    """Cannot complete delivery if not in OUT_FOR_DELIVERY status."""
    user = make_user()
    partner = make_delivery_partner(user_id=user.id)
    rest = make_restaurant()
    order = make_order(
        restaurant_id=rest.id, restaurant=rest, status=OrderStatus.PICKED_UP
    )
    delivery = make_delivery(
        order=order, partner_id=partner.id, status=DeliveryStatus.PICKED_UP
    )

    mock_session = AsyncMock()
    app.dependency_overrides[require_delivery_partner] = lambda: user
    app.dependency_overrides[get_db] = lambda: mock_session

    try:
        with monkeypatch.context() as mp:
            mock_deliv_repo = MagicMock()
            mock_deliv_repo.get_partner_by_user_id = AsyncMock(return_value=partner)
            mock_deliv_repo.get_by_id_with_details = AsyncMock(return_value=delivery)
            mp.setattr(
                "app.delivery.service.DeliveryRepository", lambda s: mock_deliv_repo
            )

            resp = client.post(
                f"/api/v1/delivery-partner/deliveries/{delivery.id}/deliver"
            )
            assert resp.status_code == 409
            assert (
                "expected status: 'out_for_delivery'" in resp.json()["detail"].lower()
            )
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_transitions_from_terminal_delivered_rejected(monkeypatch):
    """Terminal state DELIVERED rejects any further transition attempts."""
    user = make_user()
    partner = make_delivery_partner(user_id=user.id)
    rest = make_restaurant()
    order = make_order(
        restaurant_id=rest.id, restaurant=rest, status=OrderStatus.DELIVERED
    )
    delivery = make_delivery(
        order=order, partner_id=partner.id, status=DeliveryStatus.DELIVERED
    )

    mock_session = AsyncMock()
    app.dependency_overrides[require_delivery_partner] = lambda: user
    app.dependency_overrides[get_db] = lambda: mock_session

    try:
        with monkeypatch.context() as mp:
            mock_deliv_repo = MagicMock()
            mock_deliv_repo.get_partner_by_user_id = AsyncMock(return_value=partner)
            mock_deliv_repo.get_by_id_with_details = AsyncMock(return_value=delivery)
            mp.setattr(
                "app.delivery.service.DeliveryRepository", lambda s: mock_deliv_repo
            )

            assert (
                client.post(
                    f"/api/v1/delivery-partner/deliveries/{delivery.id}/pickup"
                ).status_code
                == 409
            )
            assert (
                client.post(
                    f"/api/v1/delivery-partner/deliveries/{delivery.id}/out-for-delivery"
                ).status_code
                == 409
            )
            assert (
                client.post(
                    f"/api/v1/delivery-partner/deliveries/{delivery.id}/deliver"
                ).status_code
                == 409
            )
    finally:
        app.dependency_overrides.clear()


# ==============================================================================
# 6. ACTIVE DELIVERY & DELIVERY HISTORY
# ==============================================================================


@pytest.mark.asyncio
async def test_get_current_delivery_active(monkeypatch):
    """Retrieve partner's currently active assignment."""
    user = make_user()
    partner = make_delivery_partner(user_id=user.id)
    rest = make_restaurant()
    order = make_order(
        restaurant_id=rest.id, restaurant=rest, status=OrderStatus.PICKED_UP
    )
    delivery = make_delivery(
        order=order, partner_id=partner.id, status=DeliveryStatus.PICKED_UP
    )

    mock_session = AsyncMock()
    app.dependency_overrides[require_delivery_partner] = lambda: user
    app.dependency_overrides[get_db] = lambda: mock_session

    try:
        with monkeypatch.context() as mp:
            mock_deliv_repo = MagicMock()
            mock_deliv_repo.get_partner_by_user_id = AsyncMock(return_value=partner)
            mock_deliv_repo.get_active_delivery_for_partner = AsyncMock(
                return_value=delivery
            )
            mp.setattr(
                "app.delivery.service.DeliveryRepository", lambda s: mock_deliv_repo
            )

            resp = client.get("/api/v1/delivery-partner/current-delivery")
            assert resp.status_code == 200
            data = resp.json()
            assert data["id"] == str(delivery.id)
            assert data["status"] == "PICKED_UP"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_current_delivery_none(monkeypatch):
    """Returns null if partner has no active deliveries."""
    user = make_user()
    partner = make_delivery_partner(user_id=user.id)

    mock_session = AsyncMock()
    app.dependency_overrides[require_delivery_partner] = lambda: user
    app.dependency_overrides[get_db] = lambda: mock_session

    try:
        with monkeypatch.context() as mp:
            mock_deliv_repo = MagicMock()
            mock_deliv_repo.get_partner_by_user_id = AsyncMock(return_value=partner)
            mock_deliv_repo.get_active_delivery_for_partner = AsyncMock(
                return_value=None
            )
            mp.setattr(
                "app.delivery.service.DeliveryRepository", lambda s: mock_deliv_repo
            )

            resp = client.get("/api/v1/delivery-partner/current-delivery")
            assert resp.status_code == 200
            assert resp.json() is None
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_list_my_deliveries_history(monkeypatch):
    """Retrieve history of deliveries assigned to partner."""
    user = make_user()
    partner = make_delivery_partner(user_id=user.id)
    rest = make_restaurant()
    order = make_order(
        restaurant_id=rest.id, restaurant=rest, status=OrderStatus.DELIVERED
    )
    delivery = make_delivery(
        order=order, partner_id=partner.id, status=DeliveryStatus.DELIVERED
    )

    mock_session = AsyncMock()
    app.dependency_overrides[require_delivery_partner] = lambda: user
    app.dependency_overrides[get_db] = lambda: mock_session

    try:
        with monkeypatch.context() as mp:
            mock_deliv_repo = MagicMock()
            mock_deliv_repo.get_partner_by_user_id = AsyncMock(return_value=partner)
            mock_deliv_repo.list_by_partner_paginated = AsyncMock(
                return_value=[delivery]
            )
            mock_deliv_repo.count_by_partner = AsyncMock(return_value=1)
            mp.setattr(
                "app.delivery.service.DeliveryRepository", lambda s: mock_deliv_repo
            )

            resp = client.get("/api/v1/delivery-partner/deliveries")
            assert resp.status_code == 200
            data = resp.json()
            assert data["total"] == 1
            assert len(data["items"]) == 1
            assert data["items"][0]["status"] == "DELIVERED"
    finally:
        app.dependency_overrides.clear()


# ==============================================================================
# 7. DELIVERY JOB CREATION ON RESTAURANT MARK_READY
# ==============================================================================


@pytest.mark.asyncio
async def test_restaurant_mark_ready_creates_unassigned_delivery():
    """When a restaurant transitions an order from PREPARING to READY_FOR_PICKUP,
    an UNASSIGNED Delivery record is automatically and atomically created.
    """
    owner = make_user(role=UserRole.RESTAURANT)
    rest = make_restaurant(owner_id=owner.id)
    order = make_order(restaurant_id=rest.id, status=OrderStatus.PREPARING)

    mock_session = AsyncMock()
    mock_order_repo = MagicMock()
    mock_order_repo.get_by_id_and_restaurant = AsyncMock(return_value=order)

    async def mock_update_order(o, target, expected_status=None):
        o.status = target
        return o

    mock_order_repo.update_status = AsyncMock(side_effect=mock_update_order)

    mock_rest_repo = MagicMock()
    mock_rest_repo.get_by_id = AsyncMock(return_value=rest)

    mock_deliv_repo = MagicMock()
    mock_deliv_repo.get_by_order_id = AsyncMock(return_value=None)
    created_deliveries = []

    async def mock_create_deliv(d):
        created_deliveries.append(d)
        return d

    mock_deliv_repo.create = AsyncMock(side_effect=mock_create_deliv)

    service = RestaurantOrderService(
        session=mock_session,
        order_repo=mock_order_repo,
        restaurant_repo=mock_rest_repo,
        delivery_repo=mock_deliv_repo,
    )

    updated_order = await service.mark_ready_for_pickup(
        user=owner, restaurant_id=rest.id, order_id=order.id
    )

    assert updated_order.status == OrderStatus.READY_FOR_PICKUP
    assert len(created_deliveries) == 1
    new_delivery = created_deliveries[0]
    assert new_delivery.order_id == order.id
    assert new_delivery.status == DeliveryStatus.UNASSIGNED
    assert new_delivery.delivery_partner_id is None


@pytest.mark.asyncio
async def test_restaurant_mark_ready_idempotent_if_delivery_already_exists():
    """If a Delivery already exists when order is marked ready, do not create duplicate."""
    owner = make_user(role=UserRole.RESTAURANT)
    rest = make_restaurant(owner_id=owner.id)
    order = make_order(restaurant_id=rest.id, status=OrderStatus.PREPARING)
    existing_deliv = make_delivery(order=order, status=DeliveryStatus.UNASSIGNED)

    mock_session = AsyncMock()
    mock_order_repo = MagicMock()
    mock_order_repo.get_by_id_and_restaurant = AsyncMock(return_value=order)

    async def mock_update_order(o, target, expected_status=None):
        o.status = target
        return o

    mock_order_repo.update_status = AsyncMock(side_effect=mock_update_order)

    mock_rest_repo = MagicMock()
    mock_rest_repo.get_by_id = AsyncMock(return_value=rest)

    mock_deliv_repo = MagicMock()
    mock_deliv_repo.get_by_order_id = AsyncMock(return_value=existing_deliv)
    mock_deliv_repo.create = AsyncMock()

    service = RestaurantOrderService(
        session=mock_session,
        order_repo=mock_order_repo,
        restaurant_repo=mock_rest_repo,
        delivery_repo=mock_deliv_repo,
    )

    updated_order = await service.mark_ready_for_pickup(
        user=owner, restaurant_id=rest.id, order_id=order.id
    )

    assert updated_order.status == OrderStatus.READY_FOR_PICKUP
    mock_deliv_repo.create.assert_not_called()
