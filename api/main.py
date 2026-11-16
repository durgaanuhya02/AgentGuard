"""AgentGuard HTTP API.

Agents (or the MCP server) call POST /v1/check before every tool call. Humans use the other
endpoints, later through the Next.js dashboard, to see the audit trail, approve actions and
unfreeze agents.

Run:  uvicorn api.main:app --reload
"""

from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import datetime, timezone  # noqa: E402

from fastapi import Depends, FastAPI, Header, HTTPException, Request  # noqa: E402
from fastapi.responses import RedirectResponse  # noqa: E402
from pydantic import BaseModel  # noqa: E402
from starlette.middleware.sessions import SessionMiddleware  # noqa: E402

from agentguard.settings import load_env  # noqa: E402

load_env()

from agentguard import ActionRequest, Guard  # noqa: E402
from agentguard import workos_client  # noqa: E402
from agentguard.copilot import build_explainer, incident_facts  # noqa: E402
from agentguard.intent import build_judge  # noqa: E402
from agentguard.keys import KeyStore  # noqa: E402
from agentguard.store import Store, default_db_path  # noqa: E402


def build_guard() -> Guard:
    sinks = []
    client = workos_client.get_client()
    org = os.getenv("WORKOS_ORGANIZATION_ID")
    if client and org:
        sinks.append(workos_client.audit_sink(client, org))
    guard = Guard(store=Store(default_db_path()), sinks=sinks)
    guard.judge = build_judge(guard.policy.intent_check)
    return guard


def init_state() -> None:
    app.state.guard = build_guard()
    # Incident copilot (AI explanation of what an agent did); uses the intent-check model settings.
    app.state.explainer = build_explainer(app.state.guard.policy.intent_check)
    # WorkOS Agent Auth tokens are accepted alongside agk_ keys when WorkOS is configured.
    client = workos_client.get_client()
    app.state.agent_tokens = (workos_client.AgentTokenVerifier(client, app.state.guard.policy)
                              if client else None)
    if app.state.agent_tokens:
        app.state.guard.freeze_hooks.append(app.state.agent_tokens.revoke_on_freeze)
    app.state.keys = KeyStore(app.state.guard.store)


app = FastAPI(title="AgentGuard", version="0.2.0")
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET", secrets.token_hex(32)))
init_state()


def guard() -> Guard:
    return app.state.guard


def keys() -> KeyStore:
    return app.state.keys


def require_admin(user_id: str) -> None:
    if guard().policy.users[user_id].role != "admin":
        raise HTTPException(403, "Admins only")


# ------------------------------------------------------------------ human auth
def user_email(user_id: str, default: str | None) -> str:
    """A user's sign-in email. AGENTGUARD_USER_EMAILS in .env overrides policies.json, so real
    emails stay out of the git repo. Format: `meera:you@example.com,priya:someone@example.com`."""
    for pair in os.getenv("AGENTGUARD_USER_EMAILS", "").split(","):
        uid, _, email = pair.strip().partition(":")
        if uid == user_id and email:
            return email.strip()
    return default or ""


def current_user(request: Request, x_user_id: str | None = Header(default=None)) -> str:
    """Returns the AgentGuard user id of the signed-in human.

    WorkOS mode: the AuthKit session, matched to a policy user by email.
    Dev mode (no WorkOS keys): the X-User-Id header, e.g. `X-User-Id: meera`.
    """
    if workos_client.configured():
        email = request.session.get("email")
        if not email:
            raise HTTPException(401, "Sign in at /auth/login")
        for uid, u in guard().policy.users.items():
            if user_email(uid, u.email).lower() == email.lower():
                return uid
        raise HTTPException(403, f"{email} is not an AgentGuard user")
    if not x_user_id or x_user_id not in guard().policy.users:
        raise HTTPException(401, "Dev mode: send an X-User-Id header (priya, arjun or meera)")
    return x_user_id


