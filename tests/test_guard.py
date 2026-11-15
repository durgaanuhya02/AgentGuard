import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agentguard import ActionRequest, Guard, Outcome  # noqa: E402

T0 = datetime(2026, 11, 16, 4, 30, tzinfo=timezone.utc)  # 10:00 IST


@pytest.fixture
def guard():
    return Guard()


def req(agent="support-bot", tool="issue_refund", amount=500, cost=2, at=T0):
    return ActionRequest(agent, tool, amount_inr=amount, cost_inr=cost, at=at)


def test_normal_refund_allowed(guard):
    assert guard.check(req()).outcome == Outcome.ALLOW


def test_agent_cannot_exceed_its_users_role(guard):
    # intern-helper is scoped for refunds, but Arjun (intern) can't refund, so the agent can't.
    d = guard.check(req(agent="intern-helper"))
    assert d.outcome == Outcome.DENY
    assert "Arjun" in d.reason


def test_tool_outside_agent_scope_denied(guard):
    d = guard.check(req(agent="intern-helper", tool="delete_customer", amount=0))
    assert d.outcome == Outcome.DENY
    assert "outside this agent's scopes" in d.reason


def test_scope_alone_is_not_enough(guard):
    # support-bot is scoped for delete_customer, but Priya (support) isn't allowed to.
    assert guard.check(req(tool="delete_customer", amount=0)).outcome == Outcome.DENY


def test_unknown_agent_denied(guard):
    assert guard.check(req(agent="ghost")).outcome == Outcome.DENY


def test_large_refund_needs_approval_then_admin_approves(guard):
    d = guard.check(req(amount=8000))
    assert d.outcome == Outcome.NEEDS_APPROVAL and d.approval_id
    done = guard.resolve_approval(d.approval_id, "meera", approve=True, at=T0 + timedelta(minutes=2))
    assert done.outcome == Outcome.ALLOW
    assert guard.store.list_approvals() == []


def test_requester_cannot_approve_above_own_limit(guard):
    d = guard.check(req(amount=8000))
    with pytest.raises(PermissionError):
        guard.resolve_approval(d.approval_id, "priya", approve=True)


def test_approval_cannot_be_decided_twice(guard):
    d = guard.check(req(amount=8000))
    guard.resolve_approval(d.approval_id, "meera", approve=False)
    with pytest.raises(ValueError):
        guard.resolve_approval(d.approval_id, "meera", approve=True)


def test_daily_budget_enforced(guard):
    # intern-helper budget is ₹1,000; lookups cost ₹400 each here, spaced out so they look normal.
    outcomes = [guard.check(req(agent="intern-helper", tool="lookup_order", amount=0, cost=400,
                                at=T0 + timedelta(minutes=10 * i))).outcome for i in range(3)]
    assert outcomes == [Outcome.ALLOW, Outcome.ALLOW, Outcome.DENY]


def test_budget_resets_next_day(guard):
    for i in range(2):
        guard.check(req(agent="intern-helper", tool="lookup_order", amount=0, cost=400,
                        at=T0 + timedelta(minutes=10 * i)))
    next_day = T0 + timedelta(days=1)
    assert guard.check(req(agent="intern-helper", tool="lookup_order", amount=0, cost=400,
                           at=next_day)).outcome == Outcome.ALLOW


def test_daily_call_limit_enforced(guard):
    guard.policy.agents["support-bot"].daily_call_limit["issue_refund"] = 2
    outcomes = [guard.check(req(at=T0 + timedelta(minutes=10 * i))).outcome for i in range(3)]
    assert outcomes[-1] == Outcome.DENY


def test_spaced_out_normal_work_never_frozen(guard):
    for i in range(20):
        d = guard.check(req(amount=300 + 50 * (i % 5), at=T0 + timedelta(minutes=6 * i)))
        assert d.outcome == Outcome.ALLOW, d.reason


def test_refund_loop_is_frozen_quickly(guard):
    outcomes = [guard.check(req(amount=1500, at=T0 + timedelta(seconds=0.5 * i))).outcome
                for i in range(10)]
    first_frozen = outcomes.index(Outcome.FROZEN)
    assert first_frozen <= 3
    assert all(o == Outcome.FROZEN for o in outcomes[first_frozen:])


def test_only_admin_can_unfreeze(guard):
    for i in range(5):
        guard.check(req(at=T0 + timedelta(seconds=0.5 * i)))
    assert guard.store.frozen("support-bot")
    with pytest.raises(PermissionError):
        guard.unfreeze("support-bot", "priya")
    guard.unfreeze("support-bot", "meera")
    assert guard.check(req(at=T0 + timedelta(minutes=30))).outcome == Outcome.ALLOW


def test_night_time_burst_is_flagged(guard):
    night = datetime(2026, 11, 16, 21, 30, tzinfo=timezone.utc)  # 03:00 IST
    outcomes = [guard.check(req(at=night + timedelta(minutes=2 * i))).outcome for i in range(3)]
    assert Outcome.FROZEN in outcomes


def test_chained_calls_seconds_apart_are_normal(guard):
    # lookup -> refund 5 s later, a few times through the morning
    for i in range(6):
        start = T0 + timedelta(minutes=8 * i)
        assert guard.check(req(tool="lookup_order", amount=0, at=start)).outcome == Outcome.ALLOW
        assert guard.check(req(at=start + timedelta(seconds=5))).outcome == Outcome.ALLOW


def test_every_decision_is_audited(guard):
    guard.check(req())
    guard.check(req(agent="intern-helper", at=T0 + timedelta(minutes=1)))
    guard.check(req(amount=8000, at=T0 + timedelta(minutes=5)))
    outcomes = {e["outcome"] for e in guard.store.audit()}
    assert outcomes == {"allow", "deny", "needs_approval"}


def test_failing_audit_sink_does_not_block(guard):
    def broken(_event):
        raise RuntimeError("WorkOS down")
    guard.sinks.append(broken)
    assert guard.check(req()).outcome == Outcome.ALLOW
