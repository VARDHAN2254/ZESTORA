"""Tests for Order domain models, state machine, repository, and migrations."""

import uuid
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import sqlalchemy as sa
from alembic.command import downgrade, upgrade
from alembic.config import Config

from app.catalog import MenuItem
from app.core.database import Base
from app.identity import User
from app.orders import (
    TERMINAL_STATES,
    VALID_TRANSITIONS,
    InvalidOrderStateTransitionError,
    Order,
    OrderItem,
    OrderRepository,
    OrderStatus,
    can_transition,
    transition,
)
from app.restaurants import Restaurant


def test_order_table_metadata():
    """Verify Order table registration, columns, constraints, and indexes."""
    assert "orders" in Base.metadata.tables
    table = Base.metadata.tables["orders"]

    # Primary key
    assert [col.name for col in table.primary_key.columns] == ["id"]
    assert isinstance(table.c.id.type, sa.Uuid)

    # Columns and nullability
    expected_cols = {
        "id": (False, sa.Uuid),
        "customer_id": (False, sa.Uuid),
        "restaurant_id": (False, sa.Uuid),
        "status": (False, sa.Enum),
        "subtotal": (False, sa.Numeric),
        "delivery_fee": (False, sa.Numeric),
        "tax": (False, sa.Numeric),
        "discount": (False, sa.Numeric),
        "total": (False, sa.Numeric),
        "currency": (False, sa.String),
        "delivery_address_line1": (False, sa.String),
        "delivery_address_line2": (True, sa.String),
        "delivery_city": (False, sa.String),
        "delivery_state": (False, sa.String),
        "delivery_postal_code": (False, sa.String),
        "delivery_latitude": (True, sa.Numeric),
        "delivery_longitude": (True, sa.Numeric),
        "notes": (True, sa.Text),
        "created_at": (False, sa.DateTime),
        "updated_at": (False, sa.DateTime),
    }

    for col_name, (nullable, expected_type) in expected_cols.items():
        assert col_name in table.columns, f"Column {col_name} missing from orders"
        col = table.columns[col_name]
        assert col.nullable is nullable
        assert isinstance(col.type, expected_type)

    # Foreign keys
    fk_targets = [(fk.column.table.name, fk.column.name) for fk in table.foreign_keys]
    assert ("users", "id") in fk_targets
    assert ("restaurants", "id") in fk_targets

    # Unique constraint on (id, restaurant_id) for composite FK integrity
    unique_constraints = [
        c for c in table.constraints if isinstance(c, sa.UniqueConstraint)
    ]
    assert any(
        {col.name for col in c.columns} == {"id", "restaurant_id"}
        for c in unique_constraints
    )

    # Check constraints on non-negative money
    check_constraints = [
        c for c in table.constraints if isinstance(c, sa.CheckConstraint)
    ]
    sql_texts = [str(c.sqltext) for c in check_constraints]
    assert any("subtotal >= 0" in text for text in sql_texts)
    assert any("delivery_fee >= 0" in text for text in sql_texts)
    assert any("tax >= 0" in text for text in sql_texts)
    assert any("discount >= 0" in text for text in sql_texts)
    assert any("total >= 0" in text for text in sql_texts)

    # Indexes
    index_names = {idx.name: [c.name for c in idx.columns] for idx in table.indexes}
    assert "ix_orders_customer_id" in index_names
    assert "ix_orders_restaurant_id" in index_names
    assert "ix_orders_status" in index_names
    assert "ix_orders_created_at" in index_names


