"""Instrumentation tests — each encodes a Week-1 critic probe."""
import json

import pytest
from fastapi.testclient import TestClient

from iparty.api.app import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("EVENTS_PATH", str(tmp_path / "events.jsonl"))
    # reset the in-memory flood guard between tests
    import iparty.api.events as ev
    ev._session_counts.clear()
    return TestClient(create_app()), tmp_path / "events.jsonl"


SID = "test-session-0001"


def test_privacy_whitelist_rejects_pii(client):
    c, _ = client
    bad = [
        {"session_id": SID, "event": "page_view", "meta": {"honoree_name": "Zoe"}},
        {"session_id": SID, "event": "page_view", "meta": {"answer": "we live at 12 Oak St"}},
        {"session_id": SID, "event": "not_a_real_event", "meta": {}},
        {"session_id": "x", "event": "page_view", "meta": {}},
    ]
    for payload in bad:
        assert c.post("/api/v1/events", json=payload).status_code == 422


def test_events_append_as_valid_jsonl(client):
    c, path = client
    for e in ["page_view", "form_started", "plan_requested"]:
        assert c.post("/api/v1/events",
                      json={"session_id": SID, "event": e, "meta": {}}).status_code == 204
    lines = path.read_text().strip().split("\n")
    assert len(lines) == 3
    assert all(json.loads(line)["session_id"] == SID for line in lines)


def test_funnel_dedupes_sessions(client):
    c, _ = client
    for e in ["page_view", "form_started", "plan_requested"]:
        c.post("/api/v1/events", json={"session_id": SID, "event": e, "meta": {}})
    for _ in range(5):  # duplicates must count once
        c.post("/api/v1/events", json={"session_id": SID, "event": "plan_verified", "meta": {}})
    c.post("/api/v1/events", json={"session_id": "bounce-session-2", "event": "page_view", "meta": {}})
    c.post("/api/v1/events", json={"session_id": SID, "event": "plan_copied", "meta": {}})
    c.post("/api/v1/events", json={"session_id": SID, "event": "feedback_answered",
                                   "meta": {"answer": "yes"}})
    s = c.get("/api/v1/events/summary").json()
    assert s["funnel_unique_sessions"] == {"page_view": 2, "form_started": 1,
                                           "plan_requested": 1, "plan_verified": 1}
    assert s["plan_taken_rate"] == 1.0
    assert s["feedback"]["yes_rate"] == 1.0


def test_summary_survives_corrupt_and_missing_log(client, tmp_path):
    c, path = client
    assert c.get("/api/v1/events/summary").status_code == 200  # missing file
    path.write_text("not json\n{\"half\":\n")
    r = c.get("/api/v1/events/summary")
    assert r.status_code == 200 and r.json()["total_events"] == 0


def test_flood_capped_per_session(client):
    c, _ = client
    from iparty.api.events import MAX_EVENTS_PER_SESSION
    codes = [c.post("/api/v1/events",
                    json={"session_id": "flood-bot-0001", "event": "page_view", "meta": {}}
                    ).status_code for _ in range(MAX_EVENTS_PER_SESSION + 50)]
    assert codes.count(204) == MAX_EVENTS_PER_SESSION
    assert codes.count(429) == 50
    # a legitimate new session is unaffected
    assert c.post("/api/v1/events",
                  json={"session_id": "legit-user-0001", "event": "page_view", "meta": {}}
                  ).status_code == 204
