"""The 90-second demo story, runnable in a terminal.

1. support-bot (launched by Priya, support role) handles a normal morning of refunds.
2. A bug / prompt injection makes it fire refunds in a loop, 0.5 s apart.
3. AgentGuard freezes it within a few calls.
4. Meanwhile the intern's agent tries a refund it was never allowed to do.
5. A large refund waits for a human; Meera (admin) approves it.

Run:  python demo/rogue_refund_demo.py
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agentguard import ActionRequest, Guard, Outcome  # noqa: E402

COLOURS = {Outcome.ALLOW: "\033[32m", Outcome.DENY: "\033[31m",
           Outcome.NEEDS_APPROVAL: "\033[33m", Outcome.FROZEN: "\033[35m"}
RESET = "\033[0m"


def show(t: datetime, req: ActionRequest, d) -> None:
    ist = t.astimezone(timezone(timedelta(hours=5, minutes=30))).strftime("%H:%M:%S.%f")[:-4]
    amt = f"₹{req.amount_inr:>6,.0f}" if req.amount_inr else "       "
    print(f"{ist}  {req.agent_id:<13} {req.tool:<13} {amt}  "
          f"{COLOURS[d.outcome]}{d.outcome.value.upper():<14}{RESET} {d.reason}")


def main() -> None:
    guard = Guard()
    # 10:00 IST on a weekday
    t = datetime(2026, 11, 16, 4, 30, tzinfo=timezone.utc)

    print("\n== A normal morning ==")
    normal = [(0, "lookup_order", 0), (7, "issue_refund", 450), (19, "lookup_order", 0),
              (26, "issue_refund", 1200), (41, "issue_refund", 300)]
    for minutes, tool, amount in normal:
        at = t + timedelta(minutes=minutes)
        req = ActionRequest("support-bot", tool, amount_inr=amount, cost_inr=2, at=at)
        show(at, req, guard.check(req))

    print("\n== The intern's agent tries something its user can't do ==")
    at = t + timedelta(minutes=45)
    req = ActionRequest("intern-helper", "issue_refund", amount_inr=800, cost_inr=2, at=at)
    show(at, req, guard.check(req))

    print("\n== A large refund needs a human ==")
    at = t + timedelta(minutes=50)
    req = ActionRequest("support-bot", "issue_refund", amount_inr=8000, cost_inr=2, at=at)
    d = guard.check(req)
    show(at, req, d)
    at2 = at + timedelta(minutes=3)
    show(at2, req, guard.resolve_approval(d.approval_id, "meera", approve=True, at=at2))

    print("\n== 11:00 - a bug puts the agent in a refund loop ==")
    loop_start = t + timedelta(hours=1)
    frozen_after = None
    for i in range(12):
        at = loop_start + timedelta(seconds=0.5 * i)
        req = ActionRequest("support-bot", "issue_refund", amount_inr=1500, cost_inr=2, at=at)
        d = guard.check(req)
        show(at, req, d)
        if d.outcome == Outcome.FROZEN and frozen_after is None:
            frozen_after = i + 1

    allowed_in_loop = sum(1 for e in guard.store.audit("support-bot")
                          if e["outcome"] == "allow" and e["at"] >= loop_start.isoformat())
    print(f"\nFrozen at call #{frozen_after}. Refunds that went through during the loop: "
          f"{allowed_in_loop} (₹{allowed_in_loop * 1500:,}).")
    print("Unchecked, 0.5 s per refund for one hour = 7,200 refunds = ₹1,08,00,000.")

    print("\n== Pending approvals / audit trail size ==")
    print(f"pending approvals: {len(guard.store.list_approvals())}, "
          f"audit events: {len(guard.store.audit(limit=10_000))}")


if __name__ == "__main__":
    main()
