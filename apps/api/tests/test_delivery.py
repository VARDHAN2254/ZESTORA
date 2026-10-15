"""Tests for Delivery domain models, state machine, repository, and migrations."""

import uuid
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import sqlalchemy as sa
from alembic.command import downgrade, upgrade
from alembic.config import Config

from app.catalog import MenuItem  # noqa: F401
from app.core.database import Base
from app.delivery import (
    TERMINAL_STATES,
    Delivery,
    DeliveryPartner,
    DeliveryPartnerAvailability,
    DeliveryPartnerStatus,
    DeliveryRepository,
    DeliveryStatus,
    InvalidDeliveryStateTransitionError,
    VehicleType,
    can_transition,
    transition,
)
from app.identity import User
from app.orders.models import Order
from app.payments.models import Payment  # noqa: F401
from app.restaurants import Restaurant  # noqa: F401


def test_delivery_partner_table_metadata():
    """Verify DeliveryPartner table registration, columns, constraints, and indexes."""
    assert "delivery_partners" in Base.metadata.tables
    table = Base.metadata.tables["delivery_partners"]

    # Primary key
    assert [col.name for col in table.primary_key.columns] == ["id"]
    assert isinstance(table.c.id.type, sa.Uuid)

    # Columns and nullability
    expected_cols = {
        "id": (False, sa.Uuid),
        "user_id": (False, sa.Uuid),
        "status": (False, sa.Enum),
        "availability": (False, sa.Enum),
        "vehicle_type": (True, sa.Enum),
        "vehicle_identifier": (True, sa.String),
        "created_at": (False, sa.DateTime),
        "updated_at": (False, sa.DateTime),
    }

    for col_name, (nullable, expected_type) in expected_cols.items():
        assert col_name in table.columns, (
            f"Column {col_name} missing from delivery_partners"
        )
        col = table.columns[col_name]
        assert col.nullable is nullable
        assert isinstance(col.type, expected_type)

    # Foreign key to users.id
    fk_targets = [(fk.column.table.name, fk.column.name) for fk in table.foreign_keys]
    assert ("users", "id") in fk_targets

    # Unique constraint on user_id
    unique_constraints = [
        c for c in table.constraints if isinstance(c, sa.UniqueConstraint)
    ]
    unique_col_sets = [{col.name for col in c.columns} for c in unique_constraints]
    assert {"user_id"} in unique_col_sets

    # Indexes
    index_names = {idx.name: [c.name for c in idx.columns] for idx in table.indexes}
    assert "ix_delivery_partners_status" in index_names
    assert "ix_delivery_partners_availability" in index_names


def test_deliveries_table_metadata():
    """Verify Delivery table registration, columns, constraints, and indexes."""
    assert "deliveries" in Base.metadata.tables
    table = Base.metadata.tables["deliveries"]

    # Primary key
    assert [col.name for col in table.primary_key.columns] == ["id"]
    assert isinstance(table.c.id.type, sa.Uuid)

    # Columns and nullability
    expected_cols = {
        "id": (False, sa.Uuid),
        "order_id": (False, sa.Uuid),
        "delivery_partner_id": (True, sa.Uuid),
        "status": (False, sa.Enum),
        "assigned_at": (True, sa.DateTime),
        "picked_up_at": (True, sa.DateTime),
        "delivered_at": (True, sa.DateTime),
        "cancelled_at": (True, sa.DateTime),
        "created_at": (False, sa.DateTime),
        "updated_at": (False, sa.DateTime),
    }

    for col_name, (nullable, expected_type) in expected_cols.items():
        assert col_name in table.columns, f"Column {col_name} missing from deliveries"
        col = table.columns[col_name]
        assert col.nullable is nullable
        assert isinstance(col.type, expected_type)

    # Foreign keys
    fk_targets = [(fk.column.table.name, fk.column.name) for fk in table.foreign_keys]
    assert ("orders", "id") in fk_targets
    assert ("delivery_partners", "id") in fk_targets

    # Unique constraint on order_id (one delivery per order)
    unique_constraints = [
        c for c in table.constraints if isinstance(c, sa.UniqueConstraint)
    ]
    unique_col_sets = [{col.name for col in c.columns} for c in unique_constraints]
    assert {"order_id"} in unique_col_sets

    # Indexes
    index_names = {idx.name: [c.name for c in idx.columns] for idx in table.indexes}
    assert "ix_deliveries_delivery_partner_id" in index_names
    assert "ix_deliveries_status" in index_names
    assert "ix_deliveries_created_at" in index_names


