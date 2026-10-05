# ADR-003: Use FastAPI for the Backend API

- Status: Accepted
- Date: 2026-10-05

## Context

ZESTORA requires a backend capable of providing:

- REST APIs
- Validation
- Authentication
- Authorization
- Business logic
- Database access
- Background processing integration
- API documentation

## Decision

ZESTORA will use **Python with FastAPI** for the backend API.

Pydantic will be used for validation and data models.

SQLAlchemy will be used for database access.

Alembic will be used for database migrations.

## Alternatives Considered

### Node.js backend

A Node.js backend would integrate naturally with the TypeScript frontend, but ZESTORA is intentionally using Python for backend engineering and ecosystem breadth.

### Django

Django is mature and powerful, but FastAPI provides a smaller API-focused foundation for the architecture we are building.

## Consequences

Positive:

- Strong API development experience
- Automatic OpenAPI documentation
- Pydantic validation
- Async support
- Clear separation of API and frontend

Negative:

- Requires separate frontend and backend applications
- Python and TypeScript introduce two primary language ecosystems

## Result

FastAPI is the standard backend framework for ZESTORA.
