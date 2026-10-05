\# ADR-001: Use a Modular Monolith as the Initial Architecture



\- Status: Accepted

\- Date: 2026-10-05

\- Decision Owners: ZESTORA Engineering

\- Related: System Architecture



\## Context



ZESTORA is a production-oriented food delivery platform being developed as a learning project.



The platform will contain multiple business domains, including:



\- Identity and authentication

\- Restaurants

\- Catalog and menus

\- Cart

\- Orders

\- Payments

\- Delivery

\- Notifications

\- Reviews

\- Administration

\- Auditing



A major architectural decision is whether to begin with:



1\. A monolith

2\. A modular monolith

3\. Microservices



Starting directly with microservices would introduce additional complexity such as:



\- Service-to-service communication

\- Distributed transactions

\- Independent deployments

\- Service discovery

\- Distributed debugging

\- Multiple CI/CD pipelines

\- Network failure handling

\- Increased infrastructure requirements



For the initial stage of ZESTORA, this complexity would distract from understanding the core product and engineering lifecycle.



\## Decision



ZESTORA will begin as a \*\*modular monolith\*\*.



The application will be deployed initially as a small number of independently runnable components, while the backend codebase remains organized into strongly separated business modules.



Initial business modules will include:



\- Identity

\- Users

\- Restaurants

\- Catalog

\- Cart

\- Orders

\- Payments

\- Delivery

\- Notifications

\- Reviews

\- Administration

\- Audit



Each module should have:



\- Clear responsibilities

\- Defined interfaces

\- Minimal coupling

\- Its own domain logic

\- Its own tests

\- Clear ownership of data and operations



The architecture will avoid unnecessary direct dependencies between unrelated modules.



\## Example Structure



```text

backend/

|

+-- app/

|   |

|   +-- core/

|   +-- identity/

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



\## Why This Decision



A modular monolith provides:



\- Simpler development

\- Easier local setup

\- Fewer operational dependencies

\- Faster iteration

\- Easier debugging

\- Strong domain boundaries

\- A realistic path toward service extraction



It also allows ZESTORA to demonstrate production engineering practices without prematurely introducing distributed-system complexity.



\## Alternatives Considered



\### Traditional Monolith



A traditional monolith would keep most business logic together without strong internal boundaries.



Advantages:



\- Very simple initially

\- Low infrastructure complexity



Disadvantages:



\- Easier to create tightly coupled code

\- Poorer separation of business domains

\- Harder to evolve safely



Decision:



\*\*Rejected.\*\*



ZESTORA is intentionally being built to teach architectural boundaries.



\### Microservices



Each major domain could be deployed as a separate service.



Advantages:



\- Independent deployment

\- Independent scaling

\- Strong service boundaries

\- Technology flexibility



Disadvantages:



\- Higher infrastructure complexity

\- Distributed transactions

\- Network failures

\- More operational overhead

\- More difficult debugging

\- More complicated local development



Decision:



\*\*Deferred.\*\*



Microservices may be introduced later where there is a genuine architectural reason.



\## Future Extraction Criteria



A module may be extracted into a separate service when one or more of the following become true:



\- Independent scaling is required

\- Independent deployment is valuable

\- The module has a clear service boundary

\- Failure isolation is important

\- The module has substantially different runtime requirements

\- The operational complexity is justified



Possible future extraction candidates include:



\- Payment Service

\- Notification Service

\- Search Service

\- Delivery Service

\- Analytics Service



\## Consequences



\### Positive Consequences



\- Easier development

\- Easier testing

\- Easier deployment

\- Lower initial infrastructure complexity

\- Clearer code organization

\- Good foundation for future service extraction



\### Negative Consequences



\- Modules still share the same application deployment

\- Incorrect module boundaries could create coupling

\- Independent scaling of individual domains is limited initially

\- Future extraction may require additional work



\## Enforcement Guidelines



New functionality should be placed inside the appropriate domain module.



Developers should avoid:



\- Putting business logic into unrelated modules

\- Directly accessing another module's internal implementation

\- Creating unnecessary global state

\- Creating cross-module database dependencies without justification



Architecture changes that significantly affect module boundaries should be documented through an Architecture Decision Record.



\## Result



ZESTORA will use a \*\*modular monolith as the initial architecture\*\*.



The system will remain intentionally simple at the deployment level while maintaining strong internal boundaries that allow future evolution.

