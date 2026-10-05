# ADR-004: Use PostgreSQL as the Primary Database

- Status: Accepted
- Date: 2026-10-05

## Context

ZESTORA contains strongly relational data:

- Users
- Restaurants
- Menus
- Orders
- Payments
- Deliveries
- Coupons
- Reviews
- Audit records

The platform also requires transactions, constraints, indexing, and reliable data integrity.

## Decision

ZESTORA will use **PostgreSQL** as its primary transactional database.

PostgreSQL will be the authoritative source of persistent business data.

## Alternatives Considered

### MySQL

A capable relational database, but PostgreSQL provides a strong feature set and is the preferred database for this project.

### MongoDB

A document database could simplify some data models, but the core ZESTORA domain is highly relational and transaction-oriented.

### SQLite

Useful for local prototypes, but not appropriate as the primary production database for this architecture.

## Consequences

Positive:

- Strong transactional guarantees
- Rich constraints
- Excellent relational modeling
- Mature indexing and query capabilities
- Good production ecosystem

Negative:

- More database design work than a simple document store
- Requires proper migration and operational management

## Result

PostgreSQL is the authoritative transactional datastore for ZESTORA.
