"""Comprehensive tests for Restaurant and Menu APIs:
- Public Restaurant Discovery
- Restaurant Owner Management & Authorization
- Public Menu Browsing (No N+1, active/available filtering, cross-restaurant isolation)
- Restaurant Owner Menu Management (Categories, Items, Price validation, Historical order protection)
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
from app.catalog.models import MenuCategory, MenuItem
from app.core.database import get_db
from app.identity.enums import UserRole, UserStatus
from app.identity.models import User
from app.main import app
from app.restaurants.enums import RestaurantStatus
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
        email=f"user-{uid.hex[:8]}@example.com",
        password_hash="argon2id$mockhash",
        first_name="Test",
        last_name="User",
        role=role,
        status=status,
    )


def make_restaurant(
    owner_id: uuid.UUID,
    name: str = "Tasty Bistro",
    slug: str = "tasty-bistro",
    status: RestaurantStatus = RestaurantStatus.ACTIVE,
    restaurant_id: uuid.UUID | None = None,
    city: str = "Mumbai",
) -> Restaurant:
    """Helper to create Restaurant instances."""
    rid = restaurant_id or uuid.uuid4()
    return Restaurant(
        id=rid,
        owner_id=owner_id,
        name=name,
        slug=slug,
        phone="+919876543210",
        address_line1="123 Food Street",
        city=city,
        state="Maharashtra",
        postal_code="400001",
        status=status,
    )


def make_category(
    restaurant_id: uuid.UUID,
    name: str = "Starters",
    display_order: int = 0,
    is_active: bool = True,
    category_id: uuid.UUID | None = None,
) -> MenuCategory:
    """Helper to create MenuCategory instances."""
    return MenuCategory(
        id=category_id or uuid.uuid4(),
        restaurant_id=restaurant_id,
        name=name,
        display_order=display_order,
        is_active=is_active,
    )


def make_item(
    restaurant_id: uuid.UUID,
    category_id: uuid.UUID,
    name: str = "Paneer Tikka",
    price: Decimal = Decimal("250.00"),
    is_available: bool = True,
    item_id: uuid.UUID | None = None,
) -> MenuItem:
    """Helper to create MenuItem instances."""
    return MenuItem(
        id=item_id or uuid.uuid4(),
        restaurant_id=restaurant_id,
        category_id=category_id,
        name=name,
        price=price,
        is_available=is_available,
    )


# ==============================================================================
# 1. PUBLIC RESTAURANT DISCOVERY TESTS
# ==============================================================================


@pytest.mark.asyncio
async def test_public_list_active_restaurants(monkeypatch):
    """Verify listing active restaurants with pagination and total count."""
    owner = make_user()
    rest1 = make_restaurant(owner.id, "Bistro 1", "bistro-1", RestaurantStatus.ACTIVE)
    rest2 = make_restaurant(owner.id, "Bistro 2", "bistro-2", RestaurantStatus.ACTIVE)

    mock_session = AsyncMock()

    async def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with monkeypatch.context() as mp:
            mock_repo = MagicMock()
            mock_repo.list_active = AsyncMock(return_value=[rest1, rest2])
            mock_repo.count_active = AsyncMock(return_value=2)
            mp.setattr(
                "app.restaurants.service.RestaurantRepository", lambda s: mock_repo
            )

            response = client.get("/api/v1/restaurants?skip=0&limit=10")
            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 2
            assert data["skip"] == 0
            assert data["limit"] == 10
            assert len(data["items"]) == 2
            assert data["items"][0]["slug"] == "bistro-1"
            assert data["items"][1]["slug"] == "bistro-2"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_public_list_active_restaurants_filter_by_city(monkeypatch):
    """Verify city filter correctly queries repository."""
    owner = make_user()
    rest = make_restaurant(owner.id, "Delhi Spices", "delhi-spices", city="Delhi")

    mock_session = AsyncMock()

    async def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with monkeypatch.context() as mp:
            mock_repo = MagicMock()
            mock_repo.list_active = AsyncMock(return_value=[rest])
            mock_repo.count_active = AsyncMock(return_value=1)
            mp.setattr(
                "app.restaurants.service.RestaurantRepository", lambda s: mock_repo
            )

            response = client.get("/api/v1/restaurants?city=Delhi")
            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 1
            assert data["items"][0]["city"] == "Delhi"
            mock_repo.list_active.assert_called_once_with(
                skip=0, limit=20, city="Delhi"
            )
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_public_get_restaurant_by_slug_success(monkeypatch):
    """Verify retrieving an active restaurant by public slug."""
    owner = make_user()
    rest = make_restaurant(owner.id, "Taj Dine", "taj-dine", RestaurantStatus.ACTIVE)

    mock_session = AsyncMock()

    async def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with monkeypatch.context() as mp:
            mock_repo = MagicMock()
            mock_repo.get_by_slug = AsyncMock(return_value=rest)
            mp.setattr(
                "app.restaurants.service.RestaurantRepository", lambda s: mock_repo
            )

            response = client.get("/api/v1/restaurants/taj-dine")
            assert response.status_code == 200
            data = response.json()
            assert data["name"] == "Taj Dine"
            assert data["slug"] == "taj-dine"
            assert data["status"] == "ACTIVE"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_public_get_restaurant_by_slug_not_found_or_inactive(monkeypatch):
    """Verify missing or non-active restaurants return 404."""
    owner = make_user()
    inactive_rest = make_restaurant(
        owner.id, "Closed Dine", "closed-dine", RestaurantStatus.INACTIVE
    )

    mock_session = AsyncMock()

    async def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with monkeypatch.context() as mp:
            mock_repo = MagicMock()
            # 1. Non-existent slug
            mock_repo.get_by_slug = AsyncMock(return_value=None)
            mp.setattr(
                "app.restaurants.service.RestaurantRepository", lambda s: mock_repo
            )

            res1 = client.get("/api/v1/restaurants/non-existent-slug")
            assert res1.status_code == 404

            # 2. Inactive restaurant slug
            mock_repo.get_by_slug = AsyncMock(return_value=inactive_rest)
            res2 = client.get("/api/v1/restaurants/closed-dine")
            assert res2.status_code == 404
    finally:
        app.dependency_overrides.clear()


# ==============================================================================
# 2. RESTAURANT AUTHORIZATION & MANAGEMENT TESTS
# ==============================================================================


def test_unauthenticated_restaurant_management_rejected():
    """Unauthenticated requests to management endpoints return 401."""
    # Create restaurant
    res1 = client.post(
        "/api/v1/restaurants",
        json={
            "name": "New Restaurant",
            "phone": "+919999999999",
            "address_line1": "Street 1",
            "city": "Mumbai",
            "state": "Maharashtra",
            "postal_code": "400001",
        },
    )
    assert res1.status_code == 401

    # List my restaurants
    res2 = client.get("/api/v1/restaurants/mine")
    assert res2.status_code == 401

    # Update restaurant
    res3 = client.patch(f"/api/v1/restaurants/{uuid.uuid4()}", json={"name": "Updated"})
    assert res3.status_code == 401


@pytest.mark.asyncio
async def test_customer_cannot_manage_restaurants():
    """A user with CUSTOMER role cannot access restaurant-management endpoints."""
    from app.identity.dependencies import require_restaurant

    app.dependency_overrides[require_restaurant] = lambda: (_ for _ in ()).throw(
        pytest.importorskip("fastapi").HTTPException(
            status_code=403, detail="Insufficient permissions for this resource."
        )
    )
    try:
        res = client.post(
            "/api/v1/restaurants",
            json={
                "name": "Customer Bistro",
                "phone": "+919999999999",
                "address_line1": "Street 1",
                "city": "Mumbai",
                "state": "Maharashtra",
                "postal_code": "400001",
            },
            headers={"Authorization": "Bearer mock-token"},
        )
        assert res.status_code == 403
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_restaurant_owner_can_create_restaurant(monkeypatch):
    """RESTAURANT user creates a restaurant; owner_id is derived from auth; slug derived if omitted."""
    from app.identity.dependencies import require_restaurant

    owner = make_user(role=UserRole.RESTAURANT)
    mock_session = AsyncMock()

    app.dependency_overrides[require_restaurant] = lambda: owner
    app.dependency_overrides[get_db] = lambda: mock_session
    try:
        with monkeypatch.context() as mp:
            mock_repo = MagicMock()
            mock_repo.get_by_slug = AsyncMock(return_value=None)
            mock_repo.create = AsyncMock(side_effect=lambda r: r)
            mp.setattr(
                "app.restaurants.service.RestaurantRepository", lambda s: mock_repo
            )

            payload = {
                "name": "Spice Route",
                "phone": "+919876543210",
                "address_line1": "45 Curry Lane",
                "city": "Bangalore",
                "state": "Karnataka",
                "postal_code": "560001",
            }
            response = client.post("/api/v1/restaurants", json=payload)
            assert response.status_code == 201
            data = response.json()
            assert data["name"] == "Spice Route"
            assert data["slug"] == "spice-route"
            assert data["owner_id"] == str(owner.id)
            assert data["status"] == "ACTIVE"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_restaurant_duplicate_slug_returns_409(monkeypatch):
    """Duplicate restaurant slug returns 409 Conflict."""
    from app.identity.dependencies import require_restaurant

    owner = make_user(role=UserRole.RESTAURANT)
    existing_rest = make_restaurant(owner.id, "Existing", "spice-route")
    mock_session = AsyncMock()

    app.dependency_overrides[require_restaurant] = lambda: owner
    app.dependency_overrides[get_db] = lambda: mock_session
    try:
        with monkeypatch.context() as mp:
            mock_repo = MagicMock()
            mock_repo.get_by_slug = AsyncMock(return_value=existing_rest)
            mp.setattr(
                "app.restaurants.service.RestaurantRepository", lambda s: mock_repo
            )

            payload = {
                "name": "Spice Route",
                "slug": "spice-route",
                "phone": "+919876543210",
                "address_line1": "45 Curry Lane",
                "city": "Bangalore",
                "state": "Karnataka",
                "postal_code": "560001",
            }
            response = client.post("/api/v1/restaurants", json=payload)
            assert response.status_code == 409
            assert "already in use" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_list_my_restaurants_returns_owner_records(monkeypatch):
    """GET /restaurants/mine returns caller's restaurants."""
    from app.identity.dependencies import require_restaurant

    owner = make_user(role=UserRole.RESTAURANT)
    rest1 = make_restaurant(owner.id, "Owner Rest 1", "owner-rest-1")
    rest2 = make_restaurant(
        owner.id, "Owner Rest 2", "owner-rest-2", status=RestaurantStatus.INACTIVE
    )
    mock_session = AsyncMock()

    app.dependency_overrides[require_restaurant] = lambda: owner
    app.dependency_overrides[get_db] = lambda: mock_session
    try:
        with monkeypatch.context() as mp:
            mock_repo = MagicMock()
            mock_repo.list_by_owner = AsyncMock(return_value=[rest1, rest2])
            mp.setattr(
                "app.restaurants.service.RestaurantRepository", lambda s: mock_repo
            )

            response = client.get("/api/v1/restaurants/mine")
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 2
            assert data[0]["name"] == "Owner Rest 1"
            assert data[1]["status"] == "INACTIVE"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_owner_cannot_modify_another_owners_restaurant(monkeypatch):
    """Modifying another user's restaurant returns 403 Forbidden."""
    from app.identity.dependencies import require_restaurant

    owner_a = make_user(role=UserRole.RESTAURANT)
    owner_b = make_user(role=UserRole.RESTAURANT)
    rest_b = make_restaurant(owner_b.id, "Rest B", "rest-b")
    mock_session = AsyncMock()

    app.dependency_overrides[require_restaurant] = lambda: owner_a
    app.dependency_overrides[get_db] = lambda: mock_session
    try:
        with monkeypatch.context() as mp:
            mock_repo = MagicMock()
            mock_repo.get_by_id = AsyncMock(return_value=rest_b)
            mp.setattr(
                "app.restaurants.service.RestaurantRepository", lambda s: mock_repo
            )

            response = client.patch(
                f"/api/v1/restaurants/{rest_b.id}",
                json={"name": "Hacked Name"},
            )
            assert response.status_code == 403
            assert "permission" in response.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_owner_update_permitted_fields_and_status_rules(monkeypatch):
    """Owner can update profile and toggle ACTIVE/INACTIVE, but cannot modify suspended restaurant."""
    from app.identity.dependencies import require_restaurant

    owner = make_user(role=UserRole.RESTAURANT)
    rest = make_restaurant(owner.id, "Active Rest", "active-rest")
    mock_session = AsyncMock()

    app.dependency_overrides[require_restaurant] = lambda: owner
    app.dependency_overrides[get_db] = lambda: mock_session
    try:
        with monkeypatch.context() as mp:
            mock_repo = MagicMock()
            mock_repo.get_by_id = AsyncMock(return_value=rest)
            mock_repo.get_by_slug = AsyncMock(return_value=None)
            mock_repo.update = AsyncMock(side_effect=lambda r: r)
            mp.setattr(
                "app.restaurants.service.RestaurantRepository", lambda s: mock_repo
            )

            # 1. Update permitted fields (toggle to INACTIVE)
            res1 = client.patch(
                f"/api/v1/restaurants/{rest.id}",
                json={"city": "Pune", "status": "INACTIVE"},
            )
            assert res1.status_code == 200
            assert res1.json()["city"] == "Pune"
            assert res1.json()["status"] == "INACTIVE"

            # 2. Cannot set status to SUSPENDED
            res2 = client.patch(
                f"/api/v1/restaurants/{rest.id}",
                json={"status": "SUSPENDED"},
            )
            assert res2.status_code == 400
            assert "cannot suspend" in res2.json()["detail"].lower()

            # 3. If restaurant is SUSPENDED, owner cannot modify it
            rest.status = RestaurantStatus.SUSPENDED
            res3 = client.patch(
                f"/api/v1/restaurants/{rest.id}",
                json={"status": "ACTIVE"},
            )
            assert res3.status_code == 400
            assert "suspended" in res3.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


