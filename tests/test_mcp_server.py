"""Each test reloads the server, so it gets a fresh in-memory Guard and makes one guarded call.

(The Guard uses the real clock here, so several calls milliseconds apart would rightly look like
a loop to the anomaly detector. Loop behaviour is covered in test_guard.py with fixed times.)
"""

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def server(monkeypatch):
    monkeypatch.delenv("AGENTGUARD_URL", raising=False)
    monkeypatch.setenv("AGENTGUARD_DB", ":memory:")
    monkeypatch.setenv("AGENTGUARD_AGENT_ID", "support-bot")
    from mcp_server import server as srv

    return importlib.reload(srv)


def test_lookup_allowed(server):
    assert "Ravi" in server.lookup_order("ORD-1001")


def test_small_refund_allowed(server):
    assert server.issue_refund("ORD-1001", 500).startswith("Refunded")


def test_tool_outside_role_blocked(server):
    assert "Blocked by AgentGuard (deny)" in server.delete_customer("Ravi")


def test_large_refund_waits_for_approval(server):
    assert "Waiting for human approval" in server.issue_refund("ORD-1003", 8000)
