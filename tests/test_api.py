import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def client(monkeypatch):
    for k in ["WORKOS_API_KEY", "WORKOS_CLIENT_ID", "WORKOS_ORGANIZATION_ID"]:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("AGENTGUARD_DB", ":memory:")
    from api import main

    main.app.state.guard = main.build_guard()
    return TestClient(main.app)


def test_check_allows_and_denies(client):
    ok = client.post("/v1/check", json={"agent_id": "support-bot", "tool": "lookup_order"}).json()
    assert ok["outcome"] == "allow"
    no = client.post("/v1/check", json={"agent_id": "intern-helper", "tool": "issue_refund",
                                        "amount_inr": 100}).json()
    assert no["outcome"] == "deny"


def test_human_endpoints_need_a_user(client):
    assert client.get("/v1/audit").status_code == 401
    assert client.get("/v1/audit", headers={"X-User-Id": "meera"}).status_code == 200


def test_approval_flow_over_http(client):
    d = client.post("/v1/check", json={"agent_id": "support-bot", "tool": "issue_refund",
                                       "amount_inr": 8000}).json()
    assert d["outcome"] == "needs_approval"
    pending = client.get("/v1/approvals", headers={"X-User-Id": "meera"}).json()
    assert [a["id"] for a in pending] == [d["approval_id"]]
    r = client.post(f"/v1/approvals/{d['approval_id']}", json={"approve": True},
                    headers={"X-User-Id": "priya"})
    assert r.status_code == 403
    r = client.post(f"/v1/approvals/{d['approval_id']}", json={"approve": True},
                    headers={"X-User-Id": "meera"})
    assert r.json()["outcome"] == "allow"


def test_agents_overview(client):
    agents = client.get("/v1/agents", headers={"X-User-Id": "meera"}).json()
    bot = next(a for a in agents if a["id"] == "support-bot")
    assert bot["effective_tools"] == ["issue_refund", "lookup_order"]
