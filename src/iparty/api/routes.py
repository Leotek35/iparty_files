"""API routes."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..llm.client import build_client
from ..planning.models import PartyRequest, PlanResult
from ..planning.planner import TTLPartyPlanner

router = APIRouter(tags=["planning"])

# Build the client once; planner is cheap to recreate per request.
_client = build_client()


@router.post("/plan", response_model=PlanResult)
async def create_plan(request: PartyRequest) -> PlanResult:
    """Generate a verified party plan for the given request."""
    try:
        planner = TTLPartyPlanner(_client)
        return await planner.plan(request)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"planning failed: {exc}") from exc
