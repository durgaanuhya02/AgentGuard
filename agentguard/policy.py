from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_POLICY_PATH = Path(__file__).resolve().parent.parent / "config" / "policies.json"


@dataclass
class Role:
    name: str
    tools: set[str]
    approval_over_inr: dict[str, float] = field(default_factory=dict)


@dataclass
class User:
    id: str
    name: str
    role: str
    # Email the person signs in with through WorkOS AuthKit.
    email: str | None = None


@dataclass
class Agent:
    id: str
    on_behalf_of: str
    scopes: set[str]
    daily_budget_inr: float
    daily_call_limit: dict[str, int] = field(default_factory=dict)


class Policy:
    """Roles, users and agents. Loaded from JSON for now; WorkOS roles later."""

    def __init__(self, roles: dict[str, Role], users: dict[str, User], agents: dict[str, Agent]):
        self.roles = roles
        self.users = users
        self.agents = agents

    @classmethod
    def load(cls, path: str | Path = DEFAULT_POLICY_PATH) -> "Policy":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        roles = {
            name: Role(name=name, tools=set(r["tools"]), approval_over_inr=r.get("approval_over_inr", {}))
            for name, r in raw["roles"].items()
        }
        users = {uid: User(id=uid, name=u["name"], role=u["role"], email=u.get("email")) for uid, u in raw["users"].items()}
        agents = {
            aid: Agent(
                id=aid,
                on_behalf_of=a["on_behalf_of"],
                scopes=set(a["scopes"]),
                daily_budget_inr=float(a["daily_budget_inr"]),
                daily_call_limit=a.get("daily_call_limit", {}),
            )
            for aid, a in raw["agents"].items()
        }
        return cls(roles, users, agents)

    def effective_tools(self, agent: Agent) -> set[str]:
        """An agent can never do more than the human who launched it.

        Effective permissions = what the agent was scoped for AND what its user's role allows.
        """
        user = self.users[agent.on_behalf_of]
        return agent.scopes & self.roles[user.role].tools

    def approval_threshold(self, agent: Agent, tool: str) -> float | None:
        user = self.users[agent.on_behalf_of]
        return self.roles[user.role].approval_over_inr.get(tool)
