# AgentGuard dashboard

Next.js 15 app. Shows agents (spend, frozen state, keys), pending approvals and the live audit
trail, refreshed every 2 seconds. It calls the AgentGuard API through `/api/*`, which
`next.config.ts` rewrites to `AGENTGUARD_API_URL` (default `http://localhost:8000`).

```bash
npm install
npm run dev -- -p 3001
```

In dev mode (API without WorkOS keys) pick the demo user from "Acting as". With WorkOS
configured, the page shows "Sign in with WorkOS" instead.
