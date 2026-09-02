"""Living Pass API — save a verified plan, invite guests by link, and watch
the plan re-verify itself as RSVPs arrive.

Two audiences, two credentials:
  plan_id     unguessable, public — the share/invite link; reveals the pass and
              the invitation, never the guest list
  host_token  returned once at creation — required for the live status and the
              guest list (X-Host-Token header or ?host_token=)

Status contract: 201 created | 200 ok | 401 bad host token | 404 unknown plan
| 409 infeasible | 422 malformed | 429 rate-limited / plan full | 503 backend.
"""
from __future__ import annotations

import hmac
import re
import secrets

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..core.config import settings
from ..core.exceptions import CircuitBreakerOpenError, NoValidPlanError, RetryExhaustedError
from ..core.ratelimit import client_key, limiter
from ..core.store import store
from ..planning import living
from ..planning.models import PartyRequest
from ..planning.planner import TTLPartyPlanner
from . import routes as _r  # shared client/catalog/orchestrator, read at call time

router = APIRouter(tags=["living-pass"])

_ID_RE = re.compile(r"^[A-Za-z0-9_\-]{8,64}$")


def _strip_control(v: str) -> str:
    return "".join(ch for ch in v if ch >= " " or ch in "\t").strip()


class RSVP(BaseModel):
    model_config = ConfigDict(extra="forbid")

    guest_name: str = Field(..., min_length=1, max_length=80)
    attending: bool
    party_size: int = Field(default=1, ge=1, le=20)
    dietary: str = Field(default="", max_length=200)
    guest_key: str | None = Field(default=None, min_length=8, max_length=64,
                                  pattern=r"^[A-Za-z0-9_\-]+$")

    @field_validator("guest_name", "dietary")
    @classmethod
    def clean(cls, v: str) -> str:
        return _strip_control(v)

    @field_validator("guest_name")
    @classmethod
    def visible(cls, v: str) -> str:
        if not v:
            raise ValueError("guest_name must contain visible characters")
        return v

    @field_validator("party_size")
    @classmethod
    def within_cap(cls, v: int) -> int:
        if v > settings.LIVING_MAX_PARTY_SIZE:
            raise ValueError(f"party_size cannot exceed {settings.LIVING_MAX_PARTY_SIZE}")
        return v


# ---------------------------------------------------------------- helpers
def _base_url(http: Request) -> str:
    return (settings.PUBLIC_BASE_URL or str(http.base_url)).rstrip("/")


def _load(plan_id: str) -> dict:
    if not _ID_RE.match(plan_id or ""):
        raise HTTPException(status_code=404, detail="plan not found")
    saved = store.get_plan(plan_id)
    if saved is None:
        raise HTTPException(status_code=404, detail="plan not found")
    return saved


def _require_host(saved: dict, header_token: str | None, query_token: str | None) -> None:
    supplied = header_token or query_token or ""
    if not hmac.compare_digest(supplied, saved["host_token"]):
        raise HTTPException(status_code=401, detail="host token required")


def _links(http: Request, plan_id: str, host_token: str | None = None) -> dict:
    base = _base_url(http)
    links = {
        "invite_url": f"{base}/rsvp?p={plan_id}",
        "pass_url": f"{base}/api/v1/plans/{plan_id}",
    }
    if host_token:
        links["host_url"] = f"{base}/?living={plan_id}&host={host_token}"
        links["status_url"] = f"{base}/api/v1/plans/{plan_id}/status"
    return links


def _public_pass(saved: dict) -> dict:
    req, plan, ver = saved["request"], saved["plan"], saved["verification"]
    return {
        "plan_id": saved["plan_id"], "created_at": saved["created_at"],
        "theme": plan["theme"], "venue": plan["venue"],
        "honoree_name": req["honoree_name"], "honoree_age": req["honoree_age"],
        "party_date": str(req["party_date"]), "location_type": req["location_type"],
        "planned_guests": req["guest_count"], "budget": req["budget"],
        "total_cost": plan["total_cost"],
        "verification": {"passed": ver["passed"], "checks_passed": ver["checks_passed"],
                         "checks_total": ver["checks_total"]},
        "line_items": [{"description": li["description"], "quantity": li["quantity"],
                        "subtotal": li["subtotal"]} for li in plan["line_items"]],
        "menu": [{"name": m["name"], "servings": m["servings"], "allergens": m["allergens"]}
                 for m in plan["menu"]],
        "schedule": plan["schedule"],
    }


