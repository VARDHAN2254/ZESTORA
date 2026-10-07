"""Tests for Payment domain models, state machine, provider abstraction, repository, and migrations."""

import uuid
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import sqlalchemy as sa
from alembic.command import downgrade, upgrade
from alembic.config import Config
from sqlalchemy.dialects import postgresql

from app.catalog import MenuItem  # noqa: F401
from app.core.database import Base
from app.identity import User  # noqa: F401
from app.orders.models import Order
from app.payments import (
    TERMINAL_STATES,
    InvalidPaymentStateTransitionError,
    Payment,
    PaymentEvent,
    PaymentMethod,
    PaymentProvider,
    PaymentRepository,
    PaymentRequest,
    PaymentResponse,
    PaymentStatus,
    WebhookEventResult,
    can_transition,
    transition,
)
from app.restaurants import Restaurant  # noqa: F401


def test_payment_table_metadata():
    """Verify Payment table registration, columns, constraints, and indexes."""
    assert "payments" in Base.metadata.tables
    table = Base.metadata.tables["payments"]

    # Primary key
    assert [col.name for col in table.primary_key.columns] == ["id"]
    assert isinstance(table.c.id.type, sa.Uuid)

    # Columns and nullability
    expected_cols = {
        "id": (False, sa.Uuid),
        "order_id": (False, sa.Uuid),
        "amount": (False, sa.Numeric),
        "currency": (False, sa.String),
        "status": (False, sa.Enum),
        "payment_method": (False, sa.Enum),
        "provider": (True, sa.String),
        "provider_payment_id": (True, sa.String),
        "idempotency_key": (False, sa.String),
        "failure_code": (True, sa.String),
        "failure_message": (True, sa.Text),
        "paid_at": (True, sa.DateTime),
        "created_at": (False, sa.DateTime),
        "updated_at": (False, sa.DateTime),
    }

    for col_name, (nullable, expected_type) in expected_cols.items():
        assert col_name in table.columns, f"Column {col_name} missing from payments"
        col = table.columns[col_name]
        assert col.nullable is nullable
        assert isinstance(col.type, expected_type)

    # Foreign key to orders.id
    fk_targets = [(fk.column.table.name, fk.column.name) for fk in table.foreign_keys]
    assert ("orders", "id") in fk_targets

    # Non-negative check constraint on amount
    check_constraints = [
        c for c in table.constraints if isinstance(c, sa.CheckConstraint)
    ]
    sql_texts = [str(c.sqltext) for c in check_constraints]
    assert any("amount >= 0" in text for text in sql_texts)

    # Unique constraints
    unique_constraints = [
        c for c in table.constraints if isinstance(c, sa.UniqueConstraint)
    ]
    unique_col_sets = [{col.name for col in c.columns} for c in unique_constraints]
    assert {"idempotency_key"} in unique_col_sets
    assert {"provider", "provider_payment_id"} in unique_col_sets

    # Indexes
    index_names = {idx.name: [c.name for c in idx.columns] for idx in table.indexes}
    assert "ix_payments_order_id" in index_names
    assert "ix_payments_status" in index_names
    assert "ix_payments_provider_payment_id" in index_names
    assert "ix_payments_created_at" in index_names


def test_payment_events_table_metadata():
    """Verify PaymentEvent table registration, columns, constraints, and indexes."""
    assert "payment_events" in Base.metadata.tables
    table = Base.metadata.tables["payment_events"]

    # Primary key
    assert [col.name for col in table.primary_key.columns] == ["id"]
    assert isinstance(table.c.id.type, sa.Uuid)

    # Columns and nullability
    expected_cols = {
        "id": (False, sa.Uuid),
        "payment_id": (False, sa.Uuid),
        "provider": (False, sa.String),
        "event_type": (False, sa.String),
        "provider_event_id": (False, sa.String),
        "payload": (False, postgresql.JSONB),
        "processed": (False, sa.Boolean),
        "processed_at": (True, sa.DateTime),
        "created_at": (False, sa.DateTime),
    }

    for col_name, (nullable, expected_type) in expected_cols.items():
        assert col_name in table.columns, (
            f"Column {col_name} missing from payment_events"
        )
        col = table.columns[col_name]
        assert col.nullable is nullable
        assert isinstance(col.type, expected_type)

    # Foreign key to payments.id
    fk_targets = [(fk.column.table.name, fk.column.name) for fk in table.foreign_keys]
    assert ("payments", "id") in fk_targets

    # Unique constraint on (provider, provider_event_id)
    unique_constraints = [
        c for c in table.constraints if isinstance(c, sa.UniqueConstraint)
    ]
    unique_col_sets = [{col.name for col in c.columns} for c in unique_constraints]
    assert {"provider", "provider_event_id"} in unique_col_sets

    # Indexes
    index_names = {idx.name: [c.name for c in idx.columns] for idx in table.indexes}
    assert "ix_payment_events_payment_id" in index_names
    assert "ix_payment_events_provider_event_id" in index_names
    assert "ix_payment_events_created_at" in index_names


