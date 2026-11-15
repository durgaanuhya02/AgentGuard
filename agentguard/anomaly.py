"""Behavioural anomaly detection for agents (Isolation Forest).

Each attempted tool call becomes a small feature vector. The model learns what "normal" agent
behaviour looks like and flags calls that don't fit, e.g. a burst of refunds seconds apart.

The baseline is SYNTHETIC for now (generated below). Once real traffic exists, retrain on each
agent's own history with `fit(features)`.
"""

from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

import numpy as np
from sklearn.ensemble import IsolationForest

IST = timezone(timedelta(hours=5, minutes=30))
FEATURES = ["calls_last_60s", "seconds_since_last", "amount_inr", "hour_ist", "is_new_tool"]
# Features checked against the training range. Amount is left out on purpose: large amounts are
# handled by human approval, and an approved big refund shouldn't push the agent towards a freeze.
RANGE_CHECKED = ["calls_last_60s", "seconds_since_last", "hour_ist"]
MAX_GAP_S = 3600.0


def build_features(now: datetime, recent: list[dict], amount_inr: float, is_new_tool: bool) -> list[float]:
    """`recent` = this agent's attempts in the last hour, oldest first (from Store.recent_attempts)."""
    times = [datetime.fromisoformat(r["at"]) for r in recent]
    calls_60 = sum(1 for t in times if (now - t).total_seconds() <= 60)
    gap = (now - times[-1]).total_seconds() if times else MAX_GAP_S
    return [float(calls_60), min(max(gap, 0.0), MAX_GAP_S), float(amount_inr),
            float(now.astimezone(IST).hour), 1.0 if is_new_tool else 0.0]


def synthetic_normal(n: int = 3000, seed: int = 7) -> np.ndarray:
    """Normal support-agent behaviour: a call every few minutes, business hours, modest amounts."""
    rng = np.random.default_rng(seed)
    calls_60 = rng.choice([0, 1, 2], size=n, p=[0.75, 0.2, 0.05])
    gap = np.clip(rng.exponential(scale=600, size=n) + 45, 45, MAX_GAP_S)
    gap[rng.random(n) < 0.05] = MAX_GAP_S  # first call after a quiet hour
    # Agents chain related calls (lookup_order -> issue_refund) a few seconds apart while the
    # LLM thinks. That is normal and must not look like a loop.
    follow_up = rng.random(n) < 0.3
    gap[follow_up] = rng.uniform(1.0, 30.0, size=follow_up.sum())
    calls_60[follow_up] = rng.choice([1, 2, 3], size=follow_up.sum(), p=[0.6, 0.3, 0.1])
    is_refund = rng.random(n) < 0.4
    amount = np.where(is_refund, rng.uniform(100, 2500, size=n), 0.0)
    hour = rng.integers(9, 22, size=n)
    new_tool = (rng.random(n) < 0.02).astype(float)
    return np.column_stack([calls_60, gap, amount, hour, new_tool]).astype(float)


class AnomalyDetector:
    def __init__(self, contamination: float = 0.01, window: int = 3, flags_to_freeze: int = 2,
                 seed: int = 42):
        self.model = IsolationForest(n_estimators=200, contamination=contamination, random_state=seed)
        self.window = window
        self.flags_to_freeze = flags_to_freeze
        self._recent_flags: dict[str, deque[bool]] = defaultdict(lambda: deque(maxlen=self.window))
        self.fit(synthetic_normal())

    def fit(self, X: np.ndarray) -> None:
        self.model.fit(X)
        # Isolation Forest only splits inside the range it was trained on, so a point far outside
        # that range (12 calls/min when training never exceeded 2) lands in the same leaf as an
        # ordinary edge point and is NOT scored as unusual. We therefore also check each feature
        # against the range seen in training.
        self.lo = np.percentile(X, 0.1, axis=0)
        self.hi = np.percentile(X, 99.9, axis=0)

    def out_of_range(self, features: list[float]) -> list[str]:
        x = np.asarray(features, dtype=float)
        idx = [FEATURES.index(f) for f in RANGE_CHECKED]
        return [FEATURES[i] for i in idx if x[i] < self.lo[i] or x[i] > self.hi[i]]

    def score(self, features: list[float]) -> tuple[float, bool]:
        """Returns (score, is_anomalous). Lower score = more unusual; < 0 means anomalous."""
        x = np.asarray([features], dtype=float)
        s = float(self.model.decision_function(x)[0])
        return s, s < 0 or bool(self.out_of_range(features))

    def observe(self, agent_id: str, features: list[float]) -> tuple[float, bool, bool]:
        """Score one call and decide whether to freeze.

        One odd call is not enough: we freeze when `flags_to_freeze` of the last `window` calls
        are anomalous. That avoids freezing on a single false positive.
        Returns (score, is_anomalous, should_freeze).
        """
        s, anomalous = self.score(features)
        flags = self._recent_flags[agent_id]
        flags.append(anomalous)
        return s, anomalous, sum(flags) >= self.flags_to_freeze

    def reset(self, agent_id: str) -> None:
        self._recent_flags.pop(agent_id, None)
