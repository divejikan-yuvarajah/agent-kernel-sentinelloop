# SentinelLoop dashboard frontend

React + Vite operations UI. Styling is CSS custom properties (no Tailwind).
JSON lives at `/api/*` on the SentinelLoop API (port 8000). Page routes such as
`/incidents` are the React UI only. The dashboard does not import agent internals.

## Design system first

Tokens, type, and primitives live in `design-system/`. Rules:
`documentation/design-rules.md`. Catalog: `/design-system`.

## Scripts

```bash
# Terminal 1 — API (required; without it the UI gets HTML instead of JSON)
cd use-cases/sentinelloop-ai
uv run python server.py

# Terminal 2 — UI
cd use-cases/sentinelloop-ai/dashboard/frontend
npm install
npm run dev      # http://localhost:5173  (proxies /api to port 8000)
npm run build
```

## Vercel (frontend)

The React dashboard deploys as a static Vite site. Demo mode works without the Python API.

```bash
cd use-cases/sentinelloop-ai/dashboard/frontend
npm run build
npx vercel --prod
```

Production project: `sentinelloop-dashboard`  
Live URL: https://sentinelloop-dashboard.vercel.app

`vercel.json` sets SPA rewrites so routes like `/incidents` resolve to `index.html`.

The FastAPI agents, Telegram bot, Slack, and Supabase API are **not** hosted on Vercel — run those separately and point `/api` at that backend when demo mode is off.

## Routes

- `/` Public marketing landing
- `/dashboard` Operations command center
- Authenticated pages share `src/components/Shell` (TopNav, router pill, breadcrumbs, page container)
- `/incidents` Active incidents
- `/incidents/:incidentId` Incident workspace
- `/evidence` Evidence review
- `/officers` Officers
- `/analytics` Analytics
- `/safety` AI Safety Center
- `/safety/review` Review Required
- `/safety/debug` Guardrail Debug Console (operators only)
- `/settings` Settings