def test_payment_model_instantiation_and_defaults():
    """Verify default values and precision preservation on Payment instantiation."""
    order_id = uuid.uuid4()
    payment = Payment(
        order_id=order_id,
        amount="499.50",
        payment_method=PaymentMethod.UPI,
        idempotency_key="idemp_12345",
    )

    assert isinstance(payment.id, uuid.UUID)
    assert payment.order_id == order_id
    assert payment.amount == Decimal("499.50")
    assert payment.currency == "INR"
    assert payment.status == PaymentStatus.PENDING
    assert payment.payment_method == PaymentMethod.UPI
    assert payment.idempotency_key == "idemp_12345"
    assert payment.provider is None
    assert payment.provider_payment_id is None
    assert payment.paid_at is None
    assert isinstance(payment.created_at, datetime)
    assert isinstance(payment.updated_at, datetime)
    assert "Payment" in repr(payment)


def test_payment_event_model_instantiation():
    """Verify PaymentEvent instantiation and attribute assignment."""
    payment_id = uuid.uuid4()
    event = PaymentEvent(
        payment_id=payment_id,
        provider="mock_gateway",
        event_type="payment.captured",
        provider_event_id="evt_98765",
        payload={"id": "evt_98765", "amount": 49950},
    )

    assert isinstance(event.id, uuid.UUID)
    assert event.payment_id == payment_id
    assert event.provider == "mock_gateway"
    assert event.event_type == "payment.captured"
    assert event.provider_event_id == "evt_98765"
    assert event.payload["amount"] == 49950
    assert event.processed is False
    assert event.processed_at is None
    assert isinstance(event.created_at, datetime)
    assert "PaymentEvent" in repr(event)


def test_order_and_payment_relationships():
    """Verify bidirectional relationships between Order, Payment, and PaymentEvent."""
    order_mapper = sa.inspect(Order)
    assert "payments" in order_mapper.relationships
    assert order_mapper.relationships["payments"].target.name == "payments"

    payment_mapper = sa.inspect(Payment)
    assert "order" in payment_mapper.relationships
    assert payment_mapper.relationships["order"].target.name == "orders"
    assert "events" in payment_mapper.relationships
    assert payment_mapper.relationships["events"].target.name == "payment_events"

    event_mapper = sa.inspect(PaymentEvent)
    assert "payment" in event_mapper.relationships
    assert event_mapper.relationships["payment"].target.name == "payments"


def test_payment_state_machine_valid_transitions():
    """Verify all defined valid payment state transitions."""
    valid_pairs = [
        # From PENDING
        (PaymentStatus.PENDING, PaymentStatus.AUTHORIZED),
        (PaymentStatus.PENDING, PaymentStatus.CAPTURED),
        (PaymentStatus.PENDING, PaymentStatus.FAILED),
        (PaymentStatus.PENDING, PaymentStatus.CANCELLED),
        # From AUTHORIZED
        (PaymentStatus.AUTHORIZED, PaymentStatus.CAPTURED),
        (PaymentStatus.AUTHORIZED, PaymentStatus.CANCELLED),
        (PaymentStatus.AUTHORIZED, PaymentStatus.FAILED),
        # From CAPTURED
        (PaymentStatus.CAPTURED, PaymentStatus.REFUNDED),
    ]

    for current, target in valid_pairs:
        assert can_transition(current, target) is True
        assert transition(current, target) == target


def test_payment_state_machine_invalid_transitions():
    """Verify illegal transitions are rejected with InvalidPaymentStateTransitionError."""
    invalid_pairs = [
        (PaymentStatus.REFUNDED, PaymentStatus.CAPTURED),
        (PaymentStatus.FAILED, PaymentStatus.REFUNDED),
        (PaymentStatus.CANCELLED, PaymentStatus.CAPTURED),
        (PaymentStatus.FAILED, PaymentStatus.CAPTURED),
        (PaymentStatus.CANCELLED, PaymentStatus.AUTHORIZED),
        (PaymentStatus.REFUNDED, PaymentStatus.PENDING),
        (PaymentStatus.CAPTURED, PaymentStatus.PENDING),
        (PaymentStatus.AUTHORIZED, PaymentStatus.PENDING),
    ]

    for current, target in invalid_pairs:
        assert can_transition(current, target) is False
        with pytest.raises(InvalidPaymentStateTransitionError) as exc_info:
            transition(current, target)
        assert (
            f"Cannot transition payment from {current.value} to {target.value}"
            in str(exc_info.value)
        )