# --------------------------------------------------------------- endpoints
@router.post("/plans", status_code=201)
async def create_living_pass(request: PartyRequest, http: Request) -> dict:
    if not limiter.allow(f"lp:{client_key(http)}", settings.LIVING_CREATE_RATE_PER_MIN, burst=5):
        raise HTTPException(status_code=429, detail="Too many plans. Please slow down.",
                            headers={"Retry-After": "10"})
    planner = TTLPartyPlanner(_r._client, _r._catalog, _r._orchestrator)
    try:
        result = await planner.plan(request)
    except NoValidPlanError as exc:
        raise HTTPException(status_code=409, detail={
            "error": "no_valid_plan", "message": exc.message, "violations": exc.violations,
            "minimum_feasible_budget": exc.minimum_feasible_budget, "telemetry": exc.telemetry,
        }) from exc
    except (RetryExhaustedError, CircuitBreakerOpenError) as exc:
        raise HTTPException(status_code=503, detail={
            "error": "planning_unavailable",
            "message": "The planning backend is temporarily unavailable. Please retry shortly.",
        }) from exc

    plan_id = secrets.token_urlsafe(12)
    host_token = secrets.token_urlsafe(24)
    store.save_plan(plan_id, host_token, result.backend,
                    request.model_dump(mode="json"), result.plan.model_dump(),
                    result.verification.model_dump())
    return {
        "plan_id": plan_id, "host_token": host_token,
        "status": "verified", "total_cost": result.plan.total_cost,
        **_links(http, plan_id, host_token),
    }


@router.get("/plans/{plan_id}")
def get_pass(plan_id: str, http: Request) -> dict:
    saved = _load(plan_id)
    return {**_public_pass(saved), **_links(http, plan_id)}


@router.get("/plans/{plan_id}/rsvp")
def get_invitation(plan_id: str) -> dict:
    """What a guest sees: the party, not the guest list."""
    saved = _load(plan_id)
    req, plan = saved["request"], saved["plan"]
    counts = living.live_counts(store.guests_for(plan_id))
    sched = plan.get("schedule") or []
    return {
        "plan_id": plan_id, "theme": plan["theme"], "venue": plan["venue"],
        "honoree_name": req["honoree_name"], "honoree_age": req["honoree_age"],
        "party_date": str(req["party_date"]), "location_type": req["location_type"],
        "starts": sched[0]["start"] if sched else None,
        "ends": sched[-1]["end"] if sched else None,
        "confirmed_guests": counts["confirmed"],
        "max_party_size": settings.LIVING_MAX_PARTY_SIZE,
    }


@router.post("/plans/{plan_id}/rsvp")
def submit_rsvp(plan_id: str, rsvp: RSVP, http: Request) -> dict:
    _load(plan_id)  # 404 for unknown/malformed ids before any write
    if not limiter.allow(f"rsvp:{client_key(http)}", settings.LIVING_RSVP_RATE_PER_MIN, burst=10):
        raise HTTPException(status_code=429, detail={"error": "rate_limited",
                            "message": "Too many responses; please slow down."})
    key = rsvp.guest_key
    existing = store.get_guest(plan_id, key) if key else None
    if key and existing is None:
        # A key we've never issued for this plan: treat as a fresh response
        # rather than letting a caller mint arbitrary rows.
        key = None
    if existing is None:
        if store.count_guests(plan_id) >= settings.LIVING_MAX_GUESTS_PER_PLAN:
            raise HTTPException(status_code=429, detail={"error": "plan_full",
                                "message": "This party's guest list is full."})
        key = secrets.token_urlsafe(12)
    store.upsert_guest(key, plan_id, rsvp.guest_name, rsvp.attending, rsvp.party_size, rsvp.dietary)
    counts = living.live_counts(store.guests_for(plan_id))
    return {
        "status": "updated" if existing else "received",
        "guest_key": key, "attending": rsvp.attending, "party_size": rsvp.party_size,
        "confirmed_guests": counts["confirmed"],
        "dietary_noted": bool(rsvp.dietary),
        "plan_will_recheck": True,
    }


@router.get("/plans/{plan_id}/status")
def living_status(plan_id: str, host_token: str | None = None,
                  x_host_token: str | None = Header(default=None)) -> dict:
    """The host's live picture. Deterministic and model-free: every poll
    re-grounds and re-verifies the saved selections at zero LLM cost."""
    saved = _load(plan_id)
    _require_host(saved, x_host_token, host_token)
    guests = store.guests_for(plan_id)
    return living.build_status(plan_id, saved, guests, _r._catalog)


@router.get("/plans/{plan_id}/guests")
def guest_list(plan_id: str, host_token: str | None = None,
               x_host_token: str | None = Header(default=None)) -> dict:
    saved = _load(plan_id)
    _require_host(saved, x_host_token, host_token)
    guests = store.guests_for(plan_id)
    counts = living.live_counts(guests)
    return {
        "plan_id": plan_id, **counts,
        "guests": [{"guest_key": g["guest_key"], "name": g["name"],
                    "attending": bool(g["attending"]), "party_size": g["party_size"],
                    "dietary": g["dietary"], "updated_at": g["updated_at"]} for g in guests],
    }


def reset_state() -> None:
    living.reset_state()
