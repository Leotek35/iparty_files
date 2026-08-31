"""Booking intent capture — the 'ticket' flow behind 'Help me book this party'.

Design constraints (mirrors events.py hardening):
- Strict pydantic validation, extra keys forbidden, tight length caps.
- Anti-flood: max N bookings per session (429 beyond that).
- Persistence is append-only JSONL under data/; the summary endpoint exposes
  counts only — never names, contacts, or free text (privacy-safe analytics).
"""
from __future__ import annotations

import json
import re
import threading
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..core.config import settings
from ..core.emailcheck import email_invalid_reason, suggest_email
from ..core.ratelimit import client_key, limiter

router = APIRouter(tags=["bookings"])

_SESSION_RE = r"^[A-Za-z0-9\-]+$"
_PHONE_RE = re.compile(r"^\+?\d{7,15}$")


def normalize_phone(v: str) -> str:
    """Optional phone: strip separators, then require +?7-15 digits."""
    if not v.strip():
        return ""
    cleaned = re.sub(r"[\s().\-]", "", v)
    if not _PHONE_RE.match(cleaned):
        raise ValueError("contact_phone must be 7-15 digits, optionally starting with +")
    return cleaned


def reject_email_typos(email: str) -> None:
    sug = suggest_email(email)
    if sug:
        raise HTTPException(status_code=422, detail={
            "error": "email_typo",
            "message": f"That email domain looks like a typo. Did you mean {sug}?",
            "did_you_mean": sug,
        })

_lock = threading.Lock()
_by_session: dict[str, int] = {}
_total = 0
_gbv = 0.0  # gross booking value pipeline (sum of requested party totals)
_confirmed_refs: set[str] = set()


class BookingParty(BaseModel):
    model_config = ConfigDict(extra="forbid")

    party_date: date
    guest_count: int = Field(..., ge=1, le=500)
    budget: float = Field(..., gt=0, le=1_000_000)
    total_cost: float = Field(..., ge=0, le=1_000_000)
    theme: str = Field(default="", max_length=120)
    location_type: str = Field(default="home", max_length=20)

    @field_validator("theme")
    @classmethod
    def strip_control(cls, v: str) -> str:
        # Same hardening as name/notes below: control chars never reach the log.
        return "".join(ch for ch in v if ch >= " " or ch in "\t")


class BookingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(..., min_length=8, max_length=64, pattern=_SESSION_RE)
    name: str = Field(..., min_length=1, max_length=100)
    contact_email: str = Field(..., min_length=6, max_length=100)
    contact_phone: str = Field(default="", max_length=25)
    notes: str = Field(default="", max_length=300)
    party: BookingParty

    @field_validator("contact_phone")
    @classmethod
    def phone_shape(cls, v: str) -> str:
        return normalize_phone(v)

    @field_validator("contact_email")
    @classmethod
    def email_shape(cls, v: str) -> str:
        reason = email_invalid_reason(v)
        if reason:
            raise ValueError(f"contact_email {reason}")
        return v.lower()

    @field_validator("name", "notes")
    @classmethod
    def strip_control(cls, v: str) -> str:
        # Strip control characters; keep unicode (names are international).
        return "".join(ch for ch in v if ch >= " " or ch in "\t")


def _bookings_path() -> Path:
    p = Path(getattr(settings, "BOOKINGS_PATH", "data/bookings.jsonl"))
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _max_per_session() -> int:
    return int(getattr(settings, "BOOKINGS_MAX_PER_SESSION", 3))


@router.post("/bookings", status_code=201)
def create_booking(req: BookingRequest, http: Request) -> dict:
    # Sync handler by design: FastAPI runs it in the threadpool, so the JSONL
    # append never blocks the event loop (triage finding BK-2).
    # Per-client rate limit closes the rotating-session_id disk-DoS hole that
    # the per-session cap alone leaves open (triage finding BK-1).
    if not limiter.allow(f"bk:{client_key(http)}", settings.BOOKINGS_RATE_PER_MIN, burst=5):
        raise HTTPException(status_code=429, detail={
            "error": "rate_limited",
            "message": "Too many booking requests; please slow down.",
        })
    reject_email_typos(req.contact_email)
    global _total, _gbv
    with _lock:
        used = _by_session.get(req.session_id, 0)
        if used >= _max_per_session():
            raise HTTPException(status_code=429, detail={
                "error": "too_many_bookings",
                "message": "This session already has the maximum number of booking requests.",
            })
        _by_session[req.session_id] = used + 1
        _total += 1
        _gbv = round(_gbv + req.party.total_cost, 2)
        ref = "IP-" + uuid.uuid4().hex[:8].upper()
        _confirmed_refs.add(ref)
        record = {
            "ref": ref,
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "session_id": req.session_id,
            "name": req.name,
            "contact_email": req.contact_email,
            "contact_phone": req.contact_phone,
            "notes": req.notes,
            "party": json.loads(req.party.model_dump_json()),
        }
        with _bookings_path().open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return {"status": "received", "booking_ref": ref,
            "message": "A party specialist will reach out within one business day."}


@router.get("/bookings/summary")
def bookings_summary() -> dict:
    """Counts and aggregates only — no PII ever leaves this endpoint.

    gbv_pipeline / est_take_revenue are the two numbers a marketplace lives
    or dies by (GBV x take rate); surfacing them here makes unit economics a
    monitored product metric instead of a spreadsheet exercise.
    """
    with _lock:
        return {
            "total_bookings": _total,
            "unique_sessions": len(_by_session),
            "gbv_pipeline": _gbv,
            "commission_rate": settings.COMMISSION_RATE,
            "est_take_revenue": round(_gbv * settings.COMMISSION_RATE, 2),
        }


def reset_state() -> None:
    """Test hook: clear in-memory counters (does not touch the JSONL log)."""
    global _total, _gbv
    with _lock:
        _by_session.clear()
        _confirmed_refs.clear()
        _total = 0
        _gbv = 0.0