def test_payment_state_machine_terminal_states():
    """Ensure terminal states permit no transitions."""
    assert TERMINAL_STATES == {
        PaymentStatus.FAILED,
        PaymentStatus.CANCELLED,
        PaymentStatus.REFUNDED,
    }

    for terminal in TERMINAL_STATES:
        for any_target in PaymentStatus:
            assert can_transition(terminal, any_target) is False
            with pytest.raises(InvalidPaymentStateTransitionError):
                transition(terminal, any_target)


@pytest.mark.asyncio
async def test_payment_provider_abstraction_mock():
    """Verify PaymentProvider abstract interface can be cleanly implemented by a mock provider."""

    class MockProvider(PaymentProvider):
        @property
        def provider_name(self) -> str:
            return "mock_gateway"

        async def create_payment(self, request: PaymentRequest) -> PaymentResponse:
            return PaymentResponse(
                provider_payment_id="mock_pay_1",
                status=PaymentStatus.PENDING,
                raw_response={"id": "mock_pay_1"},
            )

        async def authorize(
            self, provider_payment_id: str, amount: Decimal
        ) -> PaymentResponse:
            return PaymentResponse(
                provider_payment_id=provider_payment_id,
                status=PaymentStatus.AUTHORIZED,
            )

        async def capture(
            self, provider_payment_id: str, amount: Decimal
        ) -> PaymentResponse:
            return PaymentResponse(
                provider_payment_id=provider_payment_id,
                status=PaymentStatus.CAPTURED,
            )

        async def cancel(
            self, provider_payment_id: str, reason: str | None = None
        ) -> PaymentResponse:
            return PaymentResponse(
                provider_payment_id=provider_payment_id,
                status=PaymentStatus.CANCELLED,
            )

        async def refund(
            self, provider_payment_id: str, amount: Decimal, reason: str | None = None
        ) -> PaymentResponse:
            return PaymentResponse(
                provider_payment_id=provider_payment_id,
                status=PaymentStatus.REFUNDED,
            )

        async def verify_webhook(
            self, payload: bytes | str, signature: str | None = None
        ) -> WebhookEventResult:
            return WebhookEventResult(
                provider_event_id="evt_123",
                event_type="payment.captured",
                provider_payment_id="mock_pay_1",
                status=PaymentStatus.CAPTURED,
                payload={"event": "payment.captured"},
            )

    provider = MockProvider()
    assert provider.provider_name == "mock_gateway"

    req = PaymentRequest(
        order_id=uuid.uuid4(),
        amount=Decimal("350.00"),
        currency="INR",
        payment_method=PaymentMethod.CARD,
        idempotency_key="idemp_abc",
    )

    created = await provider.create_payment(req)
    assert created.status == PaymentStatus.PENDING
    assert created.provider_payment_id == "mock_pay_1"

    authorized = await provider.authorize("mock_pay_1", Decimal("350.00"))
    assert authorized.status == PaymentStatus.AUTHORIZED

    captured = await provider.capture("mock_pay_1", Decimal("350.00"))
    assert captured.status == PaymentStatus.CAPTURED

    refunded = await provider.refund("mock_pay_1", Decimal("350.00"))
    assert refunded.status == PaymentStatus.REFUNDED

    cancelled = await provider.cancel("mock_pay_1")
    assert cancelled.status == PaymentStatus.CANCELLED

    event = await provider.verify_webhook(b'{"mock": true}')
    assert event.provider_event_id == "evt_123"
    assert event.status == PaymentStatus.CAPTURED


