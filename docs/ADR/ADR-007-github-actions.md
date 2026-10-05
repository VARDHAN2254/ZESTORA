# ADR-007: Use GitHub Actions for CI/CD

- Status: Accepted
- Date: 2026-10-05

## Context

ZESTORA requires automated validation and deployment workflows.

The project repository already resides on GitHub, and the engineering workflow uses pull requests.

## Decision

ZESTORA will use **GitHub Actions** for CI/CD.

Initial CI responsibilities will include:

- Dependency installation
- Linting
- Type checking
- Unit tests
- Integration tests
- Security checks
- Application builds

CD will later support:

- Staging deployment
- Smoke tests
- Production promotion
- Deployment verification
- Rollback workflows

## Alternatives Considered

### GitLab CI

A capable alternative, but GitHub Actions integrates directly with the existing GitHub repository workflow.

### Jenkins

Powerful and flexible, but introduces additional infrastructure and operational overhead.

## Consequences

Positive:

- Native GitHub integration
- Pull request checks
- Repository-based workflow configuration
- Large ecosystem of reusable actions

Negative:

- Workflow configuration becomes part of the repository
- CI usage and execution limits must be managed

## Result

GitHub Actions is the standard CI/CD platform for ZESTORA.
