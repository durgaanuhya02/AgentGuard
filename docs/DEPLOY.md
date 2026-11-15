# Deploying AgentGuard

The API runs on **Render** (free, Docker) and the dashboard on **Vercel** (free, Next.js). The
dashboard proxies `/api/*` to the API, so the browser only ever talks to one origin and the WorkOS
login cookie just works.

## 1. API on Render

1. render.com → **New → Blueprint** → pick this GitHub repo. It reads `render.yaml`.
2. Fill in the secret values when Render asks: `WORKOS_API_KEY`, `WORKOS_CLIENT_ID`,
   `WORKOS_ORGANIZATION_ID`, `AGENTGUARD_USER_EMAILS` (e.g. `meera:you@example.com`).
   Leave `WORKOS_REDIRECT_URI` and `DASHBOARD_URL` for step 3.
3. When it's live, open `https://<api>.onrender.com/health`. You should see `{"ok": true, ...}`.

## 2. Dashboard on Vercel

1. vercel.com → **Add New → Project** → this repo, **Root Directory: `dashboard`**.
2. Environment variable: `AGENTGUARD_API_URL = https://<api>.onrender.com`
3. Deploy. Note the URL, e.g. `https://agentguard-xyz.vercel.app`.

## 3. Connect them

1. On Render set `DASHBOARD_URL = https://agentguard-xyz.vercel.app` and
   `WORKOS_REDIRECT_URI = https://agentguard-xyz.vercel.app/api/auth/callback`.
2. In WorkOS → Applications → your app → Redirects, add that same callback URL.
3. Open the Vercel URL and sign in with WorkOS.

## Things to know

- **No AI model in the cloud.** Render's free tier can't run Ollama, so `AGENTGUARD_JUDGE=rules`:
  the rule pre-check clears clear-cut honest refunds and sends anything unclear to a human, and the
  incident copilot shows its rule-based summary. Point the judge at a hosted model to get AI back.
- **Data resets.** The free tier has no persistent disk, so the SQLite audit trail is wiped on each
  redeploy or restart. Fine for a demo; use a paid disk or Postgres for anything real. WorkOS Audit
  Logs keep their copy either way.
- **Cold starts.** Free Render services sleep when idle; the first request can take ~30-60 s.
- **Agent keys.** Create them in the dashboard (admin) after signing in.
- **Local everything:** `docker compose up --build` runs API + dashboard together.
