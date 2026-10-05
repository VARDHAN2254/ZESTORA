# ZESTORA — System Architecture

## 1. Architecture Overview

ZESTORA will be built as a production-oriented food delivery platform.

The initial architecture will use a modular monolith rather than immediately adopting microservices.

This provides:

- Clear separation of responsibilities
- Easier local development
- Simpler deployment
- Strong module boundaries
- Realistic production practices
- A future path toward service extraction

The system will consist of:

- Customer web application
- Restaurant dashboard
- Delivery dashboard
- Admin dashboard
- Backend API
- Background workers
- PostgreSQL
- Redis
- Object storage
- External service integrations

## 2. High-Level Architecture

```text
                         INTERNET
                            |
                         DNS / CDN
                            |
                           WAF
                            |
                     Load Balancer
                            |
              +-------------+-------------+
              |                           |
       Web Application               API Server
              |                           |
              |                  +--------+--------+
              |                  |        |        |
              |             PostgreSQL  Redis  Object Storage
              |                  |
              |              Job Queue
              |                  |
              |               Workers
              |
              +-------- Real-Time Events
```

## 3. Applications

### 3.1 Customer Application

Customers can:

- Discover restaurants
- Search for food
- Browse menus
- Manage carts
- Checkout
- Make payments
- Track orders
- View order history
- Review orders
- Manage profiles and addresses

### 3.2 Restaurant Dashboard

Restaurants can:

- Manage restaurant information
- Manage menus
- Manage food items
- Update availability
- Receive orders
- Accept or reject orders
- Update preparation status
- Mark orders ready

### 3.3 Delivery Dashboard

Delivery partners can:

- Manage availability
- Receive delivery assignments
- Accept assignments
- View pickup information
- Update delivery status
- Complete deliveries
- View delivery history

### 3.4 Admin Dashboard

Administrators can:

- Manage users
- Manage restaurants
- Manage delivery partners
- Manage orders
- Manage payments
- Manage coupons
- View audit logs
- Manage platform configuration
- Monitor platform activity

## 4. Technology Stack

### Frontend

- Next.js
- React
- TypeScript
- Tailwind CSS

### Backend

- Python
- FastAPI
- Pydantic
- SQLAlchemy
- Alembic

### Database

- PostgreSQL

### Cache and Coordination

- Redis

### Background Jobs

- Celery
- Redis as the initial broker/backend

### Real-Time Communication

- Server-Sent Events (SSE)

### Authentication

- Secure session/token-based authentication
- Password hashing
- Role-Based Access Control

### Payments

- Provider-independent payment abstraction

### Object Storage

- S3-compatible object storage

### Testing

- Pytest
- Playwright
- Frontend unit and integration testing tools

### Version Control

- Git
- GitHub

### CI/CD

- GitHub Actions

### Containers

- Docker

### Infrastructure as Code

- Terraform

### Observability

- Structured logging
- Metrics
- Error tracking
- Distributed tracing where appropriate

## 5. Backend Architecture

The backend will use a modular monolith.

```text
backend/
|
+-- app/
|   |
|   +-- core/
|   +-- auth/
|   +-- users/
|   +-- restaurants/
|   +-- catalog/
|   +-- cart/
|   +-- orders/
|   +-- payments/
|   +-- delivery/
|   +-- notifications/
|   +-- reviews/
|   +-- admin/
|   +-- audit/
|
+-- workers/
+-- tests/
+-- migrations/
```

Each module should have clearly defined responsibilities.

## 6. Core Modules

### Identity

Responsible for:

- Registration
- Login
- Logout
- Password management
- Sessions
- Roles
- Permissions

### Restaurants

Responsible for:

- Restaurant profile
- Operating hours
- Availability
- Restaurant settings

### Catalog

Responsible for:

- Categories
- Menu items
- Prices
- Item availability

### Cart

Responsible for:

- Cart creation
- Item addition and removal
- Quantity changes
- Cart validation

### Orders

Responsible for:

- Order creation
- Order state
- Order totals
- Order history
- Order cancellation

### Payments

Responsible for:

- Payment creation
- Payment verification
- Webhooks
- Refunds
- Reconciliation

### Delivery

Responsible for:

- Delivery assignments
- Delivery state
- Delivery partner workflows

### Notifications

Responsible for:

- Email
- Push notifications
- In-app notifications

### Reviews

Responsible for:

- Ratings
- Reviews
- Review moderation

### Admin

Responsible for:

- Platform administration
- Configuration
- Account management

