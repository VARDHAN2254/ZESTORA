# ZESTORA Worker

Celery background worker service for the ZESTORA food delivery platform.

## Architecture

Built according to [ADR-005: Redis](../../docs/ADR/ADR-005-redis.md) and system architecture for asynchronous operations:
- **Engine:** Celery
- **Broker/Backend:** Redis (configured via `CELERY_BROKER_URL`, defaults to in-memory for local isolated testing)

## Directory Structure

```text
apps/worker/
├── tasks/
│   ├── notifications/  # Email, SMS, Push notification dispatch
│   ├── payments/       # Payment reconciliation and status webhooks
│   ├── orders/         # Timeout checks, auto-cancellation
│   ├── cleanup/        # Ephemeral data cleanup and garbage collection
│   └── scheduled/      # Periodic recurring maintenance jobs
├── tests/              # Worker task unit tests
├── worker.py           # Celery application entrypoint
├── pyproject.toml      # Project manifest and dependencies
└── README.md
```

## Local Development

```bash
# Install dependencies
uv pip install -e ".[dev]"
# Or: pip install -e ".[dev]"

# Start Celery worker locally
celery -A worker.celery worker --loglevel=info

# Run worker tests
pytest
```
