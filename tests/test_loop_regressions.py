"""Regression tests from agentic loop iterations. Each test encodes a defect the
critic found, so it can never silently return."""
import asyncio
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from iparty.api.app import create_app
from iparty.orchestration.ttl_engine import TTLOrchestrator
from iparty.pricing.catalog import StaticCatalog, parse_forbidden_allergens
from iparty.planning.grounding import ground_draft
from iparty.planning.models import PartyRequest, PlanDraft, ScheduleSlot, Selection
from iparty.planning.planner import TTLPartyPlanner
from iparty.planning.verifier import verify_plan

CAT = StaticCatalog()


def _sched():
    return [ScheduleSlot(start="14:00", end="15:00", activity="g"),
            ScheduleSlot(start="15:00", end="16:00", activity="c")]


# ---- LOOP 1, DEFECT 1: vegan must forbid animal-derived allergens ----
def test_vegan_maps_to_animal_allergens():
    assert {"milk", "egg"} <= parse_forbidden_allergens("vegan")


def test_egg_milk_cake_fails_vegan_request():
    req = PartyRequest(honoree_name="V", honoree_age=7,
                       party_date=date.today() + timedelta(days=10),
                       guest_count=10, budget=800, dietary_restrictions="vegan")
    d = PlanDraft(theme="t", venue_sku="VEN-HOME",
                  food=[Selection(sku="FD-CAKE", quantity=1)],  # wheat, egg, milk
                  supplies=[Selection(sku="SUP-BASIC", quantity=1)],
                  activities=[Selection(sku="ACT-GAMES", quantity=1)],
                  schedule=_sched())
    r = verify_plan(ground_draft(d, CAT, 10), req, CAT)
    assert not r.passed
    assert any(v.code == "ALLERGEN_VIOLATION" for v in r.violations)


def test_vegan_request_still_plannable():
    """FD-CAKE-VG / fruit / veggie exist, so vegan must remain feasible."""
    from iparty.planning.feasibility import cheapest_compliant_draft
    req = PartyRequest(honoree_name="V", honoree_age=7,
                       party_date=date.today() + timedelta(days=10),
                       guest_count=10, budget=800, dietary_restrictions="vegan")
    draft = cheapest_compliant_draft(req, CAT)
    assert draft is not None
    r = verify_plan(ground_draft(draft, CAT, 10), req, CAT)
    assert r.passed, [v.code for v in r.violations]


# ---- LOOP 1, DEFECT 2: status-code contract is unambiguous ----
def test_status_contract_409_vs_422():
    c = TestClient(create_app())
    # pydantic-invalid -> 422, detail is a LIST
    p = c.post("/api/v1/plan", json={"honoree_name": "X"})
    assert p.status_code == 422 and isinstance(p.json()["detail"], list)
    # infeasible -> 409, detail is a DICT with minimum_feasible_budget
    i = c.post("/api/v1/plan", json={
        "honoree_name": "Z", "honoree_age": 7,
        "party_date": (date.today() + timedelta(days=9)).isoformat(),
        "guest_count": 60, "budget": 3, "theme": "",
        "dietary_restrictions": "", "location_type": "home"})
    assert i.status_code == 409
    assert isinstance(i.json()["detail"], dict)
    assert i.json()["detail"]["minimum_feasible_budget"] > 3


# ---- LOOP 1, DEFECT 3: one flaky provider call must not abort the request ----
class FlakyThenGoodLLM:
    """Fails twice, then delegates to the real mock — best-of-N must recover."""
    name = "flaky"

    def __init__(self):
        from iparty.llm.client import MockClient
        self._inner = MockClient(flaw_rate=0.0)
        self.calls = 0

    async def generate_draft(self, request, catalog, temperature=0.5, feedback=None):
        self.calls += 1
        if self.calls <= 2:
            raise RuntimeError("transient provider blip")
        return await self._inner.generate_draft(request, catalog, temperature, feedback=feedback)


@pytest.mark.asyncio
async def test_transient_provider_errors_are_retried():
    req = PartyRequest(honoree_name="F", honoree_age=7,
                       party_date=date.today() + timedelta(days=9),
                       guest_count=10, budget=500)
    planner = TTLPartyPlanner(FlakyThenGoodLLM(), CAT,
                              TTLOrchestrator("flaky-test"))
    result = await planner.plan(req)          # must NOT raise RuntimeError
    assert result.status == "verified"
    assert any("produce error" in e for e in result.telemetry["pattern_log"])


@pytest.mark.asyncio
async def test_dead_provider_yields_clean_exhaustion():
    from iparty.core.exceptions import RetryExhaustedError

    class DeadLLM:
        name = "dead"
        async def generate_draft(self, *a, **k):
            raise RuntimeError("provider down")

    req = PartyRequest(honoree_name="D", honoree_age=7,
                       party_date=date.today() + timedelta(days=9),
                       guest_count=10, budget=500)
    with pytest.raises(RetryExhaustedError):
        await TTLPartyPlanner(DeadLLM(), CAT, TTLOrchestrator("dead-test")).plan(req)


