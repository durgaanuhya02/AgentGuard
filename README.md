# AgentGuard

**Identity, spending caps and anomaly detection for AI agents, so every agent action is tied to a
human, limited in cost, and stoppable.**

Most AI agents today run on one shared API key with full access. When an agent loops, gets
prompt-injected or simply misreads a task, nothing stops it. AgentGuard sits in front of every tool
call an agent makes and answers four questions:

1. **On whose behalf?** Every agent is launched by a real person and can never do more than that
   person's role allows (agent scopes ∩ user role).
2. **Is it within budget?** Daily spend caps and per-tool call limits per agent.
3. **Does it need a human?** Actions above the user's limit (e.g. a ₹8,000 refund) wait for
   someone who is allowed to approve them.
4. **Is it behaving normally?** An Isolation Forest model scores each call's behaviour and freezes
   the agent when it starts acting unlike itself (bursts, night-time activity), before the budget is
   gone.

Every decision is written to an audit trail, locally and optionally to **WorkOS Audit Logs**.
Humans sign in with **WorkOS AuthKit**.

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
                         5. anomaly (Isolation Forest)  6. approval threshold
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
| `demo/rogue_refund_demo.py` | The demo story |

## Run it

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
pytest                          # 26 tests
uvicorn api.main:app --reload   # API on http://localhost:8000/docs
```

Without WorkOS keys the API runs in dev mode: pick the human with an `X-User-Id` header
(`priya`, `arjun`, `meera`). To use WorkOS, copy `.env.example` to `.env`, add your keys from
the WorkOS dashboard, and set each user's `email` in `config/policies.json`. For Audit Logs, also
create event schemas such as `agent.issue_refund.deny` in the dashboard.

To use the MCP server from an MCP client, point it at `python mcp_server/server.py` (stdio).

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
- **Limitation:** the baseline is synthetic. With real traffic, retrain per agent on its own
  history (`AnomalyDetector.fit`).

## Build plan

- **Week 1 (done):** core guard, anomaly detector, API, guarded MCP server, demo, tests.
- **Week 2:** create a WorkOS account, wire up AuthKit login and Audit Logs end to end.
  Authenticate agents themselves on `/v1/check`. Read the WorkOS **Agents API** docs (the SDK has
  `client.agents`: blueprints, instances, sessions) and use WorkOS agent identities instead of the
  JSON agent list where it fits.
- **Week 3:** Next.js dashboard: live audit feed, approve/reject buttons, frozen agents with an
  unfreeze button, spend per agent.
- **Week 4:** connect a real LLM agent through the MCP server, record the 90-second demo, deploy
  (Render + Vercel), write the README story and the blog post, then send the cold emails.
