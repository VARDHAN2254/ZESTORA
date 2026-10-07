"""Tests for Restaurant and Catalog foundation models, constraints, and migrations."""

import uuid
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import sqlalchemy as sa
from alembic.command import downgrade, upgrade
from alembic.config import Config

from app.catalog import CatalogRepository, MenuCategory, MenuItem
from app.core.database import Base
from app.identity import User
from app.restaurants import Restaurant, RestaurantRepository, RestaurantStatus


def test_restaurant_table_metadata():
    """Verify Restaurant table registration, columns, constraints, and indexes."""
    assert "restaurants" in Base.metadata.tables
    table = Base.metadata.tables["restaurants"]

    # Primary key
    assert [col.name for col in table.primary_key.columns] == ["id"]
    assert isinstance(table.c.id.type, sa.Uuid)

    # Columns and nullability
    expected_cols = {
        "id": (False, sa.Uuid),
        "owner_id": (False, sa.Uuid),
        "name": (False, sa.String),
        "slug": (False, sa.String),
        "description": (True, sa.Text),
        "phone": (False, sa.String),
        "address_line1": (False, sa.String),
        "address_line2": (True, sa.String),
        "city": (False, sa.String),
        "state": (False, sa.String),
        "postal_code": (False, sa.String),
        "latitude": (True, sa.Numeric),
        "longitude": (True, sa.Numeric),
        "status": (False, sa.Enum),
        "created_at": (False, sa.DateTime),
        "updated_at": (False, sa.DateTime),
    }
    for col_name, (nullable, expected_type) in expected_cols.items():
        assert col_name in table.columns, f"Column {col_name} missing from restaurants"
        col = table.columns[col_name]
        assert col.nullable is nullable
        assert isinstance(col.type, expected_type)

    # Foreign key to users
    fk_targets = [(fk.column.table.name, fk.column.name) for fk in table.foreign_keys]
    assert ("users", "id") in fk_targets

    # Unique slug constraint
    unique_constraints = [
        c for c in table.constraints if isinstance(c, sa.UniqueConstraint)
    ]
    slug_unique = any(
        "slug" in [col.name for col in c.columns] for c in unique_constraints
    )
    assert slug_unique

    # Indexes
    index_names = {idx.name: [c.name for c in idx.columns] for idx in table.indexes}
    assert "ix_restaurants_owner_id" in index_names
    assert index_names["ix_restaurants_owner_id"] == ["owner_id"]
    assert "ix_restaurants_status" in index_names
    assert index_names["ix_restaurants_status"] == ["status"]


def test_restaurant_status_enum():
    """Verify RestaurantStatus values."""
    assert {s.value for s in RestaurantStatus} == {"ACTIVE", "INACTIVE", "SUSPENDED"}
    assert RestaurantStatus.ACTIVE == "ACTIVE"
    assert RestaurantStatus.INACTIVE == "INACTIVE"
    assert RestaurantStatus.SUSPENDED == "SUSPENDED"


