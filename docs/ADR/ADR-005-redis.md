# ADR-005: Use Redis for Caching and Coordination

- Status: Accepted
- Date: 2026-10-05

## Context

ZESTORA needs fast temporary data and coordination mechanisms for:

- Caching
- Rate limiting
- Background job infrastructure
- Short-lived state
- Distributed coordination

## Decision

ZESTORA will use **Redis** for ephemeral and high-speed data operations.

Redis will not replace PostgreSQL as the source of transactional truth.

## Initial Uses

- Cache
- Rate limiting
- Job queue infrastructure
- Temporary state
- Distributed coordination where required

## Alternatives Considered

### In-memory application caching

Simple but not suitable when multiple application instances need shared state.

### Database-only caching

Would increase database load and does not provide the same purpose-built capabilities.

## Consequences

Positive:

- Fast access
- Shared cache
- Useful queue infrastructure
- Supports horizontal application scaling

Negative:

- Adds another infrastructure dependency
- Requires eviction and failure-handling strategies

## Result

Redis will be introduced only where its capabilities provide a measurable benefit.
