# @zestora/web

Next.js frontend application for the ZESTORA food delivery platform.

## Architecture

Built according to [ADR-002: Next.js](../../docs/ADR/ADR-002-nextjs.md) using:
- **Framework:** Next.js (App Router)
- **Language:** TypeScript
- **Styling:** Tailwind CSS

## Directory Structure

```text
apps/web/
├── app/          # App Router routes and layouts
├── components/   # Shared UI components
├── features/     # Feature-specific modules (customer, restaurant, delivery, admin)
├── lib/          # Utility functions and helpers
├── hooks/        # Custom React hooks
├── services/     # API client and backend service integrations
├── styles/       # Global styles and themes
├── public/       # Static assets
└── tests/        # Frontend unit and component tests
```

## Local Development

```bash
# Install dependencies
npm install

# Start development server
npm run dev

# Run type check
npm run typecheck

# Run production build
npm run build
```
