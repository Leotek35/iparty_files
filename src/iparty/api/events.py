"""Adoption-metrics instrumentation.

Design principles:
- PRIVACY BY DESIGN: metadata is a strict whitelist of non-identifying keys.
  Names, free text, and anything user-typed are rejected at the schema level,
  so PII cannot leak into the analytics log even by accident.
- DURABLE + SIMPLE: events append to a JSONL file (one JSON object per line)
  behind an asyncio lock, so concurrent writes never interleave. No database
  needed for the first 100 users.
- FUNNEL-FIRST: /events/summary computes the activation funnel on UNIQUE
  sessions, so a session that fires an event five times counts once.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

router = APIRouter(tags=["events"])

def _events_path() -> Path:
    """Resolved lazily so tests/deploys can change EVENTS_PATH after import."""
    return Path(os.environ.get("EVENTS_PATH", "data/events.jsonl"))


_write_lock = asyncio.Lock()

# Abuse guard: per-session event cap (in-memory, per process). Generous for a
# real user (~30 events/visit), fatal for a flooding bot.
MAX_EVENTS_PER_SESSION = 300
_session_counts: dict[str, int] = {}

EventName = Literal[
    "page_view",
    "form_started",
    "plan_requested",
    "plan_verified",
    "plan_infeasible",
    "plan_unavailable",
    "plan_copied",
    "plan_downloaded",
    "booking_interest",
    "feedback_answered",
]

# Whitelisted, non-identifying metadata keys and their allowed values.
_ALLOWED_META: dict[str, "set[str] | None"] = {
    "status": None,                       # http status as string
    "has_diet": {"true", "false"},        # whether dietary restrictions were entered
    "guests_band": {"1-10", "11-25", "26-60", "61+"},
    "budget_band": {"<100", "100-300", "301-800", "801+"},
    "answer": {"yes", "maybe", "no"},     # feedback prompt
}


class Event(BaseModel):
    session_id: str = Field(..., min_length=8, max_length=64, pattern=r"^[A-Za-z0-9\-]+$")
    event: EventName
    meta: dict[str, str] = Field(default_factory=dict)

    @field_validator("meta")
    @classmethod
    def whitelist_meta(cls, meta: dict[str, str]) -> dict[str, str]:
        if len(meta) > 6:
            raise ValueError("too many metadata keys")
        for key, value in meta.items():
            if key not in _ALLOWED_META:
                raise ValueError(f"metadata key '{key}' is not allowed (privacy whitelist)")
            if not isinstance(value, str) or len(value) > 40:
                raise ValueError(f"metadata value for '{key}' must be a short string")
            allowed = _ALLOWED_META[key]
            if allowed is not None and value not in allowed:
                raise ValueError(f"metadata value '{value}' not allowed for '{key}'")
        return meta


@router.post("/events", status_code=204)
async def record_event(event: Event) -> None:
    count = _session_counts.get(event.session_id, 0)
    if count >= MAX_EVENTS_PER_SESSION:
        raise HTTPException(status_code=429, detail="event limit reached for this session")
    _session_counts[event.session_id] = count + 1
    if len(_session_counts) > 50_000:   # bound the guard's own memory
        _session_counts.clear()

    record = {"ts": round(time.time(), 3), "session_id": event.session_id,
              "event": event.event, "meta": event.meta}
    line = json.dumps(record, separators=(",", ":")) + "\n"
    path = _events_path()
    async with _write_lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(line)


def _load_events() -> list[dict]:
    path = _events_path()
    if not path.exists():
        return []
    out = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # never let one corrupt line break analytics
    return out


@router.get("/events/summary")
async def events_summary() -> dict:
    events = _load_events()
    by_event: dict[str, set] = {}
    feedback = {"yes": 0, "maybe": 0, "no": 0}
    diet_requested = set()
    for e in events:
        by_event.setdefault(e["event"], set()).add(e["session_id"])
        if e["event"] == "feedback_answered":
            ans = e.get("meta", {}).get("answer")
            if ans in feedback:
                feedback[ans] += 1
        if e["event"] == "plan_requested" and e.get("meta", {}).get("has_diet") == "true":
            diet_requested.add(e["session_id"])

    def n(name: str) -> int:
        return len(by_event.get(name, set()))

    def rate(a: int, b: int) -> "float | None":
        return round(a / b, 3) if b else None

    verified = n("plan_verified")
    taken = len(by_event.get("plan_copied", set()) | by_event.get("plan_downloaded", set()))
    booking = n("booking_interest")
    fb_total = sum(feedback.values())
    return {
        "total_events": len(events),
        "funnel_unique_sessions": {
            "page_view": n("page_view"),
            "form_started": n("form_started"),
            "plan_requested": n("plan_requested"),
            "plan_verified": verified,
        },
        "conversion": {
            "view_to_form": rate(n("form_started"), n("page_view")),
            "form_to_request": rate(n("plan_requested"), n("form_started")),
            "request_to_verified": rate(verified, n("plan_requested")),
        },
        "plan_taken_sessions": taken,
        "plan_taken_rate": rate(taken, verified),
        "booking_interest_sessions": booking,
        "booking_interest_rate": rate(booking, verified),
        "feedback": {**feedback, "yes_rate": rate(feedback["yes"], fb_total)},
        "outcomes": {"infeasible_sessions": n("plan_infeasible"),
                     "unavailable_sessions": n("plan_unavailable")},
        "dietary_share_of_requests": rate(len(diet_requested), n("plan_requested")),
    }