def test_delivery_partner_model_instantiation():
    """Verify default values and attribute assignments on DeliveryPartner."""
    user_id = uuid.uuid4()
    partner = DeliveryPartner(
        user_id=user_id,
        vehicle_type=VehicleType.MOTORCYCLE,
        vehicle_identifier="DL-01-AB-1234",
    )

    assert isinstance(partner.id, uuid.UUID)
    assert partner.user_id == user_id
    assert partner.status == DeliveryPartnerStatus.ACTIVE
    assert partner.availability == DeliveryPartnerAvailability.UNAVAILABLE
    assert partner.vehicle_type == VehicleType.MOTORCYCLE
    assert partner.vehicle_identifier == "DL-01-AB-1234"
    assert isinstance(partner.created_at, datetime)
    assert isinstance(partner.updated_at, datetime)
    assert "DeliveryPartner" in repr(partner)


def test_delivery_model_instantiation():
    """Verify default values and attribute assignments on Delivery."""
    order_id = uuid.uuid4()
    delivery = Delivery(order_id=order_id)

    assert isinstance(delivery.id, uuid.UUID)
    assert delivery.order_id == order_id
    assert delivery.delivery_partner_id is None
    assert delivery.status == DeliveryStatus.UNASSIGNED
    assert delivery.assigned_at is None
    assert delivery.picked_up_at is None
    assert delivery.delivered_at is None
    assert delivery.cancelled_at is None
    assert isinstance(delivery.created_at, datetime)
    assert isinstance(delivery.updated_at, datetime)
    assert "Delivery" in repr(delivery)


def test_delivery_domain_relationships():
    """Verify relationships between User, DeliveryPartner, Delivery, and Order."""
    user_mapper = sa.inspect(User)
    assert "delivery_partner" in user_mapper.relationships
    assert (
        user_mapper.relationships["delivery_partner"].target.name == "delivery_partners"
    )
    assert user_mapper.relationships["delivery_partner"].uselist is False

    partner_mapper = sa.inspect(DeliveryPartner)
    assert "user" in partner_mapper.relationships
    assert partner_mapper.relationships["user"].target.name == "users"
    assert "deliveries" in partner_mapper.relationships
    assert partner_mapper.relationships["deliveries"].target.name == "deliveries"

    delivery_mapper = sa.inspect(Delivery)
    assert "order" in delivery_mapper.relationships
    assert delivery_mapper.relationships["order"].target.name == "orders"
    assert "delivery_partner" in delivery_mapper.relationships
    assert (
        delivery_mapper.relationships["delivery_partner"].target.name
        == "delivery_partners"
    )

    order_mapper = sa.inspect(Order)
    assert "delivery" in order_mapper.relationships
    assert order_mapper.relationships["delivery"].target.name == "deliveries"
    assert order_mapper.relationships["delivery"].uselist is False


def test_delivery_state_machine_valid_transitions():
    """Verify all valid delivery state transitions."""
    valid_pairs = [
        # From UNASSIGNED
        (DeliveryStatus.UNASSIGNED, DeliveryStatus.ASSIGNED),
        (DeliveryStatus.UNASSIGNED, DeliveryStatus.CANCELLED),
        (DeliveryStatus.UNASSIGNED, DeliveryStatus.FAILED),
        # From ASSIGNED
        (DeliveryStatus.ASSIGNED, DeliveryStatus.PICKED_UP),
        (DeliveryStatus.ASSIGNED, DeliveryStatus.UNASSIGNED),
        (DeliveryStatus.ASSIGNED, DeliveryStatus.CANCELLED),
        (DeliveryStatus.ASSIGNED, DeliveryStatus.FAILED),
        # From PICKED_UP
        (DeliveryStatus.PICKED_UP, DeliveryStatus.OUT_FOR_DELIVERY),
        (DeliveryStatus.PICKED_UP, DeliveryStatus.CANCELLED),
        (DeliveryStatus.PICKED_UP, DeliveryStatus.FAILED),
        # From OUT_FOR_DELIVERY
        (DeliveryStatus.OUT_FOR_DELIVERY, DeliveryStatus.DELIVERED),
        (DeliveryStatus.OUT_FOR_DELIVERY, DeliveryStatus.CANCELLED),
        (DeliveryStatus.OUT_FOR_DELIVERY, DeliveryStatus.FAILED),
    ]

    for current, target in valid_pairs:
        assert can_transition(current, target) is True
        assert transition(current, target) == target


