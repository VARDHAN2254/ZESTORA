# ADR-002: Use Next.js for the Web Applications

- Status: Accepted
- Date: 2026-10-05

## Context

ZESTORA requires multiple web interfaces for customers, restaurants, delivery partners, and administrators.

The frontend needs:

- Server-side rendering where useful
- Client-side interactivity
- Routing
- TypeScript support
- Good performance
- Responsive UI
- Production deployment support

## Decision

ZESTORA will use **Next.js with React and TypeScript** for its web applications.

Tailwind CSS will be used for the styling system.

## Alternatives Considered

### React with a separate frontend router

Provides flexibility but requires additional decisions around routing, rendering, and deployment.

### Other frontend frameworks

Other frameworks are viable, but Next.js provides a strong full-stack web application foundation and fits the project's requirements.

## Consequences

Positive:

- React ecosystem
- File-based routing
- Server and client rendering options
- Strong TypeScript support
- Production-oriented tooling

Negative:

- Additional framework concepts to learn
- Some framework-specific conventions

## Result

Next.js is the standard web application framework for ZESTORA.
