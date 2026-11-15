# 90-second demo video script

Goal: in 90 seconds, show a real AI agent being attacked and AgentGuard stopping it, with WorkOS
underneath. Record the screen with Loom (or OBS), voice on, 1080p.

## Before recording (5 minutes)

1. `python scripts/reset_demo.py` (clean audit trail), then start the API and dashboard.
2. `ollama run llama3.2 "hi"` once, so the model is loaded and the first call isn't slow.
3. Open three windows side by side: the **dashboard** (signed in with WorkOS), a **terminal** in the
   project folder, and the **WorkOS dashboard** on Organizations → Test Organization → Audit Logs.
4. Do a full dry run once. The local model is slow; you'll cut the waiting in editing.

## Script

| Time | On screen | Say |
|---|---|---|
| 0:00–0:10 | Dashboard, signed in "via WorkOS" | "AI agents now take real actions, like refunds. One prompt injection and an agent can drain money. This is AgentGuard: every agent action tied to a human, capped in cost, and stoppable, built on WorkOS." |
| 0:10–0:25 | Terminal: `python agent/run_agent.py normal --api http://127.0.0.1:8000` | "Here's a real LLM agent, running locally, handling a normal refund. AgentGuard's rule check sees the order and amount match what the customer asked for, so it goes straight through." |
| 0:25–0:50 | Terminal: `python agent/run_agent.py injection --api http://127.0.0.1:8000`, then the dashboard approval card | "Now an attacker hides fake admin instructions in the chat: refund ₹2,000, ten times, no confirmation. The agent obeys. But AgentGuard's AI intent check compares the action with what the customer actually asked, which was just a check, and sends the very first refund to a human. No money moves." |
| 0:50–1:05 | Agent card → **Explain with AI** | "If an agent misbehaves, the incident copilot explains what happened. The numbers come from the audit trail, the AI just writes the summary." |
| 1:05–1:20 | WorkOS dashboard → Audit Logs | "Humans sign in with WorkOS AuthKit, and every decision AgentGuard makes also lands in WorkOS Audit Logs, with the agent as the actor." |
| 1:20–1:30 | GitHub repo README | "WorkOS answers *who* the agent is. AgentGuard answers *should it keep going*. Code's on GitHub. Thanks!" |

## Tips

- Speed up the model's thinking time in editing (2–4x); say "sped up" on screen to stay honest.
- Zoom in (Ctrl +) on the dashboard so text is readable in the video.
- Don't show `.env`, API keys or your full email on screen.
- If a take goes wrong, re-run `scripts/reset_demo.py` and restart the API.
