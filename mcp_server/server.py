"""A sample "orders" MCP server whose every tool call is checked by AgentGuard first.

Any MCP client (Claude Desktop, Cursor, your own agent) can connect to it. The agent identity
comes from AGENTGUARD_AGENT_ID. Each tool asks AgentGuard before doing anything:

- AGENTGUARD_URL set   -> asks the AgentGuard API over HTTP (the real setup)
- AGENTGUARD_URL unset -> uses an in-process Guard (handy for local testing)

Run:  python mcp_server/server.py          (stdio transport, mcp 2.x)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402
from mcp.server.mcpserver import MCPServer  # noqa: E402

from agentguard import ActionRequest, Guard  # noqa: E402
from agentguard.store import Store  # noqa: E402

AGENT_ID = os.getenv("AGENTGUARD_AGENT_ID", "support-bot")
API_URL = os.getenv("AGENTGUARD_URL")
COST_PER_CALL_INR = float(os.getenv("AGENTGUARD_COST_PER_CALL_INR", "2"))

# Fake data so the demo needs no real backend.
ORDERS = {
    "ORD-1001": {"customer": "Ravi", "item": "Headphones", "paid_inr": 1499, "status": "delivered"},
    "ORD-1002": {"customer": "Sana", "item": "Laptop stand", "paid_inr": 2199, "status": "delivered"},
    "ORD-1003": {"customer": "Kiran", "item": "Office chair", "paid_inr": 8999, "status": "damaged"},
}

_local_guard: Guard | None = None


def guard_check(tool: str, amount_inr: float = 0.0) -> dict:
    if API_URL:
        r = httpx.post(f"{API_URL}/v1/check", timeout=10, json={
            "agent_id": AGENT_ID, "tool": tool, "amount_inr": amount_inr, "cost_inr": COST_PER_CALL_INR})
        r.raise_for_status()
        return r.json()
    global _local_guard
    if _local_guard is None:
        _local_guard = Guard(store=Store(os.getenv("AGENTGUARD_DB", "agentguard.db")))
    d = _local_guard.check(ActionRequest(AGENT_ID, tool, amount_inr=amount_inr, cost_inr=COST_PER_CALL_INR))
    return {"outcome": d.outcome.value, "reason": d.reason, "approval_id": d.approval_id}


def blocked(decision: dict) -> str | None:
    if decision["outcome"] == "allow":
        return None
    if decision["outcome"] == "needs_approval":
        return (f"Waiting for human approval (#{decision['approval_id']}): {decision['reason']}. "
                "Tell the user a manager must approve this refund.")
    return f"Blocked by AgentGuard ({decision['outcome']}): {decision['reason']}"


mcp = MCPServer("agentguard-orders",
                instructions="Order lookup and refunds. Every call is checked by AgentGuard.")


@mcp.tool()
def lookup_order(order_id: str) -> str:
    """Look up an order by its ID, e.g. ORD-1001."""
    if msg := blocked(guard_check("lookup_order")):
        return msg
    order = ORDERS.get(order_id)
    return str(order) if order else f"No order {order_id}"


@mcp.tool()
def issue_refund(order_id: str, amount_inr: float) -> str:
    """Refund an order (amount in rupees)."""
    if msg := blocked(guard_check("issue_refund", amount_inr)):
        return msg
    order = ORDERS.get(order_id)
    if not order:
        return f"No order {order_id}"
    if amount_inr > order["paid_inr"]:
        return f"Refund ₹{amount_inr:,.0f} is more than the ₹{order['paid_inr']:,} paid"
    return f"Refunded ₹{amount_inr:,.0f} for {order_id} ({order['customer']})"


@mcp.tool()
def delete_customer(customer: str) -> str:
    """Delete a customer record. Admin-only."""
    if msg := blocked(guard_check("delete_customer")):
        return msg
    return f"Deleted customer {customer} (demo only, nothing was really deleted)"


if __name__ == "__main__":
    mcp.run()