# ==============================================================================
# 3. PUBLIC MENU BROWSING TESTS
# ==============================================================================


@pytest.mark.asyncio
async def test_public_menu_browsing_success_and_no_n_plus_one(monkeypatch):
    """Verify loading full restaurant menu grouping items by category without N+1 queries."""
    owner = make_user()
    rest = make_restaurant(owner.id, "Biryani House", "biryani-house")
    cat1 = make_category(rest.id, "Biryanis", 1)
    cat2 = make_category(rest.id, "Beverages", 2)
    item1 = make_item(rest.id, cat1.id, "Hyderabadi Biryani", Decimal("350.00"))
    item2 = make_item(rest.id, cat2.id, "Lassi", Decimal("60.00"))

    mock_session = AsyncMock()

    async def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with monkeypatch.context() as mp:
            mock_rest_repo = MagicMock()
            mock_rest_repo.get_by_slug = AsyncMock(return_value=rest)
            mp.setattr(
                "app.catalog.service.RestaurantRepository", lambda s: mock_rest_repo
            )

            mock_cat_repo = MagicMock()
            # Precisely two calls: one for categories, one for items
            mock_cat_repo.list_active_categories = AsyncMock(return_value=[cat1, cat2])
            mock_cat_repo.list_available_items = AsyncMock(return_value=[item1, item2])
            mp.setattr("app.catalog.service.CatalogRepository", lambda s: mock_cat_repo)

            response = client.get("/api/v1/restaurants/biryani-house/menu")
            assert response.status_code == 200
            data = response.json()
            assert data["restaurant_name"] == "Biryani House"
            assert len(data["categories"]) == 2
            assert data["categories"][0]["name"] == "Biryanis"
            assert len(data["categories"][0]["items"]) == 1
            assert data["categories"][0]["items"][0]["name"] == "Hyderabadi Biryani"
            assert data["categories"][1]["name"] == "Beverages"
            assert len(data["categories"][1]["items"]) == 1

            # Assert only 2 queries executed
            mock_cat_repo.list_active_categories.assert_called_once_with(rest.id)
            mock_cat_repo.list_available_items.assert_called_once_with(rest.id)
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_public_menu_browsing_category_and_items_endpoints(monkeypatch):
    """Verify listing categories and items via dedicated public endpoints."""
    owner = make_user()
    rest = make_restaurant(owner.id, "Pasta Palace", "pasta-palace")
    cat = make_category(rest.id, "Pastas", 1)
    item = make_item(rest.id, cat.id, "Penne Arrabbiata", Decimal("280.00"))

    mock_session = AsyncMock()

    async def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with monkeypatch.context() as mp:
            mock_rest_repo = MagicMock()
            mock_rest_repo.get_by_slug = AsyncMock(return_value=rest)
            mp.setattr(
                "app.catalog.service.RestaurantRepository", lambda s: mock_rest_repo
            )

            mock_cat_repo = MagicMock()
            mock_cat_repo.list_active_categories = AsyncMock(return_value=[cat])
            mock_cat_repo.list_available_items = AsyncMock(return_value=[item])
            mock_cat_repo.get_item_by_id_and_restaurant = AsyncMock(return_value=item)
            mock_cat_repo.get_category_by_id_and_restaurant = AsyncMock(
                return_value=cat
            )
            mp.setattr("app.catalog.service.CatalogRepository", lambda s: mock_cat_repo)

            # 1. Categories endpoint
            res1 = client.get("/api/v1/restaurants/pasta-palace/categories")
            assert res1.status_code == 200
            assert res1.json()[0]["name"] == "Pastas"

            # 2. Items endpoint
            res2 = client.get("/api/v1/restaurants/pasta-palace/items")
            assert res2.status_code == 200
            assert res2.json()[0]["name"] == "Penne Arrabbiata"

            # 3. Single item endpoint
            res3 = client.get(f"/api/v1/restaurants/pasta-palace/items/{item.id}")
            assert res3.status_code == 200
            assert res3.json()["id"] == str(item.id)
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_public_menu_item_unavailable_or_inactive_category_returns_404(
    monkeypatch,
):
    """Unavailable items or items belonging to inactive categories return 404."""
    owner = make_user()
    rest = make_restaurant(owner.id, "Cafe Roma", "cafe-roma")
    cat = make_category(rest.id, "Seasonal", is_active=False)
    item_unavailable = make_item(rest.id, cat.id, "Special Soup", is_available=False)
    item_inactive_cat = make_item(rest.id, cat.id, "Winter Tea", is_available=True)

    mock_session = AsyncMock()

    async def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with monkeypatch.context() as mp:
            mock_rest_repo = MagicMock()
            mock_rest_repo.get_by_slug = AsyncMock(return_value=rest)
            mp.setattr(
                "app.catalog.service.RestaurantRepository", lambda s: mock_rest_repo
            )

            mock_cat_repo = MagicMock()
            # Unavailable item
            mock_cat_repo.get_item_by_id_and_restaurant = AsyncMock(
                return_value=item_unavailable
            )
            mp.setattr("app.catalog.service.CatalogRepository", lambda s: mock_cat_repo)

            res1 = client.get(
                f"/api/v1/restaurants/cafe-roma/items/{item_unavailable.id}"
            )
            assert res1.status_code == 404

            # Available item in inactive category
            mock_cat_repo.get_item_by_id_and_restaurant = AsyncMock(
                return_value=item_inactive_cat
            )
            mock_cat_repo.get_category_by_id_and_restaurant = AsyncMock(
                return_value=cat
            )
            res2 = client.get(
                f"/api/v1/restaurants/cafe-roma/items/{item_inactive_cat.id}"
            )
            assert res2.status_code == 404
    finally:
        app.dependency_overrides.clear()