def test_delivery_state_machine_invalid_transitions():
    """Verify illegal transitions are rejected with InvalidDeliveryStateTransitionError."""
    invalid_pairs = [
        (DeliveryStatus.DELIVERED, DeliveryStatus.ASSIGNED),
        (DeliveryStatus.CANCELLED, DeliveryStatus.OUT_FOR_DELIVERY),
        (DeliveryStatus.FAILED, DeliveryStatus.PICKED_UP),
        (DeliveryStatus.UNASSIGNED, DeliveryStatus.DELIVERED),
        (DeliveryStatus.UNASSIGNED, DeliveryStatus.OUT_FOR_DELIVERY),
        (DeliveryStatus.PICKED_UP, DeliveryStatus.ASSIGNED),
        (DeliveryStatus.DELIVERED, DeliveryStatus.UNASSIGNED),
    ]

    for current, target in invalid_pairs:
        assert can_transition(current, target) is False
        with pytest.raises(InvalidDeliveryStateTransitionError) as exc_info:
            transition(current, target)
        assert (
            f"Cannot transition delivery from {current.value} to {target.value}"
            in str(exc_info.value)
        )


def test_delivery_state_machine_terminal_states():
    """Ensure terminal states permit no transitions."""
    assert TERMINAL_STATES == {
        DeliveryStatus.DELIVERED,
        DeliveryStatus.CANCELLED,
        DeliveryStatus.FAILED,
    }

    for terminal in TERMINAL_STATES:
        for any_target in DeliveryStatus:
            assert can_transition(terminal, any_target) is False
            with pytest.raises(InvalidDeliveryStateTransitionError):
                transition(terminal, any_target)


@pytest.mark.asyncio
async def test_delivery_repository_methods():
    """Verify DeliveryRepository operations for partners and deliveries."""
    session = AsyncMock()
    session.add = MagicMock()
    repo = DeliveryRepository(session)

    # get_by_id
    mock_delivery = MagicMock(spec=Delivery)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_delivery
    session.execute.return_value = mock_result

    delivery_id = uuid.uuid4()
    assert await repo.get_by_id(delivery_id) is mock_delivery

    # get_by_order_id
    order_id = uuid.uuid4()
    assert await repo.get_by_order_id(order_id) is mock_delivery

    # get_by_partner_id
    mock_result.scalars.return_value.all.return_value = [mock_delivery]
    partner_id = uuid.uuid4()
    assert await repo.get_by_partner_id(partner_id) == [mock_delivery]

    # get_partner_by_id
    mock_partner = MagicMock(spec=DeliveryPartner)
    mock_result.scalar_one_or_none.return_value = mock_partner
    assert await repo.get_partner_by_id(partner_id) is mock_partner

    # get_partner_by_user_id
    user_id = uuid.uuid4()
    assert await repo.get_partner_by_user_id(user_id) is mock_partner

    # list_available_partners
    mock_result.scalars.return_value.all.return_value = [mock_partner]
    assert await repo.list_available_partners() == [mock_partner]

    # create_partner
    partner_to_create = DeliveryPartner(user_id=user_id)
    created_partner = await repo.create_partner(partner_to_create)
    session.add.assert_called_with(partner_to_create)
    session.flush.assert_awaited()
    assert created_partner is partner_to_create

    # create delivery
    delivery_to_create = Delivery(order_id=order_id)
    created_delivery = await repo.create(delivery_to_create)
    session.add.assert_called_with(delivery_to_create)
    session.flush.assert_awaited()
    assert created_delivery is delivery_to_create

    # assign_partner
    assigned_delivery = await repo.assign_partner(created_delivery, partner_id)
    assert assigned_delivery.status == DeliveryStatus.ASSIGNED
    assert assigned_delivery.delivery_partner_id == partner_id
    assert assigned_delivery.assigned_at is not None

    # update_status to PICKED_UP
    picked_up_delivery = await repo.update_status(
        assigned_delivery, DeliveryStatus.PICKED_UP
    )
    assert picked_up_delivery.status == DeliveryStatus.PICKED_UP
    assert picked_up_delivery.picked_up_at is not None

    # update_status to OUT_FOR_DELIVERY then DELIVERED
    await repo.update_status(picked_up_delivery, DeliveryStatus.OUT_FOR_DELIVERY)
    delivered = await repo.update_status(picked_up_delivery, DeliveryStatus.DELIVERED)
    assert delivered.status == DeliveryStatus.DELIVERED
    assert delivered.delivered_at is not None


