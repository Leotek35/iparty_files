"""API routes with a shared orchestrator, per-IP rate limiting, and optional
token-gated operational endpoints.

Status contract: 200 verified | 409 infeasible/unverifiable | 422 malformed
| 429 rate-limited | 503 backend unavailable."""
from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Request

from ..core.config import settings
from ..core.exceptions import CircuitBreakerOpenError, NoValidPlanError, RetryExhaustedError
from ..core.ratelimit import client_key, limiter
from ..llm.client import build_client
from ..orchestration.ttl_engine import TTLOrchestrator
from ..planning.models import PartyRequest, PlanResult
from ..planning.planner import TTLPartyPlanner
from ..pricing.catalog import StaticCatalog

router = APIRouter(tags=["planning"])

_client = build_client()
_catalog = StaticCatalog()
_orchestrator = TTLOrchestrator(name="party")


def _require_token(header_token: str | None) -> None:
    if settings.METRICS_TOKEN and header_token != settings.METRICS_TOKEN:
        raise HTTPException(status_code=401, detail="operational endpoint requires a valid token")


@router.post("/plan", response_model=PlanResult)
async def create_plan(request: PartyRequest, http: Request) -> PlanResult:
    if not limiter.allow(f"plan:{client_key(http)}", settings.PLAN_RATE_PER_MIN, burst=5):
        raise HTTPException(status_code=429, detail="Too many plan requests. Please slow down.",
                            headers={"Retry-After": "10"})
    planner = TTLPartyPlanner(_client, _catalog, _orchestrator)
    try:
        return await planner.plan(request)
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


@router.get("/metrics")
async def metrics(x_metrics_token: str | None = Header(default=None)) -> dict:
    _require_token(x_metrics_token)
    return {
        "circuit_breaker": _orchestrator.breaker.metrics(),
        "watchdog": _orchestrator.watchdog.metrics(),
        "backend": _client.name, "catalog_items": len(_catalog.all()),
    }