def test_order_item_table_metadata_and_integrity():
    """Verify OrderItem table metadata, check constraints, and composite FK integrity."""
    assert "order_items" in Base.metadata.tables
    table = Base.metadata.tables["order_items"]

    # Primary key
    assert [col.name for col in table.primary_key.columns] == ["id"]
    assert isinstance(table.c.id.type, sa.Uuid)

    # Columns and nullability
    expected_cols = {
        "id": (False, sa.Uuid),
        "order_id": (False, sa.Uuid),
        "restaurant_id": (False, sa.Uuid),
        "menu_item_id": (False, sa.Uuid),
        "quantity": (False, sa.Integer),
        "unit_price": (False, sa.Numeric),
        "line_total": (False, sa.Numeric),
        "item_name": (False, sa.String),
        "item_description": (True, sa.Text),
        "created_at": (False, sa.DateTime),
        "updated_at": (False, sa.DateTime),
    }

    for col_name, (nullable, expected_type) in expected_cols.items():
        assert col_name in table.columns, f"Column {col_name} missing from order_items"
        col = table.columns[col_name]
        assert col.nullable is nullable
        assert isinstance(col.type, expected_type)

    # Check constraints
    check_constraints = [
        c for c in table.constraints if isinstance(c, sa.CheckConstraint)
    ]
    sql_texts = [str(c.sqltext) for c in check_constraints]
    assert any("quantity > 0" in text for text in sql_texts)
    assert any("unit_price >= 0" in text for text in sql_texts)
    assert any("line_total >= 0" in text for text in sql_texts)

    # Composite foreign key constraints enforcing order & menu_item same restaurant
    fk_constraints = [
        c for c in table.constraints if isinstance(c, sa.ForeignKeyConstraint)
    ]

    order_fk = any(
        [col.name for col in c.columns] == ["order_id", "restaurant_id"]
        and [elem.column.name for elem in c.elements] == ["id", "restaurant_id"]
        for c in fk_constraints
    )
    assert order_fk, "Composite FK (order_id, restaurant_id) -> orders missing"

    item_fk = any(
        [col.name for col in c.columns] == ["menu_item_id", "restaurant_id"]
        and [elem.column.name for elem in c.elements] == ["id", "restaurant_id"]
        for c in fk_constraints
    )
    assert item_fk, "Composite FK (menu_item_id, restaurant_id) -> menu_items missing"

    # Indexes
    index_names = {idx.name: [c.name for c in idx.columns] for idx in table.indexes}
    assert "ix_order_items_order_id" in index_names
    assert "ix_order_items_menu_item_id" in index_names


def test_relationships_declarations():
    """Verify declared SQLAlchemy relationships across User, Restaurant, Order, OrderItem."""
    # User -> Orders
    assert hasattr(User, "orders")
    assert User.orders.property.target == Order.__table__

    # Restaurant -> Orders
    assert hasattr(Restaurant, "orders")
    assert Restaurant.orders.property.target == Order.__table__

    # Order -> Customer, Restaurant, Items
    assert hasattr(Order, "customer")
    assert Order.customer.property.target == User.__table__
    assert hasattr(Order, "restaurant")
    assert Order.restaurant.property.target == Restaurant.__table__
    assert hasattr(Order, "items")
    assert Order.items.property.target == OrderItem.__table__

    # OrderItem -> Order, MenuItem
    assert hasattr(OrderItem, "order")
    assert OrderItem.order.property.target == Order.__table__
    assert hasattr(OrderItem, "menu_item")
    assert OrderItem.menu_item.property.target == MenuItem.__table__


def test_order_model_instantiation_and_defaults():
    """Verify in-memory Order and OrderItem instantiation sets defaults correctly."""
    customer_id = uuid.uuid4()
    restaurant_id = uuid.uuid4()
    menu_item_id = uuid.uuid4()

    order = Order(
        customer_id=customer_id,
        restaurant_id=restaurant_id,
        subtotal=Decimal("45.00"),
        delivery_fee=Decimal("5.00"),
        tax=Decimal("4.50"),
        total=Decimal("54.50"),
        delivery_address_line1="456 Oak Avenue",
        delivery_city="Springfield",
        delivery_state="IL",
        delivery_postal_code="62704",
    )
    assert isinstance(order.id, uuid.UUID)
    assert order.status == OrderStatus.PENDING_PAYMENT
    assert order.currency == "INR"
    assert order.subtotal == Decimal("45.00")
    assert order.total == Decimal("54.50")
    assert order.discount == Decimal("0.00")
    assert isinstance(order.created_at, datetime)
    assert isinstance(order.updated_at, datetime)
    assert "54.50 INR" in repr(order)

    item = OrderItem(
        order_id=order.id,
        restaurant_id=restaurant_id,
        menu_item_id=menu_item_id,
        quantity=2,
        unit_price=Decimal("22.50"),
        line_total=Decimal("45.00"),
        item_name="Cheese Pizza",
        item_description="Classic cheese pizza",
    )
    assert isinstance(item.id, uuid.UUID)
    assert item.quantity == 2
    assert item.unit_price == Decimal("22.50")
    assert item.line_total == Decimal("45.00")
    assert item.item_name == "Cheese Pizza"
    assert "Cheese Pizza" in repr(item)


