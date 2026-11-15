"""Create an API key for an agent straight in the database (for first-time setup).

After that, admins can create and revoke keys from the dashboard or the API.

Usage:  python scripts/create_agent_key.py support-bot
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agentguard.keys import KeyStore  # noqa: E402
from agentguard.policy import Policy  # noqa: E402
from agentguard.store import Store, default_db_path  # noqa: E402


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("usage: python scripts/create_agent_key.py <agent_id>")
    agent_id = sys.argv[1]
    if agent_id not in Policy.load().agents:
        sys.exit(f"Unknown agent '{agent_id}'. Add it to config/policies.json first.")
    k = KeyStore(Store(default_db_path())).create(agent_id, "cli")
    print(f"Key for {agent_id} (shown once, store it safely):\n{k['key']}")


if __name__ == "__main__":
    main()
