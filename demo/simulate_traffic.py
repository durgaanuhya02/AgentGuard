"""Send live agent traffic to a running AgentGuard API, so the dashboard has something to show.

It plays the demo story in real time:
  1. support-bot works normally (lookup -> refund a few seconds later, then a pause)
  2. intern-helper tries a refund its user isn't allowed to make
  3. support-bot asks for an ₹8,000 refund (needs approval: approve it in the dashboard)
  4. support-bot falls into a refund loop and gets frozen

Usage (API must be running in dev mode, i.e. without WorkOS keys):
  python demo/simulate_traffic.py                 # full story, about 2 minutes
  python demo/simulate_traffic.py --pause 10      # shorter pauses between normal tasks
"""

import argparse
import time

import httpx

ADMIN = {"X-User-Id": "meera"}
# One shared connection: a fresh connection per call adds ~0.4 s on Windows.
http = httpx.Client(timeout=10)


def key_for(api: str, agent_id: str) -> dict:
    r = http.post(f"{api}/v1/agents/{agent_id}/keys", headers=ADMIN)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['key']}"}


def call(api: str, headers: dict, agent: str, tool: str, amount: float = 0) -> None:
    r = http.post(f"{api}/v1/check", headers=headers,
                  json={"tool": tool, "amount_inr": amount, "cost_inr": 2})
    d = r.json()
    print(f"{time.strftime('%H:%M:%S')}  {agent:<13} {tool:<13} ₹{amount:>6,.0f}  "
          f"{d.get('outcome', r.status_code)!s:<14} {d.get('reason', d.get('detail', ''))}")


def main() -> None:
    p = argparse.ArgumentParser()
    # 127.0.0.1, not localhost: on Windows "localhost" tries IPv6 first and adds ~2 s per call.
    p.add_argument("--api", default="http://127.0.0.1:8000")
    p.add_argument("--pause", type=float, default=50, help="seconds between normal tasks")
    args = p.parse_args()
    api = args.api

    support, intern = key_for(api, "support-bot"), key_for(api, "intern-helper")

    print("\n== Normal work ==")
    for order_amount in (450, 1200, 300):
        call(api, support, "support-bot", "lookup_order")
        time.sleep(5)
        call(api, support, "support-bot", "issue_refund", order_amount)
        time.sleep(args.pause)

    print("\n== Intern's agent oversteps ==")
    call(api, intern, "intern-helper", "issue_refund", 800)
    time.sleep(args.pause)

    print("\n== Large refund: approve it in the dashboard ==")
    call(api, support, "support-bot", "issue_refund", 8000)
    time.sleep(args.pause)

    print("\n== Refund loop ==")
    for _ in range(10):
        call(api, support, "support-bot", "issue_refund", 1500)
        time.sleep(0.5)


if __name__ == "__main__":
    main()
