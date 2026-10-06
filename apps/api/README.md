# ZESTORA API

FastAPI backend service for the ZESTORA food delivery platform.

## Architecture

Built according to [ADR-003: FastAPI](../../docs/ADR/ADR-003-fastapi.md) as a modular monolith adhering to [ADR-001](../../docs/ADR/ADR-001-modular-monolith.md).

## Modular Domain Structure

```text
apps/api/
├── app/
│   ├── core/           # Configuration, security utilities, database setup
│   ├── identity/       # Authentication, credentials, tokens
│   ├── users/          # User profiles, customer details
│   ├── restaurants/    # Restaurant profiles and management
│   ├── catalog/        # Menus, categories, items
│   ├── cart/           # Shopping cart management
│   ├── orders/         # Order state machine and lifecycle
│   ├── payments/       # Payment integration and processing
│   ├── delivery/       # Partner assignment and delivery tracking
│   ├── notifications/  # Notification dispatch
│   ├── reviews/        # Ratings and reviews
│   ├── admin/          # Admin backoffice endpoints
│   └── audit/          # System audit trail
├── migrations/         # Alembic database migrations
├── tests/              # Automated unit and integration tests
├── pyproject.toml      # Dependency and project manifest
└── README.md
```

## Local Development

```bash
# Using uv or pip
uv pip install -e ".[dev]"
# Or: pip install -e ".[dev]"

# Run FastAPI development server
uvicorn app.main:app --reload --port 8000

# Run automated tests
pytest
```