### Audit

Responsible for:

- Administrative audit events
- Security-relevant events
- Financially significant actions

## 7. Database Architecture

PostgreSQL will be the primary source of transactional truth.

Major tables and domains:

```text
users
roles
user_roles
restaurants
restaurant_users
addresses
menu_categories
menu_items
carts
cart_items
orders
order_items
payments
payment_events
deliveries
delivery_events
coupons
reviews
notifications
audit_logs
```

Database rules:

- Foreign keys must be used where appropriate.
- Unique constraints must protect unique business data.
- Check constraints should protect valid states.
- Transactions must protect critical operations.
- Indexes should be added based on query patterns.
- Schema changes must use migrations.
- Application code must not directly modify production schemas.

## 8. Order Lifecycle

Orders will use an explicit state machine.

Example:

```text
PENDING_PAYMENT
       |
       v
CONFIRMED
       |
       v
ACCEPTED
       |
       v
PREPARING
       |
       v
READY_FOR_PICKUP
       |
       v
PICKED_UP
       |
       v
OUT_FOR_DELIVERY
       |
       v
DELIVERED
```

Possible terminal states:

```text
CANCELLED
FAILED
```

Invalid state transitions must be rejected by the backend.

## 9. Payment Architecture

Payment processing will be isolated behind an abstraction.

```text
Customer
   |
Checkout
   |
Order
   |
Payment Service
   |
Payment Provider
   |
Webhook
   |
Webhook Verification
   |
Payment State
   |
Order State
```

Requirements:

- Server-side verification
- Webhook verification
- Idempotency
- Duplicate-event protection
- Refund handling
- Reconciliation
- Payment audit records

The frontend must never be treated as the authoritative source of payment status.

## 10. Background Processing

Long-running operations will be moved to workers.

```text
API
 |
 +--> PostgreSQL
 |
 +--> Redis / Queue
          |
          v
       Celery
          |
          v
       Worker
```

Background tasks may include:

- Email sending
- Notifications
- Payment reconciliation
- Retryable API calls
- Scheduled cleanup
- Data processing

Workers must support:

- Retries
- Timeouts
- Failure handling
- Idempotency
- Observability

## 11. Real-Time Architecture

SSE will initially be used for real-time order updates.

```text
Restaurant
    |
    v
Backend
    |
    v
Event
    |
    v
SSE Connection
    |
    v
Customer Browser
```

Examples:

- Order accepted
- Order preparing
- Order ready
- Delivery assigned
- Out for delivery
- Delivered

WebSockets can be introduced later if bidirectional communication becomes necessary.

## 12. Authentication and Authorization

Authentication answers:

> Who is the user?

Authorization answers:

> What may this user do?

Roles:

```text
CUSTOMER
RESTAURANT
DELIVERY_PARTNER
ADMIN
```

Authorization will be enforced server-side.

Resource ownership will also be checked.

Example:

```text
Restaurant A user
    |
    X
Restaurant B order

Restaurant A user
    |
    v
Restaurant A order
```

## 13. API Architecture

The API will be versioned.

Example:

```text
/api/v1/auth
/api/v1/users
/api/v1/restaurants
/api/v1/catalog
/api/v1/cart
/api/v1/orders
/api/v1/payments
/api/v1/deliveries
/api/v1/reviews
/api/v1/admin
```

API requirements:

- Input validation
- Authentication
- Authorization
- Pagination
- Filtering
- Consistent error responses
- Rate limiting
- Request IDs
- Structured logging

## 14. Caching

Redis may be used for:

- Frequently accessed data
- Rate limiting
- Temporary state
- Queue infrastructure
- Distributed coordination

Redis must not become the permanent source of truth for transactional records.

## 15. Object Storage

Object storage will be used for:

- Restaurant images
- Food images
- User profile images
- Other uploaded assets

Architecture:

```text
Browser
   |
   v
Upload mechanism
   |
   v
Object Storage
   |
   v
CDN
   |
   v
Browser
```

Application servers should not permanently store uploaded files.

## 16. Environments

ZESTORA will have:

```text
Development
    |
    v
Staging
    |
    v
Production
```

### Development

Local development and feature work.

### Staging

Integration testing, deployment testing, and release validation.

### Production

Real production workload.

Each environment must have separate configuration and secrets.

## 17. Configuration and Secrets

Sensitive configuration must never be committed to Git.

Examples:

```text
DATABASE_URL
REDIS_URL
JWT_SECRET
PAYMENT_SECRET
STORAGE_CREDENTIALS
```

