"""API routes. A single shared orchestrator gives the circuit breaker real
cross-request protection.

Status-code contract (stable for the frontend):
  200 verified plan | 422 malformed input (pydantic, detail is a list)
  409 constraints infeasible (detail is a dict with minimum_feasible_budget)
  503 planning backend unavailable (breaker open / retries exhausted)
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..core.exceptions import (
    CircuitBreakerOpenError,
    NoValidPlanError,
    RetryExhaustedError,
)
from ..llm.client import build_client
from ..orchestration.ttl_engine import TTLOrchestrator
from ..pricing.catalog import StaticCatalog
from ..planning.models import PartyRequest, PlanResult
from ..planning.planner import TTLPartyPlanner

router = APIRouter(tags=["planning"])

_client = build_client()
_catalog = StaticCatalog()
_orchestrator = TTLOrchestrator(name="party")


@router.post("/plan", response_model=PlanResult)
async def create_plan(request: PartyRequest) -> PlanResult:
    planner = TTLPartyPlanner(_client, _catalog, _orchestrator)
    try:
        return await planner.plan(request)
    except NoValidPlanError as exc:
        raise HTTPException(status_code=409, detail={
            "error": "no_valid_plan",
            "message": exc.message,
            "violations": exc.violations,
            "minimum_feasible_budget": exc.minimum_feasible_budget,
            "telemetry": exc.telemetry,
        }) from exc
    except (RetryExhaustedError, CircuitBreakerOpenError) as exc:
        raise HTTPException(status_code=503, detail={
            "error": "planning_unavailable",
            "message": "The planning backend is temporarily unavailable. Please retry shortly.",
        }) from exc


@router.get("/metrics")
async def metrics() -> dict:
    return {
        "circuit_breaker": _orchestrator.breaker.metrics(),
        "watchdog": _orchestrator.watchdog.metrics(),
        "backend": _client.name,
        "catalog_items": len(_catalog.all()),
    }