def test_delivery_migration_sql_generation(capsys):
    """Verify offline migration SQL generation for 0005_create_delivery upgrade and downgrade."""
    api_dir = Path(__file__).resolve().parent.parent
    alembic_ini = api_dir / "alembic.ini"

    alembic_cfg = Config(str(alembic_ini))
    alembic_cfg.set_main_option("script_location", str(api_dir / "migrations"))

    # Test upgrade --sql from 0004 to 0005
    upgrade(alembic_cfg, "0004_create_payments:0005_create_delivery", sql=True)
    out, _ = capsys.readouterr()

    # Tables created
    assert "CREATE TABLE delivery_partners (" in out
    assert "CREATE TABLE deliveries (" in out

    # Enums created
    assert (
        "CREATE TYPE delivery_partner_status AS ENUM ('ACTIVE', 'INACTIVE', 'SUSPENDED')"
        in out
    )
    assert (
        "CREATE TYPE delivery_partner_availability AS ENUM ('AVAILABLE', 'UNAVAILABLE')"
        in out
    )
    assert (
        "CREATE TYPE vehicle_type AS ENUM ('BIKE', 'SCOOTER', 'MOTORCYCLE', 'BICYCLE', 'CAR', 'OTHER')"
        in out
    )
    assert (
        "CREATE TYPE delivery_status AS ENUM ('UNASSIGNED', 'ASSIGNED', 'PICKED_UP', 'OUT_FOR_DELIVERY', 'DELIVERED', 'CANCELLED', 'FAILED')"
        in out
    )

    # Foreign keys and unique constraints
    assert (
        "CONSTRAINT fk_delivery_partners_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE RESTRICT"
        in out
    )
    assert "CONSTRAINT uq_delivery_partners_user_id UNIQUE (user_id)" in out
    assert (
        "CONSTRAINT fk_deliveries_order_id_orders FOREIGN KEY(order_id) REFERENCES orders (id) ON DELETE RESTRICT"
        in out
    )
    assert (
        "CONSTRAINT fk_deliveries_delivery_partner_id_delivery_partners FOREIGN KEY(delivery_partner_id) REFERENCES delivery_partners (id) ON DELETE RESTRICT"
        in out
    )
    assert "CONSTRAINT uq_deliveries_order_id UNIQUE (order_id)" in out

    # Indexes
    assert (
        "CREATE INDEX ix_delivery_partners_status ON delivery_partners (status)" in out
    )
    assert (
        "CREATE INDEX ix_delivery_partners_availability ON delivery_partners (availability)"
        in out
    )
    assert (
        "CREATE INDEX ix_deliveries_delivery_partner_id ON deliveries (delivery_partner_id)"
        in out
    )
    assert "CREATE INDEX ix_deliveries_status ON deliveries (status)" in out
    assert "CREATE INDEX ix_deliveries_created_at ON deliveries (created_at)" in out

    # Test downgrade --sql from 0005 to 0004
    downgrade(alembic_cfg, "0005_create_delivery:0004_create_payments", sql=True)
    out_down, _ = capsys.readouterr()

    assert "DROP TABLE deliveries" in out_down
    assert "DROP TABLE delivery_partners" in out_down
    assert "DROP TYPE delivery_status" in out_down
    assert "DROP TYPE vehicle_type" in out_down
    assert "DROP TYPE delivery_partner_availability" in out_down
    assert "DROP TYPE delivery_partner_status" in out_down
