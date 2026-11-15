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


def audit_sink(client, organization_id: str) -> AuditSink:
    """Send each AgentGuard decision to WorkOS Audit Logs.

    The action names (e.g. `agent.issue_refund.deny`) must first be added as Audit Log event
    schemas in the WorkOS dashboard, or WorkOS will reject them.
    """
    from workos.audit_logs.models import (
        AuditLogEvent,
        AuditLogEventActor,
        AuditLogEventContext,
        AuditLogEventTarget,
    )

    def send(e: dict) -> None:
        event = AuditLogEvent(
            action=f"agent.{e['tool']}.{e['outcome']}",
            occurred_at=datetime.fromisoformat(e["at"]),
            actor=AuditLogEventActor(id=e["agent_id"], type="agent", name=e["agent_id"], metadata=None),
            targets=[AuditLogEventTarget(id=e["on_behalf_of"] or "unknown", type="user", name=None,
                                         metadata=None)],
            context=AuditLogEventContext(location="agentguard", user_agent=None),
            metadata={"reason": e["reason"][:500], "amount_inr": float(e["amount_inr"]),
                      "cost_inr": float(e["cost_inr"])},
            version=None,
        )
        client.audit_logs.create_event(organization_id=organization_id, event=event)

    return send
