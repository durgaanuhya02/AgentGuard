"""The core decision engine. Every agent tool call goes through `Guard.check` first."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable

from agentguard.anomaly import AnomalyDetector, build_features
from agentguard.models import ActionRequest, Decision, Outcome
from agentguard.policy import Policy
from agentguard.store import Store

AuditSink = Callable[[dict], None]


class Guard:
    def __init__(self, policy: Policy | None = None, store: Store | None = None,
                 detector: AnomalyDetector | None = None, sinks: list[AuditSink] | None = None):
        self.policy = policy or Policy.load()
        self.store = store or Store()
        self.detector = detector or AnomalyDetector()
        # Extra places to send every audit event, e.g. WorkOS Audit Logs.
        self.sinks = sinks or []

    # ------------------------------------------------------------------ check
    def check(self, req: ActionRequest) -> Decision:
        now = req.at.astimezone(timezone.utc)
        agent = self.policy.agents.get(req.agent_id)
        if agent is None:
            return self._finish(req, now, None, Outcome.DENY, f"Unknown agent '{req.agent_id}'")
        user = self.policy.users[agent.on_behalf_of]

        # 1. Frozen agents can do nothing until an admin unfreezes them.
        frozen = self.store.frozen(agent.id)
        if frozen:
            return self._finish(req, now, user.id, Outcome.FROZEN,
                                f"Agent frozen since {frozen['frozen_at'][:19]}Z, waiting for admin review")

        # 2. Delegation: agent scope AND the launching user's role.
        if req.tool not in self.policy.effective_tools(agent):
            if req.tool not in agent.scopes:
                why = f"'{req.tool}' is outside this agent's scopes"
            else:
                why = (f"{user.name} ({user.role}) launched this agent and is not allowed to use "
                       f"'{req.tool}', so the agent can't either")
            return self._finish(req, now, user.id, Outcome.DENY, why)

        # 3. Daily spend cap (what running the agent costs).
        spent = self.store.spent_today(agent.id, now)
        if spent + req.cost_inr > agent.daily_budget_inr:
            return self._finish(req, now, user.id, Outcome.DENY,
                                f"Daily budget ₹{agent.daily_budget_inr:,.0f} would be exceeded "
                                f"(spent ₹{spent:,.0f}, this call ₹{req.cost_inr:,.0f})")

        # 4. Daily call limit per tool.
        limit = agent.daily_call_limit.get(req.tool)
        if limit is not None and self.store.calls_today(agent.id, req.tool, now) >= limit:
            return self._finish(req, now, user.id, Outcome.DENY,
                                f"Daily limit of {limit} '{req.tool}' calls reached")

        # 5. Behaviour check. Runs before approvals so a loop of large actions is still caught.
        recent = self.store.recent_attempts(agent.id, now, timedelta(hours=1))
        features = build_features(now, recent, req.amount_inr,
                                  is_new_tool=req.tool not in self.store.tools_used(agent.id))
        score, anomalous, should_freeze = self.detector.observe(agent.id, features)
        if should_freeze:
            reason = (f"Unusual behaviour ({int(features[0]) + 1} calls in 60s, "
                      f"{features[1]:.1f}s apart). Agent frozen for admin review")
            self.store.freeze(agent.id, now, reason)
            return self._finish(req, now, user.id, Outcome.FROZEN, reason, score)

        # 6. Large actions need a human.
        threshold = self.policy.approval_threshold(agent, req.tool)
        if threshold is not None and req.amount_inr > threshold:
            approval_id = self.store.create_approval(now, agent.id, user.id, req.tool,
                                                     req.amount_inr, req.cost_inr)
            return self._finish(req, now, user.id, Outcome.NEEDS_APPROVAL,
                                f"₹{req.amount_inr:,.0f} is above {user.name}'s limit of "
                                f"₹{threshold:,.0f} for '{req.tool}'", score, approval_id)

        note = " (slightly unusual, watching)" if anomalous else ""
        return self._finish(req, now, user.id, Outcome.ALLOW, "Within permissions and budget" + note, score)

    # -------------------------------------------------------------- approvals
    def resolve_approval(self, approval_id: int, approver_id: str, approve: bool,
                         at: datetime | None = None) -> Decision:
        at = (at or datetime.now(timezone.utc)).astimezone(timezone.utc)
        ap = self.store.get_approval(approval_id)
        if ap is None or ap["status"] != "pending":
            raise ValueError(f"Approval {approval_id} not found or already decided")
        approver = self.policy.users.get(approver_id)
        if approver is None:
            raise PermissionError(f"Unknown approver '{approver_id}'")
        role = self.policy.roles[approver.role]
        limit = role.approval_over_inr.get(ap["tool"])
        if ap["tool"] not in role.tools or (limit is not None and ap["amount_inr"] > limit):
            raise PermissionError(f"{approver.name} ({approver.role}) can't approve this action")

        self.store.decide_approval(approval_id, approve, approver_id, at)
        req = ActionRequest(agent_id=ap["agent_id"], tool=ap["tool"], amount_inr=ap["amount_inr"],
                            cost_inr=ap["cost_inr"], at=at)
        if approve:
            return self._finish(req, at, ap["on_behalf_of"], Outcome.ALLOW,
                                f"Approved by {approver.name} (approval #{approval_id})")
        return self._finish(req, at, ap["on_behalf_of"], Outcome.DENY,
                            f"Rejected by {approver.name} (approval #{approval_id})")

    # ---------------------------------------------------------------- freezing
    def unfreeze(self, agent_id: str, admin_id: str) -> None:
        admin = self.policy.users.get(admin_id)
        if admin is None or admin.role != "admin":
            raise PermissionError("Only an admin can unfreeze an agent")
        self.store.unfreeze(agent_id)
        self.detector.reset(agent_id)

    # ----------------------------------------------------------------- helpers
    def _finish(self, req: ActionRequest, now: datetime, on_behalf_of: str | None, outcome: Outcome,
                reason: str, score: float | None = None, approval_id: int | None = None) -> Decision:
        self.store.record(now, req.agent_id, on_behalf_of, req.tool, req.amount_inr, req.cost_inr,
                          outcome.value, reason, score)
        event = {"at": now.isoformat(), "agent_id": req.agent_id, "on_behalf_of": on_behalf_of,
                 "tool": req.tool, "amount_inr": req.amount_inr, "cost_inr": req.cost_inr,
                 "outcome": outcome.value, "reason": reason}
        for sink in self.sinks:
            try:
                sink(event)
            except Exception:  # an audit sink failing must never block the decision
                pass
        return Decision(outcome=outcome, reason=reason, agent_id=req.agent_id, tool=req.tool,
                        on_behalf_of=on_behalf_of, approval_id=approval_id, anomaly_score=score)
