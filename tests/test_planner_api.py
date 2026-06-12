from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from iparty.api.app import create_app
from iparty.llm.client import MockClient
from iparty.planning.models import PartyRequest
from iparty.planning.planner import TTLPartyPlanner


@pytest.mark.asyncio
async def test_planner_returns_verified_plan():
    planner = TTLPartyPlanner(MockClient(flaw_rate=0.45))
    req = PartyRequest(
        honoree_name="Mia", honoree_age=6, party_date=date.today() + timedelta(days=30),
        guest_count=12, budget=600, theme="Space", dietary_restrictions="vegetarian",
    )
    result = await planner.plan(req)
    # Best-of-N should find a passing plan most of the time; always returns telemetry.
    assert result.telemetry["candidates_generated"] >= 1
    assert "pattern_log" in result.telemetry
    assert result.plan.total_cost <= req.budget or not result.verification.passed


def test_health_and_plan_endpoints():
    client = TestClient(create_app())
    assert client.get("/health").json()["status"] == "ok"
    payload = {
        "honoree_name": "Leo", "honoree_age": 8,
        "party_date": (date.today() + timedelta(days=14)).isoformat(),
        "guest_count": 15, "budget": 750, "theme": "Superheroes",
        "dietary_restrictions": "", "location_type": "home",
    }
    r = client.post("/api/v1/plan", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["plan"]["theme"]
    assert "telemetry" in body and "verification" in body