@app.get("/auth/login")
def login(request: Request):
    client = workos_client.get_client()
    if not client:
        raise HTTPException(400, "WorkOS is not configured; using dev mode")
    state = secrets.token_urlsafe(16)
    request.session["state"] = state
    redirect = os.getenv("WORKOS_REDIRECT_URI", "http://localhost:8000/auth/callback")
    return RedirectResponse(workos_client.authorization_url(client, redirect, state))


@app.get("/auth/callback")
def callback(request: Request, code: str, state: str | None = None):
    if not state or state != request.session.pop("state", None):
        raise HTTPException(400, "Invalid login state")
    user = workos_client.authenticate(workos_client.get_client(), code)
    request.session["email"] = user["email"]
    return RedirectResponse(os.getenv("DASHBOARD_URL", "/me"))


@app.get("/auth/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(os.getenv("DASHBOARD_URL", "/"))


@app.get("/health")
def health():
    """For hosting health checks. Says which optional features are on, never any secrets."""
    return {"ok": True, "workos": workos_client.configured(),
            "ai_judge": type(guard().judge).__name__ if guard().judge else None}


@app.get("/me")
def me(request: Request, user_id: str = Depends(current_user)):
    u = guard().policy.users[user_id]
    workos = workos_client.configured()
    return {"id": u.id, "name": u.name, "role": u.role,
            "auth": "workos" if workos else "dev",
            "email": request.session.get("email") if workos else None}


# ---------------------------------------------------------------- agent checks
class CheckBody(BaseModel):
    tool: str
    amount_inr: float = 0.0
    cost_inr: float = 0.0
    # Optional: if sent, it must match the agent the key belongs to.
    agent_id: str | None = None
    # The user's request this action serves, and the tool call's arguments (for the AI intent check).
    intent: str | None = None
    args: dict | None = None


def current_agent(authorization: str | None = Header(default=None)) -> tuple[str, set[str] | None]:
    """The calling agent and any permission ceiling from its credential.

    Accepts an AgentGuard key (`Bearer agk_...`) or, when WorkOS is configured, a WorkOS Agent
    Auth access token minted from the agent's blueprint.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Agent credential required: Authorization: Bearer <key or token>")
    credential = authorization.removeprefix("Bearer ").strip()
    if credential.startswith("agk_"):
        agent_id = keys().verify(credential)
        if agent_id is None:
            raise HTTPException(401, "Invalid or revoked agent key")
        return agent_id, None
    verifier = app.state.agent_tokens
    found = verifier.verify(credential) if verifier else None
    if found is None:
        raise HTTPException(401, "Invalid agent credential")
    return found


@app.post("/v1/check")
def check(body: CheckBody, caller: tuple[str, set[str] | None] = Depends(current_agent)):
    agent_id, ceiling = caller
    if body.agent_id and body.agent_id != agent_id:
        raise HTTPException(403, f"This credential belongs to '{agent_id}', not '{body.agent_id}'")
    d = guard().check(ActionRequest(agent_id, body.tool, body.amount_inr, body.cost_inr,
                                    ceiling=ceiling, intent=body.intent, args=body.args))
    return {"outcome": d.outcome.value, "allowed": d.allowed, "reason": d.reason,
            "on_behalf_of": d.on_behalf_of, "approval_id": d.approval_id,
            "anomaly_score": d.anomaly_score}


# ------------------------------------------------------------- human actions
@app.get("/v1/agents")
def agents(_: str = Depends(current_user)):
    g, now = guard(), datetime.now(timezone.utc)
    return [{"id": a.id, "on_behalf_of": a.on_behalf_of,
             "effective_tools": sorted(g.policy.effective_tools(a)),
             "daily_budget_inr": a.daily_budget_inr, "spent_today_inr": g.store.spent_today(a.id, now),
             **g.store.stats_today(a.id, now), "frozen": g.store.frozen(a.id),
             "keys": [k["prefix"] for k in keys().list(a.id) if not k["revoked_at"]]}
            for a in g.policy.agents.values()]


@app.get("/v1/audit")
def audit(agent_id: str | None = None, limit: int = 200, _: str = Depends(current_user)):
    return guard().store.audit(agent_id, limit)


@app.get("/v1/approvals")
def approvals(status: str | None = "pending", _: str = Depends(current_user)):
    return guard().store.list_approvals(status)


class ApprovalBody(BaseModel):
    approve: bool


@app.post("/v1/approvals/{approval_id}")
def decide(approval_id: int, body: ApprovalBody, user_id: str = Depends(current_user)):
    try:
        d = guard().resolve_approval(approval_id, user_id, body.approve)
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {"outcome": d.outcome.value, "reason": d.reason}


@app.post("/v1/agents/{agent_id}/unfreeze")
def unfreeze(agent_id: str, user_id: str = Depends(current_user)):
    try:
        guard().unfreeze(agent_id, user_id)
    except PermissionError as e:
        raise HTTPException(403, str(e))
    return {"ok": True}


# ------------------------------------------------------------------ agent keys
@app.post("/v1/agents/{agent_id}/keys")
def create_key(agent_id: str, user_id: str = Depends(current_user)):
    """Creates a key for an agent. The full key is returned only this once."""
    require_admin(user_id)
    if agent_id not in guard().policy.agents:
        raise HTTPException(404, f"Unknown agent '{agent_id}'")
    return keys().create(agent_id, user_id)


@app.get("/v1/agents/{agent_id}/keys")
def list_keys(agent_id: str, _: str = Depends(current_user)):
    return keys().list(agent_id)


@app.delete("/v1/keys/{prefix}")
def revoke_key(prefix: str, user_id: str = Depends(current_user)):
    require_admin(user_id)
    if not keys().revoke(prefix):
        raise HTTPException(404, "No active key with that prefix")
    return {"ok": True}


# ------------------------------------------------------------- incident copilot
@app.post("/v1/agents/{agent_id}/explain")
def explain(agent_id: str, _: str = Depends(current_user)):
    """What did this agent do recently, why, and what should we do? Facts are computed in code;
    the AI only writes the explanation (falls back to a rule-based summary)."""
    g = guard()
    if agent_id not in g.policy.agents:
        raise HTTPException(404, f"Unknown agent '{agent_id}'")
    facts = incident_facts(g.store, g.policy, agent_id)
    explainer = app.state.explainer
    explanation = explainer.explain(facts) if explainer else None
    if explanation is None:
        from agentguard.copilot import rule_summary
        explanation = rule_summary(facts)
    return {"facts": facts, "explanation": explanation}


# ------------------------------------------------------------- public read-only demo
PUBLIC_AUDIT_FIELDS = ("id", "at", "agent_id", "on_behalf_of", "tool", "amount_inr", "outcome",
                       "reason", "intent")
PUBLIC_APPROVAL_FIELDS = ("id", "created_at", "agent_id", "on_behalf_of", "tool", "amount_inr",
                          "reason", "intent")


@app.get("/v1/public/overview")
def public_overview():
    """Read-only snapshot for the public demo page, so visitors can see AgentGuard working
    without an account. Off unless AGENTGUARD_PUBLIC_DEMO=1. Never returns keys, emails or
    secrets, and offers no actions. Only enable it on a deployment that holds demo data."""
    if os.getenv("AGENTGUARD_PUBLIC_DEMO") != "1":
        raise HTTPException(404, "Public demo is not enabled")
    g, now = guard(), datetime.now(timezone.utc)
    agents = [{"id": a.id, "on_behalf_of": a.on_behalf_of,
               "effective_tools": sorted(g.policy.effective_tools(a)),
               "daily_budget_inr": a.daily_budget_inr,
               "spent_today_inr": g.store.spent_today(a.id, now),
               **g.store.stats_today(a.id, now),
               "frozen": g.store.frozen(a.id)} for a in g.policy.agents.values()]
    audit = [{k: e.get(k) for k in PUBLIC_AUDIT_FIELDS} for e in g.store.audit(limit=50)]
    approvals = [{k: p.get(k) for k in PUBLIC_APPROVAL_FIELDS} for p in g.store.list_approvals()]
    return {"agents": agents, "audit": audit, "approvals": approvals}
