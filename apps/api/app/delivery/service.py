"""Delivery partner service coordinating delivery lifecycle and assignment rules."""

import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.delivery.enums import (
    DeliveryPartnerAvailability,
    DeliveryPartnerStatus,
    DeliveryStatus,
)
from app.delivery.exceptions import (
    DeliveryAlreadyAssignedError,
    DeliveryNotFoundError,
    DeliveryOrderConflictError,
    DeliveryPartnerNotEligibleError,
    DeliveryPartnerNotFoundError,
    InvalidDeliveryTransitionError,
    OrderNotReadyForPickupError,
    UnauthorizedDeliveryAccessError,
)
from app.delivery.models import Delivery, DeliveryPartner
from app.delivery.repository import DeliveryRepository
from app.delivery.schemas import DeliveryPartnerProfileCreate
from app.delivery.state_machine import InvalidDeliveryStateTransitionError
from app.identity.enums import UserRole
from app.identity.models import User
from app.orders.enums import OrderStatus
from app.orders.repository import OrderRepository
from app.orders.state_machine import InvalidOrderStateTransitionError


class DeliveryPartnerService:
    """Service layer enforcing delivery partner policies, assignment rules,
    and synchronized Delivery/Order state transitions.
    """

    def __init__(
        self,
        session: AsyncSession,
        delivery_repo: DeliveryRepository | None = None,
        order_repo: OrderRepository | None = None,
    ) -> None:
        self.session = session
        self.delivery_repo = delivery_repo or DeliveryRepository(session)
        self.order_repo = order_repo or OrderRepository(session)

    def _verify_delivery_partner_role(self, user: User) -> None:
        """Verify that the user possesses the DELIVERY_PARTNER role."""
        if user.role != UserRole.DELIVERY_PARTNER:
            raise UnauthorizedDeliveryAccessError(
                "Only users with DELIVERY_PARTNER role can access delivery operations."
            )

    async def get_partner_profile(self, user: User) -> DeliveryPartner:
        """Retrieve the delivery partner profile for the authenticated user.

        Raises:
            UnauthorizedDeliveryAccessError: If user does not have DELIVERY_PARTNER role.
            DeliveryPartnerNotFoundError: If no profile exists for the user.
        """
        self._verify_delivery_partner_role(user)
        partner = await self.delivery_repo.get_partner_by_user_id(user.id)
        if partner is None:
            raise DeliveryPartnerNotFoundError("Delivery partner profile not found.")
        return partner

    async def create_partner_profile(
        self, user: User, data: DeliveryPartnerProfileCreate
    ) -> DeliveryPartner:
        """Create or onboard a delivery partner profile for the authenticated user.

        Raises:
            UnauthorizedDeliveryAccessError: If user does not have DELIVERY_PARTNER role.
            DeliveryPartnerNotEligibleError: If a profile already exists.
        """
        self._verify_delivery_partner_role(user)
        existing = await self.delivery_repo.get_partner_by_user_id(user.id)
        if existing is not None:
            raise DeliveryPartnerNotEligibleError(
                "Delivery partner profile already exists for this account."
            )

        partner = DeliveryPartner(
            user_id=user.id,
            status=DeliveryPartnerStatus.ACTIVE,
            availability=data.availability,
            vehicle_type=data.vehicle_type,
            vehicle_identifier=data.vehicle_identifier,
        )
        return await self.delivery_repo.create_partner(partner)

    async def update_availability(
        self, user: User, availability: DeliveryPartnerAvailability
    ) -> DeliveryPartner:
        """Update the availability status of the authenticated delivery partner.

        Raises:
            UnauthorizedDeliveryAccessError: If role mismatch.
            DeliveryPartnerNotFoundError: If profile not found.
            DeliveryPartnerNotEligibleError: If partner is suspended or inactive.
        """
        partner = await self.get_partner_profile(user)
        if partner.status != DeliveryPartnerStatus.ACTIVE:
            raise DeliveryPartnerNotEligibleError(
                f"Cannot update availability: account is {partner.status.value.lower()}."
            )
        return await self.delivery_repo.update_partner_availability(
            partner, availability
        )

    async def list_available_deliveries(
        self, user: User, skip: int = 0, limit: int = 20
    ) -> tuple[Sequence[Delivery], int]:
        """List eligible, unassigned deliveries where the order is ready for pickup.

        Raises:
            UnauthorizedDeliveryAccessError: If role mismatch.
            DeliveryPartnerNotFoundError: If profile not found.
        """
        await self.get_partner_profile(user)
        deliveries = await self.delivery_repo.list_available_deliveries(
            skip=skip, limit=limit
        )
        total = await self.delivery_repo.count_available_deliveries()
        return deliveries, total

    async def get_current_delivery(self, user: User) -> Delivery | None:
        """Retrieve the partner's active delivery assignment, if one exists.

        Raises:
            UnauthorizedDeliveryAccessError: If role mismatch.
            DeliveryPartnerNotFoundError: If profile not found.
        """
        partner = await self.get_partner_profile(user)
        return await self.delivery_repo.get_active_delivery_for_partner(partner.id)

    async def list_partner_deliveries(
        self,
        user: User,
        skip: int = 0,
        limit: int = 20,
        status: DeliveryStatus | None = None,
    ) -> tuple[Sequence[Delivery], int]:
        """List delivery history assigned to the authenticated delivery partner.

        Raises:
            UnauthorizedDeliveryAccessError: If role mismatch.
            DeliveryPartnerNotFoundError: If profile not found.
        """
        partner = await self.get_partner_profile(user)
        deliveries = await self.delivery_repo.list_by_partner_paginated(
            partner_id=partner.id,
            skip=skip,
            limit=limit,
            status=status,
        )
        total = await self.delivery_repo.count_by_partner(
            partner_id=partner.id,
            status=status,
        )
        return deliveries, total

    async def get_delivery_details(
        self, user: User, delivery_id: uuid.UUID
    ) -> Delivery:
        """Retrieve details of a delivery assigned to the authenticated partner.

        Raises:
            UnauthorizedDeliveryAccessError: If role mismatch or assigned to another partner.
            DeliveryNotFoundError: If delivery does not exist.
        """
        partner = await self.get_partner_profile(user)
        delivery = await self.delivery_repo.get_by_id_with_details(delivery_id)
        if delivery is None:
            raise DeliveryNotFoundError(f"Delivery '{delivery_id}' not found.")

        if delivery.delivery_partner_id != partner.id:
            raise UnauthorizedDeliveryAccessError(
                "You do not have permission to access this delivery's details."
            )
        return delivery

    async def accept_delivery(self, user: User, delivery_id: uuid.UUID) -> Delivery:
        """Accept an available delivery job atomically under row-level lock.

        Guarantees:
        - Partner must be ACTIVE and AVAILABLE.
        - Partner cannot take multiple active deliveries simultaneously.
        - Row-level lock (FOR UPDATE) prevents concurrent double-assignment.
        - Order must be legitimately in READY_FOR_PICKUP status.
        - Second or losing concurrent requests receive a predictable conflict error.

        Raises:
            UnauthorizedDeliveryAccessError: If role mismatch.
            DeliveryPartnerNotFoundError: If partner profile not found.
            DeliveryPartnerNotEligibleError: If partner is inactive, unavailable, or has active job.
            DeliveryNotFoundError: If delivery does not exist.
            DeliveryAlreadyAssignedError: If already claimed by another partner.
            InvalidDeliveryTransitionError: If order is not ready for pickup.
        """
        partner = await self.get_partner_profile(user)

        if partner.status != DeliveryPartnerStatus.ACTIVE:
            raise DeliveryPartnerNotEligibleError(
                f"Cannot accept deliveries: account is {partner.status.value.lower()}."
            )

        if partner.availability != DeliveryPartnerAvailability.AVAILABLE:
            raise DeliveryPartnerNotEligibleError(
                "You must set your availability to AVAILABLE before accepting deliveries."
            )

        # Enforce single active delivery per partner
        active_delivery = await self.delivery_repo.get_active_delivery_for_partner(
            partner.id
        )
        if active_delivery is not None:
            raise DeliveryPartnerNotEligibleError(
                "You already have an active delivery assignment in progress."
            )

        # Acquire exclusive row-level lock
        delivery = await self.delivery_repo.get_by_id_with_details(
            delivery_id, for_update=True
        )
        if delivery is None:
            raise DeliveryNotFoundError(f"Delivery '{delivery_id}' not found.")

        # Check eligibility under lock
        if (
            delivery.status != DeliveryStatus.UNASSIGNED
            or delivery.delivery_partner_id is not None
        ):
            raise DeliveryAlreadyAssignedError(
                "This delivery has already been assigned or is no longer available."
            )

        if (
            delivery.order is None
            or delivery.order.status != OrderStatus.READY_FOR_PICKUP
        ):
            raise InvalidDeliveryTransitionError(
                "Order is not ready for delivery pickup."
            )

        try:
            delivery = await self.delivery_repo.assign_partner_atomic(
                delivery,
                partner.id,
                expected_status=DeliveryStatus.UNASSIGNED,
            )
        except InvalidDeliveryStateTransitionError as exc:
            raise DeliveryAlreadyAssignedError(str(exc)) from exc

        return delivery

    async def pickup_delivery(self, user: User, delivery_id: uuid.UUID) -> Delivery:
        """Mark an order as picked up by the assigned delivery partner.

        Coordinates Delivery (ASSIGNED -> PICKED_UP) and Order (READY_FOR_PICKUP -> PICKED_UP)
        transitions atomically under row lock.

        Raises:
            UnauthorizedDeliveryAccessError: If not assigned to caller.
            DeliveryNotFoundError: If delivery not found.
            InvalidDeliveryTransitionError: If delivery status is not ASSIGNED.
            OrderNotReadyForPickupError: If order status is not READY_FOR_PICKUP.
        """
        partner = await self.get_partner_profile(user)

        delivery = await self.delivery_repo.get_by_id_with_details(
            delivery_id, for_update=True
        )
        if delivery is None:
            raise DeliveryNotFoundError(f"Delivery '{delivery_id}' not found.")

        if delivery.delivery_partner_id != partner.id:
            raise UnauthorizedDeliveryAccessError(
                "You are not the delivery partner assigned to this delivery."
            )

        if delivery.status != DeliveryStatus.ASSIGNED:
            raise InvalidDeliveryTransitionError(
                f"Cannot pick up delivery in '{delivery.status.value}' status. "
                "Expected status: 'ASSIGNED'."
            )

        if (
            delivery.order is None
            or delivery.order.status != OrderStatus.READY_FOR_PICKUP
        ):
            order_stat = delivery.order.status.value if delivery.order else "None"
            raise OrderNotReadyForPickupError(
                f"Cannot pick up order in '{order_stat}' status. "
                "Expected status: 'READY_FOR_PICKUP'."
            )

        try:
            delivery = await self.delivery_repo.update_status(
                delivery,
                DeliveryStatus.PICKED_UP,
                expected_status=DeliveryStatus.ASSIGNED,
            )
            await self.order_repo.update_status(
                delivery.order,
                OrderStatus.PICKED_UP,
                expected_status=OrderStatus.READY_FOR_PICKUP,
            )
        except (
            InvalidDeliveryStateTransitionError,
            InvalidOrderStateTransitionError,
        ) as exc:
            raise InvalidDeliveryTransitionError(str(exc)) from exc

        return delivery

    async def start_delivery(self, user: User, delivery_id: uuid.UUID) -> Delivery:
        """Mark an order as out for delivery by the assigned delivery partner.

        Coordinates Delivery (PICKED_UP -> OUT_FOR_DELIVERY) and
        Order (PICKED_UP -> OUT_FOR_DELIVERY) transitions atomically.

        Raises:
            UnauthorizedDeliveryAccessError: If not assigned to caller.
            DeliveryNotFoundError: If delivery not found.
            InvalidDeliveryTransitionError: If status is not PICKED_UP.
            DeliveryOrderConflictError: If order status does not match.
        """
        partner = await self.get_partner_profile(user)

        delivery = await self.delivery_repo.get_by_id_with_details(
            delivery_id, for_update=True
        )
        if delivery is None:
            raise DeliveryNotFoundError(f"Delivery '{delivery_id}' not found.")

        if delivery.delivery_partner_id != partner.id:
            raise UnauthorizedDeliveryAccessError(
                "You are not the delivery partner assigned to this delivery."
            )

        if delivery.status != DeliveryStatus.PICKED_UP:
            raise InvalidDeliveryTransitionError(
                f"Cannot transition delivery from '{delivery.status.value}' to 'OUT_FOR_DELIVERY'. "
                "Expected status: 'PICKED_UP'."
            )

        if delivery.order is None or delivery.order.status != OrderStatus.PICKED_UP:
            order_stat = delivery.order.status.value if delivery.order else "None"
            raise DeliveryOrderConflictError(
                f"Order status '{order_stat}' does not match delivery status 'PICKED_UP'."
            )

        try:
            delivery = await self.delivery_repo.update_status(
                delivery,
                DeliveryStatus.OUT_FOR_DELIVERY,
                expected_status=DeliveryStatus.PICKED_UP,
            )
            await self.order_repo.update_status(
                delivery.order,
                OrderStatus.OUT_FOR_DELIVERY,
                expected_status=OrderStatus.PICKED_UP,
            )
        except (
            InvalidDeliveryStateTransitionError,
            InvalidOrderStateTransitionError,
        ) as exc:
            raise InvalidDeliveryTransitionError(str(exc)) from exc

        return delivery

    async def complete_delivery(self, user: User, delivery_id: uuid.UUID) -> Delivery:
        """Mark an order as delivered by the assigned delivery partner.

        Coordinates Delivery (OUT_FOR_DELIVERY -> DELIVERED) and
        Order (OUT_FOR_DELIVERY -> DELIVERED) transitions atomically.

        Raises:
            UnauthorizedDeliveryAccessError: If not assigned to caller.
            DeliveryNotFoundError: If delivery not found.
            InvalidDeliveryTransitionError: If status is not OUT_FOR_DELIVERY.
            DeliveryOrderConflictError: If order status does not match.
        """
        partner = await self.get_partner_profile(user)

        delivery = await self.delivery_repo.get_by_id_with_details(
            delivery_id, for_update=True
        )
        if delivery is None:
            raise DeliveryNotFoundError(f"Delivery '{delivery_id}' not found.")

        if delivery.delivery_partner_id != partner.id:
            raise UnauthorizedDeliveryAccessError(
                "You are not the delivery partner assigned to this delivery."
            )

        if delivery.status != DeliveryStatus.OUT_FOR_DELIVERY:
            raise InvalidDeliveryTransitionError(
                f"Cannot complete delivery in '{delivery.status.value}' status. "
                "Expected status: 'OUT_FOR_DELIVERY'."
            )

        if (
            delivery.order is None
            or delivery.order.status != OrderStatus.OUT_FOR_DELIVERY
        ):
            order_stat = delivery.order.status.value if delivery.order else "None"
            raise DeliveryOrderConflictError(
                f"Order status '{order_stat}' does not match delivery status 'OUT_FOR_DELIVERY'."
            )

        try:
            delivery = await self.delivery_repo.update_status(
                delivery,
                DeliveryStatus.DELIVERED,
                expected_status=DeliveryStatus.OUT_FOR_DELIVERY,
            )
            await self.order_repo.update_status(
                delivery.order,
                OrderStatus.DELIVERED,
                expected_status=OrderStatus.OUT_FOR_DELIVERY,
            )
        except (
            InvalidDeliveryStateTransitionError,
            InvalidOrderStateTransitionError,
        ) as exc:
            raise InvalidDeliveryTransitionError(str(exc)) from exc

        return delivery
