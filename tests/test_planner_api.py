from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from iparty.api.app import create_app
from iparty.llm.client import MockClient
from iparty.orchestration.ttl_engine import TTLOrchestrator
from iparty.pricing.catalog import StaticCatalog
from iparty.planning.models import PartyRequest
from iparty.planning.planner import TTLPartyPlanner
from iparty.core.exceptions import NoValidPlanError

CAT = StaticCatalog()


@pytest.mark.asyncio
async def test_planner_returns_verified_or_raises():
    planner = TTLPartyPlanner(MockClient(), CAT, TTLOrchestrator("t"))
    req = PartyRequest(honoree_name="Mia", honoree_age=6,
                       party_date=date.today() + timedelta(days=30),
                       guest_count=12, budget=800, theme="Space",
                       dietary_restrictions="gluten-free")
    result = await planner.plan(req)
    assert result.status == "verified"
    assert result.verification.passed
    assert result.plan.total_cost <= req.budget


@pytest.mark.asyncio
async def test_infeasible_budget_raises_with_minimum():
    planner = TTLPartyPlanner(MockClient(), CAT, TTLOrchestrator("t"))
    req = PartyRequest(honoree_name="Zoe", honoree_age=7,
                       party_date=date.today() + timedelta(days=30),
                       guest_count=50, budget=5, theme="Space")
    with pytest.raises(NoValidPlanError) as ei:
        await planner.plan(req)
    assert ei.value.minimum_feasible_budget is not None
    assert ei.value.minimum_feasible_budget > 5


def test_endpoints():
    client = TestClient(create_app())
    assert client.get("/health").json()["status"] == "ok"
    assert "circuit_breaker" in client.get("/api/v1/metrics").json()
    ok = {"honoree_name": "Leo", "honoree_age": 8,
          "party_date": (date.today() + timedelta(days=14)).isoformat(),
          "guest_count": 15, "budget": 900, "theme": "Superheroes",
          "dietary_restrictions": "", "location_type": "home"}
    r = client.post("/api/v1/plan", json=ok)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "verified"
    # Infeasible -> honest 409 with a minimum budget, NOT a shipped invalid plan.
    bad = {**ok, "budget": 3, "guest_count": 60}
    r2 = client.post("/api/v1/plan", json=bad)
    assert r2.status_code == 409
    assert r2.json()["detail"]["minimum_feasible_budget"] > 3
