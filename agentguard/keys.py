"""Per-agent API keys.

Every agent gets its own key, so AgentGuard always knows *which* agent is calling, and one leaked
key can be revoked without touching any other agent.

Keys look like `agk_<prefix>_<secret>`. Only a SHA-256 hash is stored; the full key is shown
once, when it is created. The short prefix is kept in clear text so people can tell keys apart in
the dashboard.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT NOT NULL,
    prefix TEXT NOT NULL UNIQUE,
    key_hash TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    revoked_at TEXT,
    last_used_at TEXT
);
"""


def _hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


class KeyStore:
    """Lives in the same SQLite database (and shares the write lock) as the main Store."""

    def __init__(self, store):
        self.conn = store.conn
        self._lock = store._lock
        self.conn.executescript(SCHEMA)

    def create(self, agent_id: str, created_by: str) -> dict:
        prefix = secrets.token_hex(4)
        key = f"agk_{prefix}_{secrets.token_urlsafe(24)}"
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._lock:
            self.conn.execute(
                "INSERT INTO agent_keys (agent_id, prefix, key_hash, created_by, created_at)"
                " VALUES (?,?,?,?,?)", (agent_id, prefix, _hash(key), created_by, now))
            self.conn.commit()
        return {"agent_id": agent_id, "prefix": prefix, "key": key, "created_at": now}

    def verify(self, key: str) -> str | None:
        """Returns the agent id for a valid, unrevoked key, else None."""
        parts = key.split("_")
        if len(parts) < 3 or parts[0] != "agk":
            return None
        row = self.conn.execute(
            "SELECT agent_id, key_hash, revoked_at FROM agent_keys WHERE prefix = ?", (parts[1],)
        ).fetchone()
        if row is None or row["revoked_at"] or not hmac.compare_digest(row["key_hash"], _hash(key)):
            return None
        with self._lock:
            self.conn.execute("UPDATE agent_keys SET last_used_at = ? WHERE prefix = ?",
                              (datetime.now(timezone.utc).isoformat(timespec="seconds"), parts[1]))
            self.conn.commit()
        return row["agent_id"]

    def list(self, agent_id: str | None = None) -> list[dict]:
        q = "SELECT agent_id, prefix, created_by, created_at, revoked_at, last_used_at FROM agent_keys"
        args: tuple = ()
        if agent_id:
            q += " WHERE agent_id = ?"
            args = (agent_id,)
        return [dict(r) for r in self.conn.execute(q + " ORDER BY id", args)]

    def revoke(self, prefix: str) -> bool:
        with self._lock:
            cur = self.conn.execute(
                "UPDATE agent_keys SET revoked_at = ? WHERE prefix = ? AND revoked_at IS NULL",
                (datetime.now(timezone.utc).isoformat(timespec="seconds"), prefix))
            self.conn.commit()
        return cur.rowcount == 1
