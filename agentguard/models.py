from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class Outcome(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    NEEDS_APPROVAL = "needs_approval"
    FROZEN = "frozen"


@dataclass
class ActionRequest:
    """One tool call an agent wants to make."""

    agent_id: str
    tool: str
    # Money the action itself moves (e.g. a refund amount). 0 for read-only tools.
    amount_inr: float = 0.0
    # What the call costs to run (API/LLM spend). Counted against the daily budget.
    cost_inr: float = 0.0
    # Extra permission ceiling from the agent's credential, e.g. the permissions in a WorkOS agent
    # token. None = no extra ceiling.
    ceiling: set[str] | None = None
    # The task the agent is working on, in the user's own words (e.g. the customer's message).
    # Should come from the trusted app layer (the chat front end), not from the agent itself.
    intent: str | None = None
    # The tool call's arguments, e.g. {"order_id": "ORD-1002", "amount_inr": 2000}.
    args: dict | None = None
    at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class Decision:
    outcome: Outcome
    reason: str
    agent_id: str
    tool: str
    on_behalf_of: str | None = None
    approval_id: int | None = None
    anomaly_score: float | None = None

    @property
    def allowed(self) -> bool:
        return self.outcome == Outcome.ALLOW
