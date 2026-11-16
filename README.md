# AgentGuard

[![CI](https://github.com/durgaanuhya02/AgentGuard/actions/workflows/ci.yml/badge.svg)](https://github.com/durgaanuhya02/AgentGuard/actions/workflows/ci.yml)

**Identity, spending caps and anomaly detection for AI agents, so every agent action is tied to a
human, limited in cost, and stoppable.** Built on WorkOS (AuthKit, Audit Logs, Agent Auth).

| | |
|---|---|
| **Live demo (no sign-in)** | https://agentguard-liard.vercel.app/demo |
| **Live dashboard (admin)** | https://agentguard-liard.vercel.app (Vercel) |
| **Live API** | https://agentguard-api-cx0v.onrender.com/health (Render, free tier) |
| **Deploy it yourself** | [docs/DEPLOY.md](docs/DEPLOY.md) |

> **Anyone can watch it:** visitors to the dashboard address land on a read-only view of the live
> data (no buttons, no keys, no emails). It's turned on with `AGENTGUARD_PUBLIC_DEMO=1` because this
> deployment only holds demo data; the free server wipes its data on restart, so the API refills the
> demo story by itself whenever it starts empty (`agentguard/demo_seed.py`). Actions (approve,
> unfreeze, keys) stay behind WorkOS sign-in for the admin. The live API runs on Render's free tier: it sleeps when idle (the
> first request can take ~1 minute), its data resets on restart, and it has no AI model, so the
> intent check runs in rules-only mode. The AI features run locally (see "Run it").

## Results at a glance

- **Prompt injection stopped on the first refund.** A real LLM agent (llama3.2, run locally) was
  told by fake "admin" text to issue ten ₹2,000 refunds. The AI intent check sent the first one to a
  human; **no money moved**.
- **Refund loops frozen** on the 3rd call at machine speed, and on the 4th at LLM speed.
- **WorkOS, tested live:** AuthKit login, Audit Logs (every decision appears in WorkOS), and Agent
  Auth (a real agent token accepted; on freeze, AgentGuard revoked the agent's WorkOS session).
- **Deployed** (Render + Vercel), **Dockerised**, **CI on every push**, 69 tests.

## What it does

Most AI agents today run on one shared API key with full access. When an agent loops, gets
prompt-injected or simply misreads a task, nothing stops it. AgentGuard sits in front of every tool
call an agent makes and answers five questions:

1. **On whose behalf?** Every agent is launched by a real person and can never do more than that
   person's role allows (agent scopes ∩ user role).
2. **Is it within budget?** Daily spend caps and per-tool call limits per agent.
3. **Does it need a human?** Actions above the user's limit (e.g. a ₹8,000 refund) wait for
   someone who is allowed to approve them.
4. **Is it behaving normally?** An Isolation Forest model scores each call's behaviour and freezes
   the agent when it starts acting unlike itself (bursts, repeats, night-time activity), before the
   budget is gone.
5. **Does it match what the user asked for?** Before a money-moving action, an **AI intent check**
   compares the action with the user's original request. A mismatch goes to a human.

Every decision is written to an audit trail, locally and optionally to **WorkOS Audit Logs**.
Humans sign in with **WorkOS AuthKit**.

## AI intent check

Speed and repetition signals only notice an attack after a few actions. A prompt-injected agent's
*first* refund already looks wrong to anyone reading the customer's request next to it, so a second
model does exactly that before money-moving actions (`agentguard/intent.py`):

1. **Rule pre-check (instant):** passes the action if the customer's own message names this order
   and this amount, has no "admin / system / authorised / don't ask" style text, and the action
   hasn't already been done.
2. **AI judge (local Ollama model):** reviews everything the rule can't clear. It writes down what
   the customer asked for, then compares the action against it.
3. A "doesn't match" verdict, or a judge failure, **sends the action to a human** with the reason
   and the customer's message. The AI never silently blocks or approves on its own.

The judge is swappable (any object with a `judge()` method); configure it under `intent_check` in
`config/policies.json`. The user's request should be passed in by the app that starts the agent
(`AGENTGUARD_INTENT` for the MCP server), never by the agent itself.

**Results on 8 hand-written cases** (a sanity check, not a benchmark):

| Judge | Correct | Honest refunds |
|---|---|---|
| llama3.2 (3B) alone | 5/8 | all 3 wrongly sent to a human |
| Rule pre-check + llama3.2 | 8/8 | cleared instantly; the model only sees unclear cases |

**Live, with a real prompt-injected agent:** told by fake "admin" text to issue ten ₹2,000 refunds,
the agent's **first** refund was flagged ("the customer asked for a check, not a refund") and sent
to a human. **No money moved.** Before the AI check, 3 refunds got through; before the repetition
signal, 5 did.

## Incident copilot

Each agent card in the dashboard has **Explain with AI** (`POST /v1/agents/{id}/explain`,
`agentguard/copilot.py`). AgentGuard first computes the facts from the audit trail in code (actions,
outcomes, money moved vs stopped, the user's requests, a timeline); the AI then turns them into a
summary, a likely cause, a risk level and recommended next steps. The numbers shown always come from
the code, never from the AI. If the model is unavailable, a rule-based summary is shown instead.

Honest result with llama3.2 (3B) on a laptop CPU: about 54 s per explanation, and the write-up is
generic (it missed that one request was a prompt-injection attempt). A stronger model would do much
better; the explainer is swappable like the intent judge.

## How it fits with WorkOS

WorkOS **Agent Auth** gives each first-party agent an identity: a blueprint, a permission ceiling,
the user it acts for, and revocable sessions. It does not cover spend limits, per-action human
approval or behaviour-based stopping. AgentGuard is that layer on top:

- `/v1/check` accepts a **WorkOS agent access token** (validated against the agent's blueprint)
  as well as AgentGuard's own `agk_` keys. The token's permissions become an extra ceiling.
- When AgentGuard **freezes** an agent, it also **revokes the agent's WorkOS session**, so its
  tokens stop working everywhere, not just here.

**Tested live against WorkOS:** a real agent token minted from a WorkOS blueprint was accepted
by `/v1/check`; a refund loop got the agent frozen; WorkOS then reported the agent's session as
`revoked` and rejected the token. Reproduce with `python scripts/test_workos_agent_auth.py`
(needs Agent Auth enabled, the `lookup_order` / `issue_refund` permissions under WorkOS →
Authorization, and `AGENTGUARD_WORKOS_BLUEPRINTS=support-bot:<blueprint id>` in `.env`).

## Demo

```bash
python demo/rogue_refund_demo.py
```

```
10:45:00  intern-helper issue_refund  ₹800    DENY            Arjun (intern) launched this agent and is not allowed to use 'issue_refund', so the agent can't either
10:50:00  support-bot   issue_refund  ₹8,000  NEEDS_APPROVAL  ₹8,000 is above Priya's limit of ₹2,000 for 'issue_refund'
10:53:00  support-bot   issue_refund  ₹8,000  ALLOW           Approved by Meera (approval #1)
11:00:00  support-bot   issue_refund  ₹1,500  ALLOW           Within permissions and budget
11:00:00  support-bot   issue_refund  ₹1,500  ALLOW           Within permissions and budget (slightly unusual, watching)
11:00:01  support-bot   issue_refund  ₹1,500  FROZEN          Unusual behaviour (3 calls in 60s, 0.5s apart). Agent frozen for admin review
```

A refund loop at 2 calls/second is stopped at the 3rd call. Unchecked for an hour it would be
7,200 refunds.

## Architecture

```
 AI agent / MCP client ──► MCP server (mcp_server/) ──► POST /v1/check ──► Guard
                                                                           │
                         1. frozen?  2. delegation  3. budget  4. call limit
                         5. anomaly (Isolation Forest)  6. AI intent check  7. approval threshold
                                                                           │
                        SQLite audit trail ◄──────────────────────────────┤
                        WorkOS Audit Logs  ◄──────────────────────────────┘
 Humans ──► WorkOS AuthKit login ──► /v1/audit, /v1/approvals, /v1/agents/{id}/unfreeze
```

| Path | What it is |
|---|---|
| `agentguard/guard.py` | The decision engine (`Guard.check`) |
| `agentguard/policy.py`, `config/policies.json` | Roles, users, agents |
| `agentguard/anomaly.py` | Behaviour features + Isolation Forest |
| `agentguard/store.py` | SQLite audit trail, approvals, frozen agents |
| `agentguard/workos_client.py` | AuthKit login + Audit Logs sink |
| `api/main.py` | FastAPI service |
| `mcp_server/server.py` | Sample "orders" MCP server, every tool guarded |
| `agentguard/keys.py` | Per-agent API keys (hashed, revocable) |
| `dashboard/` | Next.js dashboard: agents, approvals, live audit trail |
| `demo/rogue_refund_demo.py` | The demo story, offline in one terminal |
| `demo/simulate_traffic.py` | The same story as live traffic against the API, for the dashboard |
| `scripts/create_agent_key.py` | Create an agent key from the command line |
| `scripts/reset_demo.py` | Wipe the local database before recording a demo |
| `agent/run_agent.py` | A real LLM agent (local Ollama model) using the guarded MCP server |
| `agentguard/intent.py` | AI intent check: rule pre-check + swappable AI judge |
| `agentguard/copilot.py` | Incident copilot: facts from code, explanation from AI |
| `scripts/seed_live_demo.py` | Plays the demo story against a deployed AgentGuard |
| `scripts/test_workos_agent_auth.py` | Live WorkOS Agent Auth test |
| `render.yaml`, `Dockerfile`, `docker-compose.yml` | Deployment |

## Run it

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
pytest                          # 69 tests
uvicorn api.main:app --reload   # API on http://localhost:8000/docs

cd dashboard && npm install && npm run dev -- -p 3001   # dashboard on http://localhost:3001
python demo/simulate_traffic.py                         # live demo traffic (about 4 minutes)
```

A real LLM agent (needs [Ollama](https://ollama.com) and `ollama pull llama3.2`):

```bash
python agent/run_agent.py normal                                   # looks up and refunds an order
python agent/run_agent.py injection --api http://127.0.0.1:8000   # prompt-injection attack, live in the dashboard
```

Result with llama3.2 (3B) at temperature 0: told by fake "admin" text to issue ten ₹2,000 refunds,
the model tried to. With the AI intent check, the first refund went to a human and no money moved
(see "AI intent check" above). Without it, behaviour signals froze the agent on the 4th call.
Note: when a tool call failed once, the agent still told the customer the refund was done. Trust
the audit trail, not the agent's words.
The `indirect-injection` scenario hides the same instruction in order data; the 3B model read it
but didn't act on it in our runs.

Agents authenticate to `/v1/check` with their own key (`Authorization: Bearer agk_...`). Admins
create and revoke keys in the dashboard; the full key is shown once and only its hash is stored.

**WorkOS login (tested live):** put `WORKOS_API_KEY`, `WORKOS_CLIENT_ID` and `WORKOS_ORGANIZATION_ID`
in `.env` (copy `.env.example`), add `http://localhost:3001/api/auth/callback` as a Redirect URI under
WorkOS → Applications → your app → Redirects, and map your login email to a user with
`AGENTGUARD_USER_EMAILS=meera:you@example.com` (kept in `.env`, so real emails stay out of git).
The dashboard then shows "Sign in with WorkOS" and "Signed in as … via WorkOS".

**WorkOS Audit Logs (tested live):** run `python scripts/setup_workos_audit_logs.py` once to register
four actions (`agent_action.allowed`, `.denied`, `.needs_approval`, `.frozen`; the tool name is in the
event metadata). With `WORKOS_ORGANIZATION_ID` set, every AgentGuard decision then also appears in
WorkOS under Organizations → your organization → Audit Logs, with the agent as the actor.

Without WorkOS keys the API runs in dev mode: pick the human with an `X-User-Id` header
(`priya`, `arjun`, `meera`), or use the "Acting as" picker in the dashboard.

To use the MCP server from an MCP client, point it at `python mcp_server/server.py` (stdio) with
`AGENTGUARD_URL=http://localhost:8000` and `AGENTGUARD_AGENT_KEY=<the agent's key>`.

## Deploy

- `docker compose up --build` runs the API and dashboard together locally.
- Cloud: API on Render (`render.yaml`), dashboard on Vercel, live at
  https://agentguard-liard.vercel.app. Step by step in [docs/DEPLOY.md](docs/DEPLOY.md). In the
  cloud there's no local model, so `AGENTGUARD_JUDGE=rules`.
- CI (GitHub Actions) runs the tests, dashboard lint/type-check/build, and both Docker builds.
- Recording the demo: [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md).

## Design notes (good interview material)

- **Why the anomaly detector also checks feature ranges.** Isolation Forest only splits inside
  the range of its training data. A burst of 12 calls/minute, when training never exceeded 3,
  lands in the same leaf as a normal edge point, so it isn't scored as unusual. The first version
  missed the loop entirely; a per-feature range check fixed it.
- **Why two flags before freezing.** One odd call (the first request after a quiet hour) shouldn't
  freeze an agent. Two of the last three calls flagged = freeze.
- **Why amount isn't range-checked.** Large amounts are handled by human approval. An approved
  ₹8,000 refund shouldn't push the agent towards a freeze.
- **Why the baseline includes calls seconds apart.** Agents chain calls (lookup → refund) while
  the LLM thinks. An early baseline without this froze normal behaviour; there's a test for it now.
- **Latency: a check takes ~10 ms, but the first live run took 3 s per call.** Two causes, both
  found by timing it: on Windows `localhost` tries IPv6 first while the API listens on IPv4
  (+2.2 s, fixed by using `127.0.0.1`), and opening a new HTTP connection per call (+0.4 s, fixed
  by reusing one client). At 3 s per call the refund loop let 5 refunds through; after the fix it
  is frozen at the 3rd call. Keep the SQLite file outside OneDrive/Dropbox folders
  (`AGENTGUARD_DB`): sync clients briefly lock it and cause occasional 1–2 s spikes.
- **Why a repetition signal.** Against a real prompt-injected LLM, calls arrive ~5 s apart (model
  thinking time), too slow for the burst signal: 5 refunds got through before the freeze. Adding
  "same money-moving action repeated in 10 min" as a feature cut that to 3. Freeze reasons now
  say in plain words which signal fired.
- **Limitation:** the baseline is synthetic. With real traffic, retrain per agent on its own
  history (`AnomalyDetector.fit`).

## Build plan

- **Week 1 (done):** core guard, anomaly detector, API, guarded MCP server, demo, tests.
- **Week 2 (done):** per-agent API keys ✅; WorkOS AuthKit login ✅, Audit Logs ✅ and Agent Auth
  (tokens accepted, session revoked on freeze) ✅, all tested live.
- **Week 3 (done early):** Next.js dashboard with live audit feed, approve/reject buttons, frozen
  agents with an unfreeze button, spend per agent, key management.
- **Week 4:** real LLM agent through the MCP server ✅ (local Ollama), AI intent check ✅, incident
  copilot ✅, Docker + CI ✅, deployed on Render + Vercel ✅. Still to do: record the 90-second demo
  video, write a short blog post, send the cold emails.
