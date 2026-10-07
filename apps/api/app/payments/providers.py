"""Provider-neutral payment abstraction interface and request/response contracts."""

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.payments.enums import PaymentMethod, PaymentStatus


@dataclass(frozen=True)
class PaymentRequest:
    """Request payload for initiating a payment through a provider."""

    order_id: uuid.UUID
    amount: Decimal
    currency: str
    payment_method: PaymentMethod
    idempotency_key: str
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class PaymentResponse:
    """Standardized result returned by a payment provider operation."""

    provider_payment_id: str
    status: PaymentStatus
    raw_response: dict[str, Any] | None = None
    failure_code: str | None = None
    failure_message: str | None = None


@dataclass(frozen=True)
class WebhookEventResult:
    """Standardized representation of a verified provider webhook event."""

    provider_event_id: str
    event_type: str
    provider_payment_id: str | None
    status: PaymentStatus | None
    payload: dict[str, Any]


class PaymentProvider(ABC):
    """Abstract base class defining the provider-neutral payment gateway interface."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the unique identifier string for this provider (e.g. 'mock', 'razorpay')."""
        ...

    @abstractmethod
    async def create_payment(self, request: PaymentRequest) -> PaymentResponse:
        """Create or initiate a payment transaction with the external provider."""
        ...

    @abstractmethod
    async def authorize(
        self, provider_payment_id: str, amount: Decimal
    ) -> PaymentResponse:
        """Authorize a pending payment hold."""
        ...

    @abstractmethod
    async def capture(
        self, provider_payment_id: str, amount: Decimal
    ) -> PaymentResponse:
        """Capture an authorized payment settlement."""
        ...

    @abstractmethod
    async def cancel(
        self, provider_payment_id: str, reason: str | None = None
    ) -> PaymentResponse:
        """Cancel/void an authorization or pending payment attempt."""
        ...

    @abstractmethod
    async def refund(
        self, provider_payment_id: str, amount: Decimal, reason: str | None = None
    ) -> PaymentResponse:
        """Refund an already captured payment."""
        ...

    @abstractmethod
    async def verify_webhook(
        self, payload: bytes | str, signature: str | None = None
    ) -> WebhookEventResult:
        """Verify webhook signature and parse raw payload into standard event representation."""
        ...
