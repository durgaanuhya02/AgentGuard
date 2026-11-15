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