def test_state_machine_valid_transitions():
    """Verify all documented valid order lifecycle transitions."""
    for current_status, next_statuses in VALID_TRANSITIONS.items():
        for next_status in next_statuses:
            assert can_transition(current_status, next_status) is True
            assert transition(current_status, next_status) == next_status


def test_state_machine_invalid_transitions():
    """Verify invalid transitions are rejected and raise InvalidOrderStateTransitionError."""
    # Cannot jump backwards
    assert can_transition(OrderStatus.DELIVERED, OrderStatus.PENDING_PAYMENT) is False
    with pytest.raises(InvalidOrderStateTransitionError) as exc_info:
        transition(OrderStatus.DELIVERED, OrderStatus.PENDING_PAYMENT)
    assert "DELIVERED" in str(exc_info.value)
    assert "PENDING_PAYMENT" in str(exc_info.value)

    # Cannot jump from PENDING_PAYMENT directly to DELIVERED
    assert can_transition(OrderStatus.PENDING_PAYMENT, OrderStatus.DELIVERED) is False
    with pytest.raises(InvalidOrderStateTransitionError):
        transition(OrderStatus.PENDING_PAYMENT, OrderStatus.DELIVERED)

    # Cannot transition out of terminal states
    for terminal in TERMINAL_STATES:
        for any_status in OrderStatus:
            assert can_transition(terminal, any_status) is False
            with pytest.raises(InvalidOrderStateTransitionError):
                transition(terminal, any_status)


@pytest.mark.asyncio
async def test_order_repository_methods():
    """Verify OrderRepository CRUD and status update operations."""
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    repo = OrderRepository(mock_session)

    # get_by_id
    mock_order = MagicMock(spec=Order)
    mock_res_id = MagicMock()
    mock_res_id.scalar_one_or_none.return_value = mock_order
    mock_session.execute.return_value = mock_res_id

    order_id = uuid.uuid4()
    assert await repo.get_by_id(order_id) == mock_order

    # list_by_customer
    mock_res_cust = MagicMock()
    mock_res_cust.scalars.return_value.all.return_value = [mock_order]
    mock_session.execute.return_value = mock_res_cust
    customer_id = uuid.uuid4()
    assert await repo.list_by_customer(customer_id) == [mock_order]

    # list_by_restaurant
    mock_res_rest = MagicMock()
    mock_res_rest.scalars.return_value.all.return_value = [mock_order]
    mock_session.execute.return_value = mock_res_rest
    restaurant_id = uuid.uuid4()
    assert await repo.list_by_restaurant(restaurant_id) == [mock_order]

    # create
    new_order = Order(
        customer_id=customer_id,
        restaurant_id=restaurant_id,
        subtotal=Decimal("20.00"),
        total=Decimal("25.00"),
        delivery_address_line1="123 Street",
        delivery_city="City",
        delivery_state="State",
        delivery_postal_code="12345",
    )
    assert await repo.create(new_order) == new_order
    mock_session.add.assert_called_once_with(new_order)
    mock_session.flush.assert_awaited()

    # update_status valid transition
    updated_order = await repo.update_status(new_order, OrderStatus.CONFIRMED)
    assert updated_order.status == OrderStatus.CONFIRMED

    # update_status invalid transition raises
    with pytest.raises(InvalidOrderStateTransitionError):
        await repo.update_status(new_order, OrderStatus.DELIVERED)


