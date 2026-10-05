\# ZESTORA — Repository Structure



\## 1. Repository Overview



ZESTORA will use a monorepo-style repository containing the web application, backend services, infrastructure, tests, documentation, and CI/CD configuration.



The repository is organized so that application code, infrastructure, and operational tooling remain clearly separated.



\## 2. Root Structure



```text

ZESTORA/

│

├── .github/

│   └── workflows/

│

├── apps/

│   ├── web/

│   ├── api/

│   └── worker/

│

├── packages/

│   ├── ui/

│   ├── config/

│   └── tooling/

│

├── infrastructure/

│   ├── docker/

│   └── terraform/

│

├── tests/

│   ├── e2e/

│   ├── performance/

│   └── security/

│

├── docs/

│   ├── ADR/

│   ├── PROJECT\_FOUNDATION.md

│   ├── REQUIREMENTS.md

│   ├── ARCHITECTURE.md

│   └── REPOSITORY\_STRUCTURE.md

│

├── scripts/

│

├── .env.example

├── .gitignore

├── README.md

└── LICENSE

```



\## 3. GitHub Configuration



```text

.github/

└── workflows/

&#x20;   ├── ci.yml

&#x20;   ├── security.yml

&#x20;   ├── e2e.yml

&#x20;   └── cd.yml

```



The workflows will eventually handle:



\- Continuous Integration

\- Security scanning

\- End-to-end testing

\- Deployment



CI/CD files will be version controlled.



\## 4. Web Application



```text

apps/web/

│

├── app/

├── components/

├── features/

├── lib/

├── hooks/

├── services/

├── styles/

├── public/

├── tests/

├── package.json

├── next.config.ts

├── tsconfig.json

└── README.md

```



The web application will contain the interfaces for:



\- Customers

\- Restaurants

\- Delivery partners

\- Administrators



Role-based routing and authorization will determine which interface a user can access.



\### Web responsibilities



\- UI rendering

\- Navigation

\- Forms

\- Client-side state

\- API communication

\- Authentication state

\- Real-time event consumption

\- Accessibility

\- Responsive design



Business-critical rules remain on the backend.



\## 5. Backend API



```text

apps/api/

│

├── app/

│   ├── core/

│   ├── identity/

│   ├── users/

│   ├── restaurants/

│   ├── catalog/

│   ├── cart/

│   ├── orders/

│   ├── payments/

│   ├── delivery/

│   ├── notifications/

│   ├── reviews/

│   ├── admin/

│   └── audit/

│

├── migrations/

├── tests/

├── pyproject.toml

└── README.md

```



The API is responsible for:



\- Authentication

\- Authorization

\- Validation

\- Business logic

\- Database operations

\- Payment coordination

\- Order processing

\- API endpoints

\- Audit logging



\## 6. Background Worker



```text

apps/worker/

│

├── tasks/

│   ├── notifications/

│   ├── payments/

│   ├── orders/

│   ├── cleanup/

│   └── scheduled/

│

├── worker.py

├── pyproject.toml

└── README.md

```



The worker handles asynchronous operations such as:



\- Notifications

\- Payment reconciliation

\- Retryable external operations

\- Scheduled jobs

\- Cleanup

\- Background processing



The worker must not duplicate business rules that belong to the API domain modules.



\## 7. Shared Packages



\### UI Package



```text

packages/ui/

├── components/

├── layouts/

├── forms/

├── feedback/

├── navigation/

└── package.json

```



Contains reusable frontend components.



Examples:



\- Buttons

\- Inputs

\- Modals

\- Tables

\- Cards

\- Alerts

\- Navigation components



\### Config Package



```text

packages/config/

├── eslint/

├── typescript/

└── prettier/

```



Contains shared development configuration.



\### Tooling Package



```text

packages/tooling/

├── scripts/

└── package.json

```



Contains reusable development tooling.



\## 8. Infrastructure



```text

infrastructure/

│

├── docker/

│   ├── web/

│   ├── api/

│   ├── worker/

│   └── compose/

│

└── terraform/

&#x20;   ├── modules/

&#x20;   └── environments/

&#x20;       ├── staging/

&#x20;       └── production/

```