The project will use:

```text
.env.example
```

for documenting required configuration without exposing secrets.

Production secrets will eventually be managed through a dedicated secret-management system.

## 18. Git Workflow

```text
feature/*
    |
    v
develop
    |
    v
Pull Request
    |
    v
CI
    |
    v
Review
    |
    v
Release PR
    |
    v
main
```

Branches:

```text
main
develop
feature/*
fix/*
docs/*
chore/*
```

`main` is protected.

## 19. CI Pipeline

GitHub Actions will perform CI.

```text
Pull Request
     |
     v
Checkout
     |
     v
Install Dependencies
     |
     +---- Lint
     |
     +---- Type Check
     |
     +---- Unit Tests
     |
     +---- Integration Tests
     |
     +---- Security Checks
     |
     +---- Build
     |
     v
CI Result
```

Eventually, `main` will require CI checks to pass before merging.

## 20. CD Pipeline

Deployment pipeline:

```text
Merge
  |
  v
Build Artifact
  |
  v
Deploy Staging
  |
  v
Smoke Tests
  |
  v
Approval / Promotion
  |
  v
Production
  |
  v
Health Checks
```

Production deployment must support rollback.

## 21. Container Architecture

Application components will be containerized.

Initial containers:

```text
web
api
worker
```

Supporting infrastructure:

```text
PostgreSQL
Redis
Object Storage
```

Containers must be:

- Reproducible
- Minimal
- Secure
- Configurable
- Vulnerability scanned

## 22. Infrastructure

Infrastructure will eventually include:

```text
DNS
CDN
WAF
Load Balancer
Compute
PostgreSQL
Redis
Object Storage
Secrets
Monitoring
```

Infrastructure should be reproducible.

## 23. Infrastructure as Code

Terraform will eventually manage infrastructure.

Example:

```text
terraform/
|
+-- modules/
|
+-- environments/
|   |
|   +-- staging/
|   +-- production/
|
+-- main configuration
```

Infrastructure changes will be version controlled.

## 24. Security Architecture

Security controls include:

- HTTPS
- Secure authentication
- Password hashing
- Authorization
- Input validation
- Rate limiting
- CORS
- Security headers
- Secret management
- Dependency scanning
- Secret scanning
- Container scanning
- Audit logging
- Least privilege
- Secure error handling

Security checks will eventually be part of CI.

## 25. Observability

The platform will provide:

### Logs

- Structured logs
- Request IDs
- Errors
- Audit events

### Metrics

- Request rate
- Error rate
- Latency
- Database performance
- Queue depth
- Worker activity

### Tracing

Distributed tracing will be introduced when useful.

### Alerts

Alerts will cover important production failures.

## 26. Reliability

Critical components should implement:

- Timeouts
- Retries
- Idempotency
- Health checks
- Graceful failure
- Transaction boundaries
- Rollback procedures

External services must not cause indefinite blocking.

## 27. Backup and Disaster Recovery

Eventually ZESTORA will support:

- Automated database backups
- Backup retention
- Restore testing
- Recovery procedures
- Deployment rollback
- Disaster recovery documentation

Recovery objectives will be defined during infrastructure planning.

## 28. Scaling

The application should support horizontal scaling.

```text
          Load Balancer
          /     |     \
         /      |      \
      API-1   API-2   API-3
        |        |       |
        +--------+-------+
                 |
             PostgreSQL
                 |
               Redis
```

The application layer should remain stateless wherever practical.

## 29. Architectural Evolution

ZESTORA will begin as a modular monolith.

Microservices will not be introduced simply to make the architecture complex.

Potential future services:

```text
Payment Service
Notification Service
Search Service
Delivery Service
Analytics Service
```

A module should only become a separate service when there is a real reason.

## 30. Architecture Decision Records

Major architectural decisions will be documented in:

```text
docs/ADR/
```

Each ADR will contain:

- Context
- Decision
- Alternatives
- Consequences

Examples:

```text
ADR-001-modular-monolith.md
ADR-002-nextjs.md
ADR-003-fastapi.md
ADR-004-postgresql.md
ADR-005-redis.md
ADR-006-sse.md
ADR-007-github-actions.md
ADR-008-terraform.md
```

## 31. Current Status

Completed:

- Project foundation
- Requirements

Current:

- System architecture

Next:

- Architecture Decision Records
- Repository structure
- Frontend architecture
- Backend architecture
- Database architecture
- CI architecture
- Security architecture
- Deployment architecture