# ---- LOOP 2, DEFECT 4: supplies must scale with guest count ----
def test_single_pack_fails_200_guests():
    req = PartyRequest(honoree_name="Big", honoree_age=10,
                       party_date=date.today() + timedelta(days=30),
                       guest_count=200, budget=4000)
    d = PlanDraft(theme="t", venue_sku="VEN-HOME",
                  food=[Selection(sku="FD-PIZZA", quantity=1)],       # per_person, covers all
                  supplies=[Selection(sku="SUP-BASIC", quantity=1)],  # 16 settings only
                  activities=[Selection(sku="ACT-GAMES", quantity=1)],
                  schedule=_sched())
    r = verify_plan(ground_draft(d, CAT, 200), req, CAT)
    assert not r.passed
    assert any(v.code == "SUPPLIES_UNDERSCALED" for v in r.violations)


def test_big_party_end_to_end_supplies_scale():
    c = TestClient(create_app())
    r = c.post("/api/v1/plan", json={
        "honoree_name": "Big", "honoree_age": 10,
        "party_date": (date.today() + timedelta(days=30)).isoformat(),
        "guest_count": 200, "budget": 4000, "theme": "Carnival",
        "dietary_restrictions": "", "location_type": "park"})
    assert r.status_code == 200, r.text
    plan = r.json()["plan"]
    capacity = 0
    for li in plan["line_items"]:
        if li["category"] != "supplies":
            continue
        item = CAT.get(li["sku"])
        capacity += 200 if item.unit == "per_person" else item.serves * li["quantity"]
    assert capacity >= 200


# ---- LOOP 4, UPGRADE 1: infeasible requests cost ZERO LLM calls ----
@pytest.mark.asyncio
async def test_feasibility_precheck_spends_no_llm_calls():
    class CountingLLM:
        name = "counting"
        calls = 0
        async def generate_draft(self, *a, **k):
            CountingLLM.calls += 1
            raise AssertionError("must not be called for infeasible request")
    from iparty.core.exceptions import NoValidPlanError
    req = PartyRequest(honoree_name="Z", honoree_age=7,
                       party_date=date.today() + timedelta(days=9),
                       guest_count=60, budget=3)
    with pytest.raises(NoValidPlanError) as ei:
        await TTLPartyPlanner(CountingLLM(), CAT, TTLOrchestrator("pre")).plan(req)
    assert CountingLLM.calls == 0
    assert ei.value.telemetry.get("llm_calls") == 0
    assert ei.value.minimum_feasible_budget > 3


# ---- LOOP 4, UPGRADE 2: HALF_OPEN admits exactly one probe ----
@pytest.mark.asyncio
async def test_half_open_single_probe():
    from iparty.orchestration.ttl_engine import CircuitBreaker
    cb = CircuitBreaker(name="probe-test", failure_threshold=2, cooldown_seconds=0.03)
    hits = {"n": 0}
    async def failing():
        hits["n"] += 1
        await asyncio.sleep(0.02)
        raise ValueError("down")
    for _ in range(2):
        with pytest.raises(ValueError):
            await cb.call(failing)
    await asyncio.sleep(0.04)
    hits["n"] = 0
    async def attempt():
        try:
            await cb.call(failing)
        except Exception:
            pass
    await asyncio.gather(*[attempt() for _ in range(20)])
    assert hits["n"] == 1  # exactly one probe reaches the provider


# ---- LOOP 4, UPGRADE 3: overall request deadline bounds latency ----
@pytest.mark.asyncio
async def test_request_deadline_bounds_latency():
    import time
    orch = TTLOrchestrator("deadline-test")
    async def slow(i):
        await asyncio.sleep(0.05)
        return i
    t0 = time.monotonic()
    _, tel = await orch.run_verified(slow, lambda v: (False, 0.1, None),
                                     n=100, consecutive_fail_limit=999,
                                     deadline_seconds=0.12)
    assert time.monotonic() - t0 < 1.0
    assert any("deadline" in e for e in tel.pattern_log)


# ---- LOOP 4, UPGRADE 4: verifier feedback reaches the model ----
@pytest.mark.asyncio
async def test_verifier_feedback_is_passed_to_model():
    from iparty.llm.client import MockClient

    seen = {"feedback": None}

    class SpyMock(MockClient):
        async def generate_draft(self, request, catalog, temperature=0.5, feedback=None):
            if feedback is not None:
                seen["feedback"] = feedback
            return await super().generate_draft(request, catalog, temperature, feedback=feedback)

    req = PartyRequest(honoree_name="R", honoree_age=7,
                       party_date=date.today() + timedelta(days=9),
                       guest_count=12, budget=300)
    # flaw_rate=1.0: first candidate always violates budget -> feedback must flow
    result = await TTLPartyPlanner(SpyMock(flaw_rate=1.0), CAT,
                                   TTLOrchestrator("fb")).plan(req)
    assert result.status == "verified"
    assert seen["feedback"] and "BUDGET_EXCEEDED" in seen["feedback"]
    assert result.telemetry["llm_calls"] == 2  # fail once, repair once
