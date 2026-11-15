"""Incident copilot: facts come from code, the AI only writes text (tested with fakes)."""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agentguard import ActionRequest, Guard  # noqa: E402
from agentguard.copilot import (  # noqa: E402
    OllamaExplainer,
    incident_facts,
    parse_explanation,
    rule_summary,
)

T0 = datetime(2026, 11, 16, 4, 30, tzinfo=timezone.utc)


def loop_incident():
    g = Guard()
    g.check(ActionRequest("support-bot", "lookup_order", at=T0))
    for i in range(6):
        g.check(ActionRequest("support-bot", "issue_refund", 1500, 2, intent="check ORD-1002",
                              at=T0 + timedelta(minutes=5, seconds=0.5 * i)))
    return g


def test_facts_are_computed_from_the_audit_trail():
    g = loop_incident()
    f = incident_facts(g.store, g.policy, "support-bot", now=T0 + timedelta(minutes=10))
    assert f["actions"] == 7
    assert f["by_outcome"]["frozen"] >= 1
    refunds_allowed = f["by_outcome"]["allow"] - 1  # one allowed call was the ₹0 lookup
    assert f["money_moved_inr"] == 1500 * refunds_allowed
    assert f["frozen"] is not None and f["user_requests"] == ["check ORD-1002"]
    assert f["acts_for"] == "Priya (support)"


def test_rule_summary_without_ai():
    g = loop_incident()
    r = rule_summary(incident_facts(g.store, g.policy, "support-bot", now=T0 + timedelta(minutes=10)))
    assert r["risk"] == "high" and r["source"] == "rules"
    assert "Keep the agent frozen" in r["recommended_actions"][0]


def test_parse_explanation():
    ok = parse_explanation(json.dumps({"summary": "It looped.", "likely_cause": "bug", "risk": "HIGH",
                                       "recommended_actions": ["Revoke key", " "]}))
    assert ok["risk"] == "high" and ok["recommended_actions"] == ["Revoke key"] and ok["source"] == "ai"
    assert parse_explanation("nope") is None
    assert parse_explanation('{"risk": "low"}') is None
    assert parse_explanation('{"summary": "x", "risk": "weird"}')["risk"] == "medium"


def test_explainer_falls_back_when_model_is_down():
    g = loop_incident()
    facts = incident_facts(g.store, g.policy, "support-bot", now=T0 + timedelta(minutes=10))
    ex = OllamaExplainer(url="http://127.0.0.1:9", timeout_s=1).explain(facts)  # nothing listens here
    assert ex["source"] == "rules" and "unavailable" in ex["note"]


def test_explain_endpoint(monkeypatch):
    from fastapi.testclient import TestClient

    for k in ["WORKOS_API_KEY", "WORKOS_CLIENT_ID", "WORKOS_ORGANIZATION_ID"]:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("AGENTGUARD_DB", ":memory:")
    from api import main

    main.init_state()

    class FakeExplainer:
        def explain(self, facts):
            return {"summary": f"{facts['actions']} actions", "likely_cause": "test", "risk": "low",
                    "recommended_actions": ["none"], "source": "ai"}

    main.app.state.explainer = FakeExplainer()
    c = TestClient(main.app)
    r = c.post("/v1/agents/support-bot/explain", headers={"X-User-Id": "priya"})
    assert r.status_code == 200 and r.json()["explanation"]["summary"] == "0 actions"
    assert c.post("/v1/agents/ghost/explain", headers={"X-User-Id": "priya"}).status_code == 404
    assert c.post("/v1/agents/support-bot/explain").status_code == 401
