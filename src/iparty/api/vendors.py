"""Vendor lead capture — the supply side of the marketplace.

YC marketplace playbook: demand is worthless without supply density, so vendor
acquisition gets a first-class, hardened endpoint (same pattern as bookings:
strict validation, per-client rate limit, append-only JSONL, counts-only
summary — no PII ever leaves the summary endpoint).
"""
from __future__ import annotations

import json
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..core.config import settings
from ..core.ratelimit import client_key, limiter
from .bookings import normalize_phone, reject_email_typos

router = APIRouter(tags=["vendors"])

_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")

_lock = threading.Lock()
_total = 0
_emails: set[str] = set()


class VendorLead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    business_name: str = Field(..., min_length=2, max_length=120)
    contact_email: str = Field(..., min_length=6, max_length=100)
    contact_phone: str = Field(default="", max_length=25)
    category: Literal["venue", "food", "cake", "supplies", "activities", "entertainment", "other"]
    city: str = Field(default="", max_length=80)
    notes: str = Field(default="", max_length=300)

    @field_validator("contact_phone")
    @classmethod
    def phone_shape(cls, v: str) -> str:
        return normalize_phone(v)

    @field_validator("contact_email")
    @classmethod
    def email_shape(cls, v: str) -> str:
        if not _EMAIL_RE.match(v):
            raise ValueError("contact_email is not a valid email address")
        return v.lower()

    @field_validator("business_name", "city", "notes")
    @classmethod
    def strip_control(cls, v: str) -> str:
        return "".join(ch for ch in v if ch >= " " or ch in "\t")


def _vendors_path() -> Path:
    p = Path(getattr(settings, "VENDORS_PATH", "data/vendor_leads.jsonl"))
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


@router.post("/vendors", status_code=201)
def create_vendor_lead(req: VendorLead, http: Request) -> dict:
    global _total
    if not limiter.allow(f"vn:{client_key(http)}", settings.VENDORS_RATE_PER_MIN, burst=5):
        raise HTTPException(status_code=429, detail={
            "error": "rate_limited",
            "message": "Too many vendor submissions; please slow down.",
        })
    reject_email_typos(req.contact_email)
    with _lock:
        if req.contact_email in _emails:
            # Idempotent by email: resubmission is a friendly no-op, not a dup row.
            return {"status": "already_registered",
                    "message": "You're already on the list — we'll be in touch."}
        _emails.add(req.contact_email)
        _total += 1
        record = {
            "ref": "VN-" + uuid.uuid4().hex[:8].upper(),
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "business_name": req.business_name,
            "contact_email": req.contact_email,
            "contact_phone": req.contact_phone,
            "category": req.category,
            "city": req.city,
            "notes": req.notes,
        }
        with _vendors_path().open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return {"status": "received",
            "message": "Thanks — we'll reach out about joining the verified catalog."}


@router.get("/vendors/summary")
def vendors_summary() -> dict:
    """Counts only — no PII."""
    with _lock:
        return {"total_leads": _total}


def reset_state() -> None:
    global _total
    with _lock:
        _emails.clear()
        _total = 0
