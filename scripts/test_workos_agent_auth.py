"""Live test of WorkOS Agent Auth with AgentGuard (run once WorkOS has enabled Agent Auth).

What it does, against your WorkOS environment and a running AgentGuard API:
  1. creates (or reuses) a blueprint "agentguard-support-bot" with the permissions in
     AGENTGUARD_AGENT_PERMISSIONS (default: lookup_order, issue_refund; they must exist as
     permission slugs under WorkOS -> Authorization)
  2. mints an autonomous agent token for your organization
  3. calls AgentGuard's /v1/check with that WorkOS token (no agk_ key)
  4. sends a fast refund loop so AgentGuard freezes the agent
  5. checks that WorkOS now rejects the token, because AgentGuard revoked its session

Before running: start the API with AGENTGUARD_WORKOS_BLUEPRINTS=support-bot:<blueprint id> in .env
(step 1 prints the id), and make sure support-bot isn't frozen.

Usage:  python scripts/test_workos_agent_auth.py [--api http://127.0.0.1:8000]
"""

import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agentguard.settings import load_env  # noqa: E402

load_env()

import httpx  # noqa: E402

from agentguard import workos_client  # noqa: E402

NAME = "agentguard-support-bot"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--api", default="http://127.0.0.1:8000")
    api = p.parse_args().api
    client = workos_client.get_client()
    org = os.getenv("WORKOS_ORGANIZATION_ID")
    if not client or not org:
        sys.exit("Set WORKOS_API_KEY, WORKOS_CLIENT_ID and WORKOS_ORGANIZATION_ID in .env")

    # 1. blueprint
    try:
        existing = [b for b in client.agents.list_blueprints(limit=100).data if b.name == NAME]
    except Exception as e:
        sys.exit(f"Agent Auth isn't available on this WorkOS environment ({type(e).__name__}). "
                 "In the WorkOS dashboard open Agents -> Agent Auth and click 'Request access'.")
    perms = os.getenv("AGENTGUARD_AGENT_PERMISSIONS", "lookup_order,issue_refund").split(",")
    bp = existing[0] if existing else client.agents.create_blueprint(
        name=NAME, description="AgentGuard demo support agent", permissions=perms)
    print(f"1. blueprint {bp.id}")
    mapped = os.getenv("AGENTGUARD_WORKOS_BLUEPRINTS", "")
    if f"support-bot:{bp.id}" not in mapped:
        sys.exit(f"   Add AGENTGUARD_WORKOS_BLUEPRINTS=support-bot:{bp.id} to .env, restart the API, rerun.")

    # 2. token
    tok = client.agents.create_blueprint_token(bp.id, type="autonomous", organization_id=org)
    print(f"2. minted token for session {tok.agent_instance_session_id}, permissions {tok.permissions}")
    auth = {"Authorization": f"Bearer {tok.access_token}"}
    http = httpx.Client(base_url=api, timeout=60)

    # 3. a normal call with the WorkOS token
    d = http.post("/v1/check", headers=auth, json={"tool": "lookup_order"}).json()
    print(f"3. lookup_order with WorkOS token -> {d.get('outcome')}: {d.get('reason', d)}")

    # 4. refund loop until frozen
    for i in range(6):
        d = http.post("/v1/check", headers=auth, json={"tool": "issue_refund", "amount_inr": 1500}).json()
        print(f"4. refund {i + 1} -> {d.get('outcome')}")
        if d.get("outcome") == "frozen":
            break
        time.sleep(0.5)

    # 5. is the WorkOS session gone?
    try:
        client.agents.validate_blueprint_token(bp.id, agent_access_token=tok.access_token)
        print("5. FAIL: WorkOS still accepts the token")
    except Exception as e:
        print(f"5. OK: WorkOS now rejects the token ({type(e).__name__}); the session was revoked")


if __name__ == "__main__":
    main()
