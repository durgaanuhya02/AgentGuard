"""Register AgentGuard's Audit Log actions in your WorkOS environment (safe to run again).

WorkOS only accepts Audit Log events whose action has a schema. This creates one schema per
AgentGuard outcome (agent_action.allowed / denied / needs_approval / frozen). If the same schema
already exists, WorkOS just returns it.

Usage (WorkOS keys in .env):  python scripts/setup_workos_audit_logs.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agentguard.settings import load_env  # noqa: E402

load_env()

from workos.audit_logs.models import AuditLogSchemaTarget  # noqa: E402

from agentguard import workos_client  # noqa: E402
from agentguard.workos_client import AUDIT_ACTIONS, AUDIT_METADATA_KEYS  # noqa: E402


def main() -> None:
    client = workos_client.get_client()
    if client is None:
        sys.exit("WorkOS isn't configured: set WORKOS_API_KEY and WORKOS_CLIENT_ID in .env")
    metadata = {"type": "object",
                "properties": {k: {"type": t} for k, t in AUDIT_METADATA_KEYS.items()}}
    for action in AUDIT_ACTIONS.values():
        schema = client.audit_logs.create_schema(
            action, targets=[AuditLogSchemaTarget(type="user")], metadata=metadata)
        print(f"{action}: schema version {schema.version}")


if __name__ == "__main__":
    main()
