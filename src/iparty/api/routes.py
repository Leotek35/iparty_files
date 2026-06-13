"""API routes. A single shared orchestrator gives the circuit breaker real
cross-request protection."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..core.exceptions import NoValidPlanError
from ..llm.client import build_client
from ..orchestration.ttl_engine import TTLOrchestrator
from ..pricing.catalog import StaticCatalog
from ..planning.models import PartyRequest, PlanResult
from ..planning.planner import TTLPartyPlanner

router = APIRouter(tags=["planning"])

# Process-wide singletons: the circuit breaker state is SHARED across requests.
_client = build_client()
_catalog = StaticCatalog()
_orchestrator = TTLOrchestrator(name="party")


@router.post("/plan", response_model=PlanResult)
async def create_plan(request: PartyRequest) -> PlanResult:
    planner = TTLPartyPlanner(_client, _catalog, _orchestrator)
    try:
        return await planner.plan(request)
    except NoValidPlanError as exc:
        raise HTTPException(status_code=422, detail={
            "error": "no_valid_plan",
            "message": exc.message,
            "violations": exc.violations,
            "minimum_feasible_budget": exc.minimum_feasible_budget,
            "telemetry": exc.telemetry,
        }) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"planning failed: {exc}") from exc


@router.get("/metrics")
async def metrics() -> dict:
    """Process-wide reliability metrics (real feedback signal)."""
    return {
        "circuit_breaker": _orchestrator.breaker.metrics(),
        "watchdog": _orchestrator.watchdog.metrics(),
        "backend": _client.name,
        "catalog_items": len(_catalog.all()),
    }
