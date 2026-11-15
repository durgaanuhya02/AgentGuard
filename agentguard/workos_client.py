"""WorkOS integration: AuthKit login for humans + Audit Logs for every agent decision.

Everything here is optional. Without WORKOS_API_KEY / WORKOS_CLIENT_ID set, AgentGuard runs in
local dev mode (users picked with an X-User-Id header, audit trail only in SQLite).

Written against the `workos` Python SDK v10. Check https://workos.com/docs if a call fails.
"""

from __future__ import annotations

import os
from datetime import datetime

from agentguard.guard import AuditSink


def configured() -> bool:
    return bool(os.getenv("WORKOS_API_KEY") and os.getenv("WORKOS_CLIENT_ID"))


def get_client():
    if not configured():
        return None
    from workos import WorkOSClient

    return WorkOSClient(api_key=os.environ["WORKOS_API_KEY"], client_id=os.environ["WORKOS_CLIENT_ID"])


def authorization_url(client, redirect_uri: str, state: str) -> str:
    return client.user_management.get_authorization_url(
        provider="authkit", redirect_uri=redirect_uri, state=state
    )


def authenticate(client, code: str) -> dict:
    """Exchange the AuthKit callback code for the signed-in user."""
    res = client.user_management.authenticate_with_code(code=code)
    u = res.user
    return {"workos_id": u.id, "email": u.email, "name": u.first_name or u.email}


AUDIT_ACTIONS = {
    "allow": "agent_action.allowed",
    "deny": "agent_action.denied",
    "needs_approval": "agent_action.needs_approval",
    "frozen": "agent_action.frozen",
}
AUDIT_METADATA_KEYS = {"tool": "string", "reason": "string", "amount_inr": "number",
                       "cost_inr": "number"}


def audit_sink(client, organization_id: str) -> AuditSink:
    """Send each AgentGuard decision to WorkOS Audit Logs.

    One WorkOS action per outcome (see AUDIT_ACTIONS); the tool goes in the metadata. Register the
    actions once with `python scripts/setup_workos_audit_logs.py`, or WorkOS rejects the events.
    """
    from workos.audit_logs.models import (
        AuditLogEvent,
        AuditLogEventActor,
        AuditLogEventContext,
        AuditLogEventTarget,
    )

    def send(e: dict) -> None:
        event = AuditLogEvent(
            action=AUDIT_ACTIONS[e["outcome"]],
            occurred_at=datetime.fromisoformat(e["at"]),
            actor=AuditLogEventActor(id=e["agent_id"], type="agent", name=e["agent_id"], metadata=None),
            targets=[AuditLogEventTarget(id=e["on_behalf_of"] or "unknown", type="user", name=None,
                                         metadata=None)],
            context=AuditLogEventContext(location="agentguard", user_agent=None),
            metadata={"tool": e["tool"], "reason": e["reason"][:500],
                      "amount_inr": float(e["amount_inr"]),
                      "cost_inr": float(e["cost_inr"])},
            version=None,
        )
        client.audit_logs.create_event(organization_id=organization_id, event=event)

    return send


class AgentTokenVerifier:
    """Accept WorkOS Agent Auth tokens (minted from a blueprint) as agent credentials.

    WorkOS handles agent identity: who the agent is, which user it acts for, its permission
    ceiling, and revocation. AgentGuard adds what WorkOS doesn't: spend caps, human approval and
    behavioural freezing. When AgentGuard freezes an agent, `revoke_on_freeze` also revokes the
    WorkOS sessions it has seen for that agent, so the agent's tokens stop working everywhere.

    Map an agent to its blueprint with `"workos_blueprint_id"` in config/policies.json. The token's
    permissions are used as an extra ceiling, so name WorkOS permissions after the tools
    (e.g. `issue_refund`). Untested against live WorkOS so far.
    """

    CACHE_SECONDS = 30

    def __init__(self, client, policy):
        self.client = client
        self.policy = policy
        self.sessions: dict[str, set[str]] = {}
        self._cache: dict[str, tuple[float, str, set[str]]] = {}

    def verify(self, token: str) -> tuple[str, set[str]] | None:
        """Returns (agent_id, permissions) for a valid token, else None."""
        import hashlib
        import time

        key = hashlib.sha256(token.encode()).hexdigest()
        hit = self._cache.get(key)
        if hit and time.monotonic() - hit[0] < self.CACHE_SECONDS:
            return hit[1], hit[2]
        for agent in self.policy.agents.values():
            if not agent.workos_blueprint_id:
                continue
            try:
                v = self.client.agents.validate_blueprint_token(
                    agent.workos_blueprint_id, agent_access_token=token)
            except Exception:  # invalid tokens are raised as errors, not valid=False
                continue
            perms = set(v.permissions or [])
            self.sessions.setdefault(agent.id, set()).add(v.agent_instance_session_id)
            self._cache[key] = (time.monotonic(), agent.id, perms)
            return agent.id, perms
        return None

    def revoke_on_freeze(self, agent_id: str, reason: str) -> None:
        for session_id in self.sessions.pop(agent_id, set()):
            self.client.agents.revoke_session(session_id)
        self._cache = {k: v for k, v in self._cache.items() if v[1] != agent_id}