def test_menu_category_table_metadata():
    """Verify MenuCategory table registration, columns, constraints, and indexes."""
    assert "menu_categories" in Base.metadata.tables
    table = Base.metadata.tables["menu_categories"]

    # Primary key
    assert [col.name for col in table.primary_key.columns] == ["id"]
    assert isinstance(table.c.id.type, sa.Uuid)

    # Columns and nullability
    expected_cols = {
        "id": (False, sa.Uuid),
        "restaurant_id": (False, sa.Uuid),
        "name": (False, sa.String),
        "description": (True, sa.Text),
        "display_order": (False, sa.Integer),
        "is_active": (False, sa.Boolean),
        "created_at": (False, sa.DateTime),
        "updated_at": (False, sa.DateTime),
    }
    for col_name, (nullable, expected_type) in expected_cols.items():
        assert col_name in table.columns
        col = table.columns[col_name]
        assert col.nullable is nullable
        assert isinstance(col.type, expected_type)

    # Foreign key to restaurants
    fk_targets = [(fk.column.table.name, fk.column.name) for fk in table.foreign_keys]
    assert ("restaurants", "id") in fk_targets

    # Unique constraint (restaurant_id, name)
    unique_constraints = [
        c for c in table.constraints if isinstance(c, sa.UniqueConstraint)
    ]
    rest_name_unique = any(
        {col.name for col in c.columns} == {"restaurant_id", "name"}
        for c in unique_constraints
    )
    assert rest_name_unique, "uq_menu_categories_restaurant_id_name missing"

    # Unique constraint (id, restaurant_id) for composite FK integrity
    id_rest_unique = any(
        {col.name for col in c.columns} == {"id", "restaurant_id"}
        for c in unique_constraints
    )
    assert id_rest_unique, "uq_menu_categories_id_restaurant_id missing"

    # Index on restaurant_id
    index_names = {idx.name: [c.name for c in idx.columns] for idx in table.indexes}
    assert "ix_menu_categories_restaurant_id" in index_names


def test_menu_item_table_metadata_and_cross_table_integrity():
    """Verify MenuItem table metadata, price check, and cross-table FK integrity."""
    assert "menu_items" in Base.metadata.tables
    table = Base.metadata.tables["menu_items"]

    # Primary key
    assert [col.name for col in table.primary_key.columns] == ["id"]
    assert isinstance(table.c.id.type, sa.Uuid)

    # Price non-negative check constraint
    check_constraints = [
        c for c in table.constraints if isinstance(c, sa.CheckConstraint)
    ]
    assert any("price >= 0" in str(c.sqltext) for c in check_constraints)

    # Cross-table composite foreign key ensuring item.restaurant_id == category.restaurant_id
    fk_constraints = [
        c for c in table.constraints if isinstance(c, sa.ForeignKeyConstraint)
    ]

    # Check composite FK (category_id, restaurant_id) -> menu_categories(id, restaurant_id)
    composite_fk = any(
        [col.name for col in c.columns] == ["category_id", "restaurant_id"]
        and [elem.column.name for elem in c.elements] == ["id", "restaurant_id"]
        for c in fk_constraints
    )
    assert composite_fk, "Composite FK ensuring category belongs to restaurant missing"

    # Indexes
    index_names = {idx.name: [c.name for c in idx.columns] for idx in table.indexes}
    assert "ix_menu_items_restaurant_id" in index_names
    assert "ix_menu_items_category_id" in index_names


def test_relationships_declarations():
    """Verify declared SQLAlchemy relationships across User, Restaurant, Category, Item."""
    # User -> Restaurant
    assert hasattr(User, "restaurants")
    assert User.restaurants.property.target == Restaurant.__table__

    # Restaurant -> User, Category, Item
    assert hasattr(Restaurant, "owner")
    assert Restaurant.owner.property.target == User.__table__
    assert hasattr(Restaurant, "categories")
    assert Restaurant.categories.property.target == MenuCategory.__table__
    assert hasattr(Restaurant, "menu_items")
    assert Restaurant.menu_items.property.target == MenuItem.__table__

    # MenuCategory -> Restaurant, Item
    assert hasattr(MenuCategory, "restaurant")
    assert MenuCategory.restaurant.property.target == Restaurant.__table__
    assert hasattr(MenuCategory, "menu_items")
    assert MenuCategory.menu_items.property.target == MenuItem.__table__

    # MenuItem -> Restaurant, Category
    assert hasattr(MenuItem, "restaurant")
    assert MenuItem.restaurant.property.target == Restaurant.__table__
    assert hasattr(MenuItem, "category")
    assert MenuItem.category.property.target == MenuCategory.__table__


