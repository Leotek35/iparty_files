"""End-to-end user journeys over the real HTTP surface (ASGI, no network).

MECE across the /plan status contract — every journey a user can land on:

  J1  happy path      health -> verified plan -> booking x3 -> cap -> summary
  J2  honest refusal  infeasible budget -> 409 with minimum -> retry succeeds
  J3  fail closed     unverifiable dietary need -> 409, zero LLM spend
  J4  malformed       bad payloads -> 422, never a 500
  J5  degraded        dead LLM backend -> 503 planning_unavailable
  J6  funnel          product events dedupe sessions and answer the funnel
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from iparty.api import bookings, routes
from iparty.api.app import create_app
from iparty.core.config import settings
from iparty.core.exceptions import MalformedPlanError
from iparty.orchestration.ttl_engine import TTLOrchestrator

FUTURE = (date.today() + timedelta(days=30)).isoformat()


@pytest.fixture(autouse=True)
def _isolated_state(tmp_path, monkeypatch):
    settings.BOOKINGS_PATH = str(tmp_path / "bookings.jsonl")
    monkeypatch.setenv("EVENTS_PATH", str(tmp_path / "events.jsonl"))
    bookings.reset_state()
    yield
    bookings.reset_state()


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://testserver")


def plan_body(guests=12, budget=800.0, **overrides) -> dict:
    body = {
        "honoree_name": "Journey Kid",
        "honoree_age": 7,
        "party_date": FUTURE,
        "guest_count": guests,
        "budget": budget,
        "theme": "Space Explorers",
        "location_type": "home",
    }
    body.update(overrides)
    return body


def booking_body(session: str, total_cost: float) -> dict:
    return {
        "session_id": session,
        "name": "Journey Parent",
        "contact_email": "organizer@example.com",
        "notes": "E2E lifecycle booking",
        "party": {"party_date": FUTURE, "guest_count": 12, "budget": 800.0,
                  "total_cost": total_cost, "theme": "Space Explorers",
                  "location_type": "home"},
    }


async def test_j1_full_lifecycle_plan_to_booking_to_summary():
    """Plan -> book to the session cap -> summary reflects pipeline GBV."""
    session = "session-e2e-client-777"
    async with _client() as client:
        res = await client.get("/health")
        assert res.status_code == 200 and res.json()["status"] == "ok"

        plan_res = await client.post("/api/v1/plan", json=plan_body())
        assert plan_res.status_code == 200
        plan = plan_res.json()
        assert plan["status"] == "verified"
        assert plan["verification"]["passed"] is True
        total = plan["plan"]["total_cost"]
        assert 0 < total <= 800.0

        # Book up to the per-session cap (anti-double-booking flood guard).
        refs = set()
        for _ in range(settings.BOOKINGS_MAX_PER_SESSION):
            r = await client.post("/api/v1/bookings", json=booking_body(session, total))
            assert r.status_code == 201
            body = r.json()
            assert body["status"] == "received"
            assert body["booking_ref"].startswith("IP-")
            refs.add(body["booking_ref"])
        assert len(refs) == settings.BOOKINGS_MAX_PER_SESSION  # refs never collide

        over_cap = await client.post("/api/v1/bookings", json=booking_body(session, total))
        assert over_cap.status_code == 429
        assert over_cap.json()["detail"]["error"] == "too_many_bookings"

        summary = (await client.get("/api/v1/bookings/summary")).json()
        assert summary["total_bookings"] == settings.BOOKINGS_MAX_PER_SESSION
        assert summary["unique_sessions"] == 1
        expected_gbv = round(total * settings.BOOKINGS_MAX_PER_SESSION, 2)
        assert summary["gbv_pipeline"] == pytest.approx(expected_gbv, abs=0.01)
        assert summary["est_take_revenue"] == pytest.approx(
            round(expected_gbv * settings.COMMISSION_RATE, 2), abs=0.01
        )


async def test_j2_infeasible_budget_refused_honestly_then_recovered():
    """The 409 carries the minimum feasible budget; retrying with it succeeds."""
    async with _client() as client:
        refusal = await client.post("/api/v1/plan", json=plan_body(guests=100, budget=10.0))
        assert refusal.status_code == 409
        detail = refusal.json()["detail"]
        assert detail["error"] == "no_valid_plan"
        minimum = detail["minimum_feasible_budget"]
        assert minimum is not None and minimum > 10.0
        assert any(v["code"] == "BUDGET_INFEASIBLE" for v in detail["violations"])

        recovery = await client.post("/api/v1/plan", json=plan_body(guests=100, budget=minimum))
        assert recovery.status_code == 200
        assert recovery.json()["status"] == "verified"


async def test_j3_unverifiable_dietary_need_fails_closed_with_zero_llm_calls():
    async with _client() as client:
        res = await client.post(
            "/api/v1/plan", json=plan_body(dietary_restrictions="strictly halal")
        )
        assert res.status_code == 409
        detail = res.json()["detail"]
        assert any(v["code"] == "DIETARY_UNVERIFIABLE" for v in detail["violations"])
        assert detail["telemetry"]["llm_calls"] == 0  # refused before any model spend


@pytest.mark.parametrize("mutation", [
    {"guest_count": 0},
    {"guest_count": 501},
    {"budget": -5000.0},
    {"budget": 10_000_000.0},
    {"party_date": "1999-01-01"},
    {"honoree_age": 0},
    {"honoree_name": ""},
    {"location_type": "moon"},
])
async def test_j4_malformed_requests_get_422_never_500(mutation):
    async with _client() as client:
        res = await client.post("/api/v1/plan", json=plan_body(**mutation))
        assert res.status_code == 422, f"{mutation} -> {res.status_code}"


async def test_j5_dead_backend_maps_to_503_planning_unavailable(monkeypatch):
    class DeadClient:
        name = "dead"

        async def generate_draft(self, request, catalog, temperature=0.5, feedback=None):
            raise MalformedPlanError("backend hard down")

    monkeypatch.setattr(routes, "_client", DeadClient())
    monkeypatch.setattr(routes, "_orchestrator", TTLOrchestrator(name="e2e-dead"))
    async with _client() as client:
        res = await client.post("/api/v1/plan", json=plan_body())
        assert res.status_code == 503
        assert res.json()["detail"]["error"] == "planning_unavailable"


async def test_j6_product_funnel_dedupes_sessions_end_to_end():
    session = "session-funnel-0001"
    async with _client() as client:
        for name in ("page_view", "form_started", "plan_requested",
                     "plan_verified", "plan_verified", "booking_interest"):
            r = await client.post("/api/v1/events", json={"session_id": session, "event": name})
            assert r.status_code == 204
        summary = (await client.get("/api/v1/events/summary")).json()
        assert summary["total_events"] == 6
        funnel = summary["funnel_unique_sessions"]
        # One real session end to end: every stage counts it exactly once,
        # even though plan_verified fired twice.
        assert funnel == {"page_view": 1, "form_started": 1,
                          "plan_requested": 1, "plan_verified": 1}
        assert summary["conversion"]["request_to_verified"] == 1.0
        assert summary["booking_interest_sessions"] == 1
        assert summary["booking_interest_rate"] == 1.0
