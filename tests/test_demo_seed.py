import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agentguard import Guard  # noqa: E402
from agentguard.demo_seed import seed, seed_if_empty, story_start  # noqa: E402
from agentguard.intent import RulesOnlyJudge  # noqa: E402


@pytest.mark.parametrize("hour_utc", [0, 3, 5, 9, 14, 21, 23])
def test_story_is_the_same_whenever_the_server_restarts(hour_utc):
    now = datetime(2026, 11, 16, hour_utc, 17, tzinfo=timezone.utc)
    g = Guard(judge=RulesOnlyJudge())  # what the cloud deployment runs
    seed(g, now)
    events = list(reversed(g.store.audit(limit=100)))
    assert all(datetime.fromisoformat(e["at"]) <= now for e in events)
    outcomes = Counter(e["outcome"] for e in events)
    assert outcomes["allow"] >= 6  # 3 lookups + 3 honest refunds (+ the loop's first call)
    assert outcomes["deny"] == 1  # the intern's agent
    assert outcomes["needs_approval"] == 2  # prompt injection + ₹8,000 refund
    assert outcomes["frozen"] >= 3  # the refund loop
    honest = [e for e in events[:6]]
    assert all(e["outcome"] == "allow" for e in honest)
    assert g.store.frozen("support-bot")


def test_story_starts_in_indian_daytime_and_in_the_past():
    for h in range(24):
        now = datetime(2026, 11, 16, h, 5, tzinfo=timezone.utc)
        start = story_start(now)
        assert start + timedelta(minutes=20) <= now
        assert start.astimezone(timezone(timedelta(hours=5, minutes=30))).hour == 10


def test_seed_only_when_empty():
    g = Guard(judge=RulesOnlyJudge())
    assert seed_if_empty(g) is True
    n = len(g.store.audit(limit=1000))
    assert seed_if_empty(g) is False
    assert len(g.store.audit(limit=1000)) == n


def test_api_seeds_public_demo_on_startup(monkeypatch):
    from fastapi.testclient import TestClient

    for k in ["WORKOS_API_KEY", "WORKOS_CLIENT_ID", "WORKOS_ORGANIZATION_ID"]:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("AGENTGUARD_DB", ":memory:")
    monkeypatch.setenv("AGENTGUARD_JUDGE", "rules")
    monkeypatch.setenv("AGENTGUARD_PUBLIC_DEMO", "1")
    from api import main

    main.init_state()
    body = TestClient(main.app).get("/v1/public/overview").json()
    assert len(body["audit"]) > 10 and len(body["approvals"]) == 2
    bot = next(a for a in body["agents"] if a["id"] == "support-bot")
    assert bot["frozen"] and bot["actions_today"]["allow"] >= 4