\### Docker



Used to create reproducible application environments.



\### Terraform



Used to define infrastructure as code.



Infrastructure must remain separate from application source code.



\## 9. Testing



```text

tests/

├── e2e/

├── performance/

└── security/

```



\### End-to-End Tests



Test complete user journeys.



Examples:



\- Registration

\- Restaurant discovery

\- Checkout

\- Order tracking



\### Performance Tests



Measure:



\- API latency

\- Throughput

\- Concurrent users

\- Database performance



\### Security Tests



Eventually cover:



\- Authentication

\- Authorization

\- Input validation

\- Rate limiting

\- Dependency vulnerabilities

\- Secret exposure



Unit and integration tests may remain close to the applications they test.



\## 10. Documentation



```text

docs/

│

├── ADR/

├── PROJECT\_FOUNDATION.md

├── REQUIREMENTS.md

├── ARCHITECTURE.md

└── REPOSITORY\_STRUCTURE.md

```



Documentation responsibilities:



\### PROJECT\_FOUNDATION.md



Defines the overall project purpose and engineering principles.



\### REQUIREMENTS.md



Defines functional and non-functional requirements.



\### ARCHITECTURE.md



Defines the system architecture and major technical components.



\### ADR/



Records important architectural decisions.



\### REPOSITORY\_STRUCTURE.md



Explains where project components belong.



\## 11. Scripts



```text

scripts/

├── development/

├── database/

├── testing/

├── deployment/

└── security/

```



Examples:



\- Local development setup

\- Database migrations

\- Seed data

\- Test execution

\- Deployment helpers

\- Security checks



Scripts should be deterministic and documented.



\## 12. Environment Configuration



The repository will contain:



```text

.env.example

```



It will document required variables without exposing secrets.



Actual environment files such as:



```text

.env

.env.local

.env.production

```



must never be committed.



\## 13. Dependency Management



Each runtime ecosystem will manage its own dependencies.



Frontend:



```text

apps/web/package.json

```



Backend:



```text

apps/api/pyproject.toml

```



Worker:



```text

apps/worker/pyproject.toml

```



Dependencies must be pinned or constrained appropriately and regularly audited.



\## 14. Build Artifacts



Generated files must not normally be committed.



Examples:



```text

node\_modules/

.next/

dist/

coverage/

\_\_pycache\_\_/

.pytest\_cache/

```



These will be excluded through `.gitignore`.



\## 15. Ownership Boundaries



\### Web owns



\- User interface

\- Client interactions

\- Presentation

\- UI state



\### API owns



\- Business rules

\- Authorization

\- Data validation

\- Transactions

\- Persistent state



\### Worker owns



\- Asynchronous processing

\- Scheduled tasks

\- Retryable background work



\### Infrastructure owns



\- Runtime environments

\- Networking

\- Cloud resources

\- Deployment infrastructure



\### Documentation owns



\- Architecture decisions

\- Requirements

\- Operational knowledge



\## 16. Architectural Rules



The following rules apply to the repository:



1\. Business logic must not be duplicated across unrelated layers.

2\. Secrets must never be committed.

3\. Infrastructure changes must be version controlled.

4\. Database schema changes must use migrations.

5\. Application modules must maintain clear boundaries.

6\. Shared packages should only contain genuinely reusable functionality.

7\. Generated artifacts should not be committed unless explicitly required.

8\. Production configuration must remain separate from source code.

9\. New major architectural patterns require documentation.

10\. Major architectural decisions should have an ADR.



\## 17. Future Expansion



The repository structure is intentionally designed to allow future expansion.



Possible future additions:



```text

apps/

├── admin/

├── restaurant/

└── delivery/



services/

├── search/

├── analytics/

└── notifications/

```



These should only be introduced when there is a justified architectural need.



The initial implementation will avoid unnecessary service fragmentation.



\## 18. Current Status



Completed:



\- Project foundation

\- Requirements

\- System architecture

\- Architecture decision records



Current:



\- Repository structure



Next:



\- Frontend architecture

\- Backend architecture

\- Database architecture

\- API contract design

\- Security architecture

\- CI pipeline

\- Development environment

\- Application skeleton

