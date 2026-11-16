import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ADMIN = {"X-User-Id": "meera"}


@pytest.fixture
def client(monkeypatch):
    for k in ["WORKOS_API_KEY", "WORKOS_CLIENT_ID", "WORKOS_ORGANIZATION_ID"]:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("AGENTGUARD_DB", ":memory:")
    from api import main

    main.init_state()
    return TestClient(main.app)


def agent_headers(client, agent_id="support-bot"):
    key = client.post(f"/v1/agents/{agent_id}/keys", headers=ADMIN).json()["key"]
    return {"Authorization": f"Bearer {key}"}


def test_check_needs_an_agent_key(client):
    assert client.post("/v1/check", json={"tool": "lookup_order"}).status_code == 401
    bad = {"Authorization": "Bearer agk_dead_beef"}
    assert client.post("/v1/check", json={"tool": "lookup_order"}, headers=bad).status_code == 401


def test_check_allows_and_denies(client):
    ok = client.post("/v1/check", json={"tool": "lookup_order"}, headers=agent_headers(client)).json()
    assert ok["outcome"] == "allow"
    no = client.post("/v1/check", json={"tool": "issue_refund", "amount_inr": 100},
                     headers=agent_headers(client, "intern-helper")).json()
    assert no["outcome"] == "deny"


def test_key_cannot_impersonate_another_agent(client):
    r = client.post("/v1/check", json={"tool": "lookup_order", "agent_id": "support-bot"},
                    headers=agent_headers(client, "intern-helper"))
    assert r.status_code == 403


def test_revoked_key_stops_working(client):
    h = agent_headers(client)
    prefix = h["Authorization"].split("_")[1]
    assert client.delete(f"/v1/keys/{prefix}", headers={"X-User-Id": "priya"}).status_code == 403
    assert client.delete(f"/v1/keys/{prefix}", headers=ADMIN).status_code == 200
    assert client.post("/v1/check", json={"tool": "lookup_order"}, headers=h).status_code == 401


def test_only_admins_create_keys(client):
    assert client.post("/v1/agents/support-bot/keys", headers={"X-User-Id": "priya"}).status_code == 403


def test_human_endpoints_need_a_user(client):
    assert client.get("/v1/audit").status_code == 401
    assert client.get("/v1/audit", headers=ADMIN).status_code == 200


def test_approval_flow_over_http(client):
    d = client.post("/v1/check", json={"tool": "issue_refund", "amount_inr": 8000},
                    headers=agent_headers(client)).json()
    assert d["outcome"] == "needs_approval"
    pending = client.get("/v1/approvals", headers=ADMIN).json()
    assert [a["id"] for a in pending] == [d["approval_id"]]
    r = client.post(f"/v1/approvals/{d['approval_id']}", json={"approve": True},
                    headers={"X-User-Id": "priya"})
    assert r.status_code == 403
    r = client.post(f"/v1/approvals/{d['approval_id']}", json={"approve": True}, headers=ADMIN)
    assert r.json()["outcome"] == "allow"


def test_agents_overview(client):
    h = agent_headers(client, "intern-helper")
    client.post("/v1/check", json={"tool": "issue_refund", "amount_inr": 700}, headers=h)
    agents = client.get("/v1/agents", headers=ADMIN).json()
    bot = next(a for a in agents if a["id"] == "support-bot")
    assert bot["effective_tools"] == ["issue_refund", "lookup_order"]
    intern = next(a for a in agents if a["id"] == "intern-helper")
    assert intern["blocked_amount_today_inr"] == 700
    assert len(intern["keys"]) == 1


def test_health_is_public_and_shows_no_secrets(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["ok"] is True
    assert "sk_" not in r.text and "key" not in r.text.lower()


def test_public_overview_is_off_by_default(client):
    assert client.get("/v1/public/overview").status_code == 404


def test_public_overview_is_read_only_and_leaks_nothing(client, monkeypatch):
    monkeypatch.setenv("AGENTGUARD_PUBLIC_DEMO", "1")
    h = agent_headers(client)
    client.post("/v1/check", json={"tool": "issue_refund", "amount_inr": 8000}, headers=h)
    r = client.get("/v1/public/overview")
    assert r.status_code == 200
    body = r.json()
    assert len(body["approvals"]) == 1 and body["audit"][0]["outcome"] == "needs_approval"
    text = r.text
    assert "agk_" not in text and "@" not in text and "keys" not in body["agents"][0]
    # no way to act through the public API
    assert client.post("/v1/public/overview").status_code == 405