@pytest.mark.asyncio
async def test_payment_repository_methods():
    """Verify PaymentRepository query execution, status updates, and event creation."""
    session = AsyncMock()
    session.add = MagicMock()
    repo = PaymentRepository(session)

    # get_by_id
    mock_payment = MagicMock(spec=Payment)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_payment
    session.execute.return_value = mock_result

    payment_id = uuid.uuid4()
    retrieved = await repo.get_by_id(payment_id)
    assert retrieved is mock_payment

    # get_by_order_id
    mock_result.scalars.return_value.all.return_value = [mock_payment]
    order_id = uuid.uuid4()
    orders_list = await repo.get_by_order_id(order_id)
    assert orders_list == [mock_payment]

    # get_by_idempotency_key
    mock_result.scalar_one_or_none.return_value = mock_payment
    by_key = await repo.get_by_idempotency_key("idemp_1")
    assert by_key is mock_payment

    # get_event_by_provider_event_id
    mock_event = MagicMock(spec=PaymentEvent)
    mock_result.scalar_one_or_none.return_value = mock_event
    event = await repo.get_event_by_provider_event_id("mock", "evt_1")
    assert event is mock_event

    # create payment
    payment_to_create = Payment(
        order_id=order_id,
        amount="100.00",
        payment_method=PaymentMethod.UPI,
        idempotency_key="key_1",
    )
    created = await repo.create(payment_to_create)
    session.add.assert_called_with(payment_to_create)
    session.flush.assert_awaited()
    assert created is payment_to_create

    # update_status to CAPTURED
    updated = await repo.update_status(created, PaymentStatus.CAPTURED)
    assert updated.status == PaymentStatus.CAPTURED
    assert updated.paid_at is not None

    # record_event
    event_to_record = PaymentEvent(
        payment_id=payment_to_create.id,
        provider="mock",
        event_type="payment.captured",
        provider_event_id="evt_rec_1",
        payload={"id": "evt_rec_1"},
    )
    recorded = await repo.record_event(event_to_record)
    session.add.assert_called_with(event_to_record)
    assert recorded is event_to_record


def test_payment_migration_sql_generation(capsys):
    """Verify offline migration SQL generation for 0004_create_payments upgrade and downgrade."""
    api_dir = Path(__file__).resolve().parent.parent
    alembic_ini = api_dir / "alembic.ini"

    alembic_cfg = Config(str(alembic_ini))
    alembic_cfg.set_main_option("script_location", str(api_dir / "migrations"))

    # Test upgrade --sql from 0003 to 0004
    upgrade(alembic_cfg, "0003_create_orders:0004_create_payments", sql=True)
    out, _ = capsys.readouterr()

    # Tables created
    assert "CREATE TABLE payments (" in out
    assert "CREATE TABLE payment_events (" in out

    # Enums created
    assert (
        "CREATE TYPE payment_status AS ENUM ('PENDING', 'AUTHORIZED', 'CAPTURED', 'FAILED', 'CANCELLED', 'REFUNDED')"
        in out
    )
    assert (
        "CREATE TYPE payment_method AS ENUM ('CARD', 'UPI', 'NET_BANKING', 'WALLET', 'CASH_ON_DELIVERY')"
        in out
    )

    # Constraints
    assert (
        "CONSTRAINT fk_payments_order_id_orders FOREIGN KEY(order_id) REFERENCES orders (id) ON DELETE RESTRICT"
        in out
    )
    assert "CONSTRAINT ck_payments_amount_non_negative CHECK (amount >= 0)" in out
    assert "CONSTRAINT uq_payments_idempotency_key UNIQUE (idempotency_key)" in out
    assert (
        "CONSTRAINT uq_payments_provider_provider_payment_id UNIQUE (provider, provider_payment_id)"
        in out
    )
    assert (
        "CONSTRAINT fk_payment_events_payment_id_payments FOREIGN KEY(payment_id) REFERENCES payments (id) ON DELETE RESTRICT"
        in out
    )
    assert (
        "CONSTRAINT uq_payment_events_provider_provider_event_id UNIQUE (provider, provider_event_id)"
        in out
    )

    # Indexes
    assert "CREATE INDEX ix_payments_order_id ON payments (order_id)" in out
    assert "CREATE INDEX ix_payments_status ON payments (status)" in out
    assert (
        "CREATE INDEX ix_payments_provider_payment_id ON payments (provider_payment_id)"
        in out
    )
    assert "CREATE INDEX ix_payments_created_at ON payments (created_at)" in out
    assert (
        "CREATE INDEX ix_payment_events_payment_id ON payment_events (payment_id)"
        in out
    )
    assert (
        "CREATE INDEX ix_payment_events_provider_event_id ON payment_events (provider_event_id)"
        in out
    )
    assert (
        "CREATE INDEX ix_payment_events_created_at ON payment_events (created_at)"
        in out
    )

    # Test downgrade --sql from 0004 to 0003
    downgrade(alembic_cfg, "0004_create_payments:0003_create_orders", sql=True)
    out_down, _ = capsys.readouterr()

    assert "DROP TABLE payment_events" in out_down
    assert "DROP TABLE payments" in out_down
    assert "DROP TYPE payment_method" in out_down
    assert "DROP TYPE payment_status" in out_down