def test_order_migration_sql_generation(capsys):
    """Verify offline SQL generation for upgrade and downgrade of orders foundation."""
    alembic_ini_path = Path(__file__).resolve().parent.parent / "alembic.ini"
    alembic_cfg = Config(str(alembic_ini_path))

    # Test upgrade --sql
    upgrade(alembic_cfg, "head", sql=True)
    out, _ = capsys.readouterr()

    # Enum
    assert "CREATE TYPE order_status AS ENUM" in out

    # Tables
    assert "CREATE TABLE orders" in out
    assert "CREATE TABLE order_items" in out

    # Unique constraint on menu_items for composite FK
    assert (
        "ALTER TABLE menu_items ADD CONSTRAINT uq_menu_items_id_restaurant_id UNIQUE (id, restaurant_id)"
        in out
    )

    # Foreign keys
    assert (
        "CONSTRAINT fk_orders_customer_id_users FOREIGN KEY(customer_id) REFERENCES users (id)"
        in out
    )
    assert (
        "CONSTRAINT fk_orders_restaurant_id_restaurants FOREIGN KEY(restaurant_id) REFERENCES restaurants (id)"
        in out
    )
    assert (
        "CONSTRAINT fk_order_items_order_id_restaurant_id FOREIGN KEY(order_id, restaurant_id) REFERENCES orders (id, restaurant_id)"
        in out
    )
    assert (
        "CONSTRAINT fk_order_items_menu_item_id_restaurant_id FOREIGN KEY(menu_item_id, restaurant_id) REFERENCES menu_items (id, restaurant_id)"
        in out
    )

    # Check constraints
    assert "CONSTRAINT ck_orders_subtotal_non_negative CHECK (subtotal >= 0)" in out
    assert "CONSTRAINT ck_orders_total_non_negative CHECK (total >= 0)" in out
    assert "CONSTRAINT ck_order_items_quantity_positive CHECK (quantity > 0)" in out
    assert (
        "CONSTRAINT ck_order_items_unit_price_non_negative CHECK (unit_price >= 0)"
        in out
    )
    assert (
        "CONSTRAINT ck_order_items_line_total_non_negative CHECK (line_total >= 0)"
        in out
    )

    # Indexes
    assert "CREATE INDEX ix_orders_customer_id ON orders (customer_id)" in out
    assert "CREATE INDEX ix_orders_restaurant_id ON orders (restaurant_id)" in out
    assert "CREATE INDEX ix_orders_status ON orders (status)" in out
    assert "CREATE INDEX ix_orders_created_at ON orders (created_at)" in out
    assert "CREATE INDEX ix_order_items_order_id ON order_items (order_id)" in out
    assert (
        "CREATE INDEX ix_order_items_menu_item_id ON order_items (menu_item_id)" in out
    )

    # Test downgrade --sql from 0003 to 0002
    downgrade(
        alembic_cfg, "0003_create_orders:0002_create_restaurant_catalog", sql=True
    )
    out_down, _ = capsys.readouterr()

    assert "DROP INDEX ix_order_items_menu_item_id" in out_down
    assert "DROP INDEX ix_order_items_order_id" in out_down
    assert "DROP TABLE order_items" in out_down
    assert "DROP INDEX ix_orders_created_at" in out_down
    assert "DROP INDEX ix_orders_status" in out_down
    assert "DROP INDEX ix_orders_restaurant_id" in out_down
    assert "DROP INDEX ix_orders_customer_id" in out_down
    assert "DROP TABLE orders" in out_down
    assert "DROP TYPE order_status" in out_down
    assert (
        "ALTER TABLE menu_items DROP CONSTRAINT uq_menu_items_id_restaurant_id"
        in out_down
    )
