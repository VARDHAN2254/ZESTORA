# ADR-008: Use Terraform for Infrastructure as Code

- Status: Accepted
- Date: 2026-10-05

## Context

ZESTORA will eventually require repeatable cloud infrastructure.

Manually creating infrastructure makes environments harder to reproduce and audit.

## Decision

ZESTORA will use **Terraform** for Infrastructure as Code.

Infrastructure definitions will be version controlled with the application code.

Terraform will eventually manage areas such as:

- Networking
- Compute
- Load balancing
- Database infrastructure
- Redis
- Object storage
- DNS
- Monitoring
- Secrets integration

## Alternatives Considered

### Manual cloud configuration

Simple initially but difficult to reproduce and audit.

### Provider-specific infrastructure tools

Useful in some ecosystems, but Terraform provides a widely used infrastructure-as-code workflow and supports multiple providers.

## Consequences

Positive:

- Reproducible infrastructure
- Version-controlled infrastructure changes
- Reviewable infrastructure modifications
- Better environment consistency

Negative:

- Additional tooling to learn
- State management is required
- Infrastructure changes require careful review

## Result

Terraform will be introduced during the infrastructure phase and become the primary Infrastructure as Code tool for ZESTORA.