def test_model_in_memory_instantiation():
    """Verify in-memory model instantiation sets defaults correctly."""
    owner_id = uuid.uuid4()
    restaurant = Restaurant(
        owner_id=owner_id,
        name="Pizza Bella",
        slug="pizza-bella",
        phone="555-0100",
        address_line1="123 Main St",
        city="Springfield",
        state="IL",
        postal_code="62701",
        latitude=Decimal("39.781721"),
        longitude=Decimal("-89.650148"),
    )
    assert isinstance(restaurant.id, uuid.UUID)
    assert restaurant.status == RestaurantStatus.ACTIVE
    assert restaurant.name == "Pizza Bella"
    assert restaurant.slug == "pizza-bella"
    assert isinstance(restaurant.created_at, datetime)
    assert isinstance(restaurant.updated_at, datetime)
    assert "Pizza Bella" in repr(restaurant)

    category = MenuCategory(
        restaurant_id=restaurant.id,
        name="Pizzas",
        display_order=1,
    )
    assert isinstance(category.id, uuid.UUID)
    assert category.is_active is True
    assert category.display_order == 1
    assert "Pizzas" in repr(category)

    item = MenuItem(
        restaurant_id=restaurant.id,
        category_id=category.id,
        name="Margherita",
        price=Decimal("12.99"),
    )
    assert isinstance(item.id, uuid.UUID)
    assert item.price == Decimal("12.99")
    assert item.is_available is True
    assert "Margherita" in repr(item)


@pytest.mark.asyncio
async def test_restaurant_repository_methods():
    """Verify RestaurantRepository operations."""
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    repo = RestaurantRepository(mock_session)

    # get_by_id
    mock_result_id = MagicMock()
    mock_restaurant = MagicMock(spec=Restaurant)
    mock_result_id.scalar_one_or_none.return_value = mock_restaurant
    mock_session.execute.return_value = mock_result_id

    rest_id = uuid.uuid4()
    assert await repo.get_by_id(rest_id) == mock_restaurant

    # get_by_slug
    mock_result_slug = MagicMock()
    mock_result_slug.scalar_one_or_none.return_value = mock_restaurant
    mock_session.execute.return_value = mock_result_slug
    assert await repo.get_by_slug("pizza-bella") == mock_restaurant

    # list_by_owner
    mock_result_owner = MagicMock()
    mock_result_owner.scalars.return_value.all.return_value = [mock_restaurant]
    mock_session.execute.return_value = mock_result_owner
    owner_id = uuid.uuid4()
    assert await repo.list_by_owner(owner_id) == [mock_restaurant]

    # create
    new_rest = Restaurant(
        owner_id=owner_id,
        name="Test",
        slug="test",
        phone="123",
        address_line1="Line 1",
        city="City",
        state="ST",
        postal_code="12345",
    )
    assert await repo.create(new_rest) == new_rest
    mock_session.add.assert_called_once_with(new_rest)
    mock_session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_catalog_repository_methods():
    """Verify CatalogRepository operations."""
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    repo = CatalogRepository(mock_session)

    # Category methods
    mock_cat = MagicMock(spec=MenuCategory)
    mock_res_cat = MagicMock()
    mock_res_cat.scalar_one_or_none.return_value = mock_cat
    mock_session.execute.return_value = mock_res_cat

    cat_id = uuid.uuid4()
    assert await repo.get_category_by_id(cat_id) == mock_cat

    mock_res_list_cat = MagicMock()
    mock_res_list_cat.scalars.return_value.all.return_value = [mock_cat]
    mock_session.execute.return_value = mock_res_list_cat
    rest_id = uuid.uuid4()
    assert await repo.list_categories_by_restaurant(rest_id) == [mock_cat]

    new_cat = MenuCategory(restaurant_id=rest_id, name="Beverages")
    assert await repo.create_category(new_cat) == new_cat

    # Item methods
    mock_item = MagicMock(spec=MenuItem)
    mock_res_item = MagicMock()
    mock_res_item.scalar_one_or_none.return_value = mock_item
    mock_session.execute.return_value = mock_res_item

    item_id = uuid.uuid4()
    assert await repo.get_item_by_id(item_id) == mock_item

    mock_res_list_item = MagicMock()
    mock_res_list_item.scalars.return_value.all.return_value = [mock_item]
    mock_session.execute.return_value = mock_res_list_item
    assert await repo.list_items_by_restaurant(rest_id) == [mock_item]
    assert await repo.list_items_by_category(cat_id) == [mock_item]

    new_item = MenuItem(
        restaurant_id=rest_id,
        category_id=cat_id,
        name="Soda",
        price=Decimal("2.50"),
    )
    assert await repo.create_item(new_item) == new_item