# ==============================================================================
# 4. RESTAURANT OWNER MENU MANAGEMENT TESTS
# ==============================================================================


@pytest.mark.asyncio
async def test_owner_create_and_update_category_success(monkeypatch):
    """Owner can create and update menu categories."""
    from app.identity.dependencies import require_restaurant

    owner = make_user(role=UserRole.RESTAURANT)
    rest = make_restaurant(owner.id, "Dosa Hub", "dosa-hub")
    mock_session = AsyncMock()

    app.dependency_overrides[require_restaurant] = lambda: owner
    app.dependency_overrides[get_db] = lambda: mock_session
    try:
        with monkeypatch.context() as mp:
            mock_rest_repo = MagicMock()
            mock_rest_repo.get_by_id = AsyncMock(return_value=rest)
            mp.setattr(
                "app.catalog.service.RestaurantRepository", lambda s: mock_rest_repo
            )

            mock_cat_repo = MagicMock()
            mock_cat_repo.get_category_by_name_and_restaurant = AsyncMock(
                return_value=None
            )
            mock_cat_repo.create_category = AsyncMock(side_effect=lambda c: c)
            mp.setattr("app.catalog.service.CatalogRepository", lambda s: mock_cat_repo)

            # 1. Create category
            res1 = client.post(
                f"/api/v1/restaurants/{rest.id}/categories",
                json={"name": "Special Dosas", "display_order": 1, "is_active": True},
            )
            assert res1.status_code == 201
            cat_data = res1.json()
            assert cat_data["name"] == "Special Dosas"
            cat_id = cat_data["id"]

            # 2. Update category
            created_cat = make_category(
                rest.id, "Special Dosas", category_id=uuid.UUID(cat_id)
            )
            mock_cat_repo.get_category_by_id_and_restaurant = AsyncMock(
                return_value=created_cat
            )
            mock_cat_repo.update_category = AsyncMock(side_effect=lambda c: c)

            res2 = client.patch(
                f"/api/v1/restaurants/{rest.id}/categories/{cat_id}",
                json={"name": "Gourmet Dosas", "is_active": False},
            )
            assert res2.status_code == 200
            assert res2.json()["name"] == "Gourmet Dosas"
            assert res2.json()["is_active"] is False
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_owner_create_category_duplicate_name_returns_409(monkeypatch):
    """Duplicate category name in the same restaurant returns 409 Conflict."""
    from app.identity.dependencies import require_restaurant

    owner = make_user(role=UserRole.RESTAURANT)
    rest = make_restaurant(owner.id, "Dosa Hub", "dosa-hub")
    existing_cat = make_category(rest.id, "Starters")
    mock_session = AsyncMock()

    app.dependency_overrides[require_restaurant] = lambda: owner
    app.dependency_overrides[get_db] = lambda: mock_session
    try:
        with monkeypatch.context() as mp:
            mock_rest_repo = MagicMock()
            mock_rest_repo.get_by_id = AsyncMock(return_value=rest)
            mp.setattr(
                "app.catalog.service.RestaurantRepository", lambda s: mock_rest_repo
            )

            mock_cat_repo = MagicMock()
            mock_cat_repo.get_category_by_name_and_restaurant = AsyncMock(
                return_value=existing_cat
            )
            mp.setattr("app.catalog.service.CatalogRepository", lambda s: mock_cat_repo)

            response = client.post(
                f"/api/v1/restaurants/{rest.id}/categories",
                json={"name": "Starters"},
            )
            assert response.status_code == 409
            assert "already exists" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_owner_create_menu_item_validations(monkeypatch):
    """Create menu item validates price non-negative and category ownership."""
    from app.identity.dependencies import require_restaurant

    owner = make_user(role=UserRole.RESTAURANT)
    rest_a = make_restaurant(owner.id, "Rest A", "rest-a")
    rest_b = make_restaurant(uuid.uuid4(), "Rest B", "rest-b")
    cat_in_rest_b = make_category(rest_b.id, "Drinks in B")
    cat_in_rest_a = make_category(rest_a.id, "Drinks in A")
    mock_session = AsyncMock()

    app.dependency_overrides[require_restaurant] = lambda: owner
    app.dependency_overrides[get_db] = lambda: mock_session
    try:
        with monkeypatch.context() as mp:
            mock_rest_repo = MagicMock()
            mock_rest_repo.get_by_id = AsyncMock(return_value=rest_a)
            mp.setattr(
                "app.catalog.service.RestaurantRepository", lambda s: mock_rest_repo
            )

            mock_cat_repo = MagicMock()
            mock_cat_repo.get_category_by_id_and_restaurant = AsyncMock(
                side_effect=lambda category_id, restaurant_id: (
                    cat_in_rest_a
                    if category_id == cat_in_rest_a.id and restaurant_id == rest_a.id
                    else None
                )
            )
            mock_cat_repo.create_item = AsyncMock(side_effect=lambda i: i)
            mp.setattr("app.catalog.service.CatalogRepository", lambda s: mock_cat_repo)

            # 1. Negative price rejected by Pydantic validation (422)
            res1 = client.post(
                f"/api/v1/restaurants/{rest_a.id}/items",
                json={
                    "category_id": str(cat_in_rest_a.id),
                    "name": "Invalid Item",
                    "price": -10.00,
                },
            )
            assert res1.status_code == 422

            # 2. Cross-restaurant category assignment rejected (400)
            res2 = client.post(
                f"/api/v1/restaurants/{rest_a.id}/items",
                json={
                    "category_id": str(cat_in_rest_b.id),
                    "name": "Cross Restaurant Item",
                    "price": 150.00,
                },
            )
            assert res2.status_code == 400
            assert "does not belong" in res2.json()["detail"]

            # 3. Valid creation succeeds (201)
            res3 = client.post(
                f"/api/v1/restaurants/{rest_a.id}/items",
                json={
                    "category_id": str(cat_in_rest_a.id),
                    "name": "Mango Lassi",
                    "price": 75.50,
                    "is_available": True,
                },
            )
            assert res3.status_code == 201
            assert res3.json()["name"] == "Mango Lassi"
            assert Decimal(res3.json()["price"]) == Decimal("75.50")
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_delete_menu_item_with_historical_orders_rejected(monkeypatch):
    """Deleting a menu item referenced in historical orders returns 409 Conflict."""
    from app.identity.dependencies import require_restaurant

    owner = make_user(role=UserRole.RESTAURANT)
    rest = make_restaurant(owner.id, "Grill House", "grill-house")
    cat = make_category(rest.id, "Mains")
    item = make_item(rest.id, cat.id, "Chicken Kebab")
    mock_session = AsyncMock()

    app.dependency_overrides[require_restaurant] = lambda: owner
    app.dependency_overrides[get_db] = lambda: mock_session
    try:
        with monkeypatch.context() as mp:
            mock_rest_repo = MagicMock()
            mock_rest_repo.get_by_id = AsyncMock(return_value=rest)
            mp.setattr(
                "app.catalog.service.RestaurantRepository", lambda s: mock_rest_repo
            )

            mock_cat_repo = MagicMock()
            mock_cat_repo.get_item_by_id_and_restaurant = AsyncMock(return_value=item)
            # Item has 3 historical orders
            mock_cat_repo.count_historical_orders_for_item = AsyncMock(return_value=3)
            mp.setattr("app.catalog.service.CatalogRepository", lambda s: mock_cat_repo)

            response = client.delete(f"/api/v1/restaurants/{rest.id}/items/{item.id}")
            assert response.status_code == 409
            assert "historical order" in response.json()["detail"]
            assert "is_available=false" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_delete_menu_item_without_orders_succeeds(monkeypatch):
    """Deleting a menu item with zero orders succeeds with 204 No Content."""
    from app.identity.dependencies import require_restaurant

    owner = make_user(role=UserRole.RESTAURANT)
    rest = make_restaurant(owner.id, "Grill House", "grill-house")
    cat = make_category(rest.id, "Mains")
    item = make_item(rest.id, cat.id, "Unordered Kebab")
    mock_session = AsyncMock()

    app.dependency_overrides[require_restaurant] = lambda: owner
    app.dependency_overrides[get_db] = lambda: mock_session
    try:
        with monkeypatch.context() as mp:
            mock_rest_repo = MagicMock()
            mock_rest_repo.get_by_id = AsyncMock(return_value=rest)
            mp.setattr(
                "app.catalog.service.RestaurantRepository", lambda s: mock_rest_repo
            )

            mock_cat_repo = MagicMock()
            mock_cat_repo.get_item_by_id_and_restaurant = AsyncMock(return_value=item)
            # 0 orders
            mock_cat_repo.count_historical_orders_for_item = AsyncMock(return_value=0)
            mock_cat_repo.delete_item = AsyncMock(return_value=None)
            mp.setattr("app.catalog.service.CatalogRepository", lambda s: mock_cat_repo)

            response = client.delete(f"/api/v1/restaurants/{rest.id}/items/{item.id}")
            assert response.status_code == 204
            mock_cat_repo.delete_item.assert_called_once_with(item)
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_non_owner_restaurant_user_cannot_manage_catalog(monkeypatch):
    """A RESTAURANT user attempting to manage categories or items for another restaurant gets 403."""
    from app.identity.dependencies import require_restaurant

    owner_a = make_user(role=UserRole.RESTAURANT)
    owner_b = make_user(role=UserRole.RESTAURANT)
    rest_b = make_restaurant(owner_b.id, "Rest B", "rest-b")
    mock_session = AsyncMock()

    app.dependency_overrides[require_restaurant] = lambda: owner_a
    app.dependency_overrides[get_db] = lambda: mock_session
    try:
        with monkeypatch.context() as mp:
            mock_rest_repo = MagicMock()
            mock_rest_repo.get_by_id = AsyncMock(return_value=rest_b)
            mp.setattr(
                "app.catalog.service.RestaurantRepository", lambda s: mock_rest_repo
            )

            # Try to create category in rest_b
            res = client.post(
                f"/api/v1/restaurants/{rest_b.id}/categories",
                json={"name": "Hacked Category"},
            )
            assert res.status_code == 403
            assert "permission" in res.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()
