# ADR-006: Use Server-Sent Events for Initial Real-Time Updates

- Status: Accepted
- Date: 2026-10-05

## Context

ZESTORA requires real-time updates for order state changes.

The initial use cases are primarily server-to-client notifications such as:

- Order accepted
- Order preparing
- Order ready
- Delivery assigned
- Out for delivery
- Delivered

These use cases do not initially require continuous bidirectional communication.

## Decision

ZESTORA will use **Server-Sent Events (SSE)** for the initial real-time order tracking implementation.

## Alternatives Considered

### WebSockets

WebSockets provide bidirectional communication, but that capability is not initially required for the core order tracking workflow.

### Polling

Polling is simple but creates unnecessary requests and slower update behavior.

## Consequences

Positive:

- Simple server-to-client streaming
- Fits order-status updates well
- Lower complexity than a full bidirectional messaging system

Negative:

- Primarily server-to-client communication
- Some future features may require WebSockets

## Future Evolution

WebSockets may be introduced if ZESTORA later requires:

- Bidirectional real-time communication
- Live delivery interaction
- Real-time chat
- High-frequency interactive events

## Result

SSE is the initial real-time transport for ZESTORA.
