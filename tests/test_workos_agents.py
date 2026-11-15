"""WorkOS Agent Auth integration, tested against a fake WorkOS client (no network)."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agentguard import ActionRequest, Guard, Outcome  # noqa: E402
from agentguard.workos_client import AgentTokenVerifier  # noqa: E402

T0 = datetime(2026, 11, 16, 4, 30, tzinfo=timezone.utc)


class FakeAgents:
    def __init__(self):
        self.revoked = []

    def validate_blueprint_token(self, blueprint_id, *, agent_access_token):
        if blueprint_id == "bp_support" and agent_access_token == "good-token":
            return SimpleNamespace(valid=True, agent_instance_id="ai_1",
                                   agent_instance_session_id="sess_1", organization_id="org_1",
                                   permissions=["lookup_order"], acting_user_id="user_priya")
        raise RuntimeError("invalid token")

    def revoke_session(self, session_id):
        self.revoked.append(session_id)


def setup():
    guard = Guard()
    guard.policy.agents["support-bot"].workos_blueprint_id = "bp_support"
    client = SimpleNamespace(agents=FakeAgents())
    verifier = AgentTokenVerifier(client, guard.policy)
    guard.freeze_hooks.append(verifier.revoke_on_freeze)
    return guard, client, verifier


def test_valid_token_maps_to_agent_with_ceiling():
    _, _, v = setup()
    assert v.verify("good-token") == ("support-bot", {"lookup_order"})
    assert v.verify("bad-token") is None


def test_workos_permissions_are_an_extra_ceiling():
    guard, _, v = setup()
    agent_id, ceiling = v.verify("good-token")
    # Priya's role allows refunds, but this token only grants lookup_order.
    d = guard.check(ActionRequest(agent_id, "issue_refund", 500, ceiling=ceiling, at=T0))
    assert d.outcome == Outcome.DENY and "credential" in d.reason
    d = guard.check(ActionRequest(agent_id, "lookup_order", ceiling=ceiling, at=T0 + timedelta(minutes=5)))
    assert d.outcome == Outcome.ALLOW


def test_freeze_revokes_the_workos_session():
    guard, client, v = setup()
    agent_id, _ = v.verify("good-token")
    for i in range(5):
        guard.check(ActionRequest(agent_id, "issue_refund", 1500, at=T0 + timedelta(seconds=0.5 * i)))
    assert guard.store.frozen(agent_id)
    assert client.agents.revoked == ["sess_1"]


def test_failing_freeze_hook_keeps_agent_frozen():
    guard, _, _ = setup()
    guard.freeze_hooks.insert(0, lambda *_: (_ for _ in ()).throw(RuntimeError("WorkOS down")))
    for i in range(5):
        guard.check(ActionRequest("support-bot", "issue_refund", 1500, at=T0 + timedelta(seconds=0.5 * i)))
    assert guard.store.frozen("support-bot")
