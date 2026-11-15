from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone

def default_db_path() -> str:
    """AGENTGUARD_DB if set, else agentguard.db in the project root (not the current directory)."""
    return os.getenv("AGENTGUARD_DB") or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "agentguard.db")


def _ts(dt: datetime) -> str:
    """Fixed-width UTC timestamps so SQLite string comparison matches time order."""
    return dt.astimezone(timezone.utc).isoformat(timespec="microseconds")


SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    on_behalf_of TEXT,
    tool TEXT NOT NULL,
    amount_inr REAL NOT NULL,
    cost_inr REAL NOT NULL,
    outcome TEXT NOT NULL,
    reason TEXT NOT NULL,
    anomaly_score REAL
);
CREATE TABLE IF NOT EXISTS approvals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    on_behalf_of TEXT,
    tool TEXT NOT NULL,
    amount_inr REAL NOT NULL,
    cost_inr REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    decided_by TEXT,
    decided_at TEXT
);
CREATE TABLE IF NOT EXISTS frozen_agents (
    agent_id TEXT PRIMARY KEY,
    frozen_at TEXT NOT NULL,
    reason TEXT NOT NULL
);
"""


class Store:
    """SQLite storage for the audit trail, approvals and frozen agents.

    Spend and call counts are derived from allowed audit events, so the audit log is the single
    source of truth.
    """

    def __init__(self, path: str = ":memory:"):
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    # ---- audit -------------------------------------------------------------
    def record(self, at: datetime, agent_id: str, on_behalf_of: str | None, tool: str,
               amount_inr: float, cost_inr: float, outcome: str, reason: str,
               anomaly_score: float | None = None) -> int:
        with self._lock:
            cur = self.conn.execute(
                "INSERT INTO audit_events (at, agent_id, on_behalf_of, tool, amount_inr, cost_inr,"
                " outcome, reason, anomaly_score) VALUES (?,?,?,?,?,?,?,?,?)",
                (_ts(at), agent_id, on_behalf_of, tool, amount_inr, cost_inr, outcome, reason,
                 anomaly_score),
            )
            self.conn.commit()
            return cur.lastrowid

    def audit(self, agent_id: str | None = None, limit: int = 200) -> list[dict]:
        q = "SELECT * FROM audit_events"
        args: tuple = ()
        if agent_id:
            q += " WHERE agent_id = ?"
            args = (agent_id,)
        q += " ORDER BY id DESC LIMIT ?"
        return [dict(r) for r in self.conn.execute(q, args + (limit,))]

    def spent_today(self, agent_id: str, now: datetime) -> float:
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        row = self.conn.execute(
            "SELECT COALESCE(SUM(cost_inr), 0) FROM audit_events"
            " WHERE agent_id = ? AND outcome = 'allow' AND at >= ? AND at <= ?",
            (agent_id, _ts(day_start), _ts(now)),
        ).fetchone()
        return float(row[0])

    def calls_today(self, agent_id: str, tool: str, now: datetime) -> int:
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        row = self.conn.execute(
            "SELECT COUNT(*) FROM audit_events"
            " WHERE agent_id = ? AND tool = ? AND outcome = 'allow' AND at >= ? AND at <= ?",
            (agent_id, tool, _ts(day_start), _ts(now)),
        ).fetchone()
        return int(row[0])

    def recent_attempts(self, agent_id: str, now: datetime, window: timedelta) -> list[dict]:
        """All attempts (any outcome) in a window, oldest first. Used for behaviour features."""
        rows = self.conn.execute(
            "SELECT at, tool, amount_inr FROM audit_events"
            " WHERE agent_id = ? AND at >= ? AND at <= ? ORDER BY at",
            (agent_id, _ts(now - window), _ts(now)),
        )
        return [dict(r) for r in rows]

    def stats_today(self, agent_id: str, now: datetime) -> dict:
        """Counts per outcome today, plus the money in actions that were stopped."""
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        rows = self.conn.execute(
            "SELECT outcome, COUNT(*), COALESCE(SUM(amount_inr), 0) FROM audit_events"
            " WHERE agent_id = ? AND at >= ? AND at <= ? GROUP BY outcome",
            (agent_id, _ts(day_start), _ts(now)),
        ).fetchall()
        counts = {r[0]: r[1] for r in rows}
        blocked = sum(r[2] for r in rows if r[0] in ("deny", "frozen"))
        return {"actions_today": counts, "blocked_amount_today_inr": float(blocked)}

    def tools_used(self, agent_id: str) -> set[str]:
        rows = self.conn.execute(
            "SELECT DISTINCT tool FROM audit_events WHERE agent_id = ? AND outcome = 'allow'",
            (agent_id,),
        )
        return {r[0] for r in rows}

    # ---- approvals ---------------------------------------------------------
    def create_approval(self, at: datetime, agent_id: str, on_behalf_of: str | None, tool: str,
                        amount_inr: float, cost_inr: float) -> int:
        with self._lock:
            cur = self.conn.execute(
                "INSERT INTO approvals (created_at, agent_id, on_behalf_of, tool, amount_inr, cost_inr)"
                " VALUES (?,?,?,?,?,?)",
                (_ts(at), agent_id, on_behalf_of, tool, amount_inr, cost_inr),
            )
            self.conn.commit()
            return cur.lastrowid

    def get_approval(self, approval_id: int) -> dict | None:
        row = self.conn.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone()
        return dict(row) if row else None

    def list_approvals(self, status: str | None = "pending") -> list[dict]:
        if status:
            rows = self.conn.execute("SELECT * FROM approvals WHERE status = ? ORDER BY id", (status,))
        else:
            rows = self.conn.execute("SELECT * FROM approvals ORDER BY id")
        return [dict(r) for r in rows]

    def decide_approval(self, approval_id: int, approved: bool, decided_by: str, at: datetime) -> None:
        with self._lock:
            self.conn.execute(
                "UPDATE approvals SET status = ?, decided_by = ?, decided_at = ? WHERE id = ?",
                ("approved" if approved else "rejected", decided_by, _ts(at), approval_id),
            )
            self.conn.commit()

    # ---- freezing ----------------------------------------------------------
    def freeze(self, agent_id: str, at: datetime, reason: str) -> None:
        with self._lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO frozen_agents (agent_id, frozen_at, reason) VALUES (?,?,?)",
                (agent_id, _ts(at), reason),
            )
            self.conn.commit()

    def unfreeze(self, agent_id: str) -> None:
        with self._lock:
            self.conn.execute("DELETE FROM frozen_agents WHERE agent_id = ?", (agent_id,))
            self.conn.commit()

    def frozen(self, agent_id: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM frozen_agents WHERE agent_id = ?", (agent_id,)).fetchone()
        return dict(row) if row else None


def to_json(rows: list[dict]) -> str:
    return json.dumps(rows, indent=2, default=str)
