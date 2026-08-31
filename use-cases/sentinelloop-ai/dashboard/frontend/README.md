# SentinelLoop dashboard frontend

React + Vite operations UI. Styling is CSS custom properties (no Tailwind).
The dashboard talks to `dashboard/api.py` later; this build uses local mock
data and does not import agent internals.

## Design system first

Tokens, type, and primitives live in `design-system/`. Rules:
`documentation/design-rules.md`. Catalog: `/design-system`.

## Scripts

```bash
cd use-cases/sentinelloop-ai/dashboard/frontend
npm install
npm run dev      # http://localhost:5173
npm run build
```

## Routes

- `/` Dashboard
- `/incidents` Active incidents
- `/incidents/:incidentId` Incident workspace
- `/evidence` Evidence review
- `/officers` Officers
- `/analytics` Analytics
- `/settings` Settings