def test_restaurant_catalog_migration_sql_generation(capsys):
    """Verify offline SQL generation for upgrade and downgrade of restaurant catalog."""
    alembic_ini_path = Path(__file__).resolve().parent.parent / "alembic.ini"
    alembic_cfg = Config(str(alembic_ini_path))

    # Test upgrade --sql
    upgrade(alembic_cfg, "head", sql=True)
    out, _ = capsys.readouterr()

    # Enum
    assert "CREATE TYPE restaurant_status AS ENUM" in out

    # Tables
    assert "CREATE TABLE restaurants" in out
    assert "CREATE TABLE menu_categories" in out
    assert "CREATE TABLE menu_items" in out

    # Foreign keys
    assert (
        "CONSTRAINT fk_restaurants_owner_id_users FOREIGN KEY(owner_id) REFERENCES users (id)"
        in out
    )
    assert (
        "CONSTRAINT fk_menu_categories_restaurant_id FOREIGN KEY(restaurant_id) REFERENCES restaurants (id)"
        in out
    )
    assert (
        "CONSTRAINT fk_menu_items_restaurant_id FOREIGN KEY(restaurant_id) REFERENCES restaurants (id)"
        in out
    )
    assert (
        "CONSTRAINT fk_menu_items_category_id_restaurant_id FOREIGN KEY(category_id, restaurant_id) REFERENCES menu_categories (id, restaurant_id)"
        in out
    )

    # Constraints
    assert "CONSTRAINT uq_restaurants_slug UNIQUE (slug)" in out
    assert (
        "CONSTRAINT uq_menu_categories_restaurant_id_name UNIQUE (restaurant_id, name)"
        in out
    )
    assert (
        "CONSTRAINT uq_menu_categories_id_restaurant_id UNIQUE (id, restaurant_id)"
        in out
    )
    assert "CONSTRAINT ck_menu_items_price_non_negative CHECK (price >= 0)" in out

    # Indexes
    assert "CREATE INDEX ix_restaurants_owner_id ON restaurants (owner_id)" in out
    assert "CREATE INDEX ix_restaurants_status ON restaurants (status)" in out
    assert (
        "CREATE INDEX ix_menu_categories_restaurant_id ON menu_categories (restaurant_id)"
        in out
    )
    assert (
        "CREATE INDEX ix_menu_items_restaurant_id ON menu_items (restaurant_id)" in out
    )
    assert "CREATE INDEX ix_menu_items_category_id ON menu_items (category_id)" in out

    # Test downgrade --sql from 0002 to 0001
    downgrade(
        alembic_cfg, "0002_create_restaurant_catalog:0001_create_users_table", sql=True
    )
    out_down, _ = capsys.readouterr()

    assert "DROP INDEX ix_menu_items_category_id" in out_down
    assert "DROP INDEX ix_menu_items_restaurant_id" in out_down
    assert "DROP TABLE menu_items" in out_down
    assert "DROP INDEX ix_menu_categories_restaurant_id" in out_down
    assert "DROP TABLE menu_categories" in out_down
    assert "DROP INDEX ix_restaurants_status" in out_down
    assert "DROP INDEX ix_restaurants_owner_id" in out_down
    assert "DROP TABLE restaurants" in out_down
    assert "DROP TYPE restaurant_status" in out_down
