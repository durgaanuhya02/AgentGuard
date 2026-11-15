"""Wipe the local demo database so a recording starts from a clean dashboard.

Deletes the SQLite file (audit trail, approvals, frozen agents, keys). Stop the API first, or
restart it afterwards, because the running API keeps the old file open.

Usage:  python scripts/reset_demo.py
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agentguard.store import default_db_path  # noqa: E402


def main() -> None:
    path = default_db_path()
    removed = [p for p in (path, path + "-journal", path + "-wal", path + "-shm") if os.path.exists(p)]
    for p in removed:
        os.remove(p)
    print(f"Removed {', '.join(removed)}" if removed else f"Nothing to remove at {path}")


if __name__ == "__main__":
    main()
