"""Gap partitions — MECE complement to the 100-profile matrix, the E2E
journeys, and the adversarial file. Each class here owns territory none of the
other suites (old or new) touch:

  G1  feasibility EXACTNESS   budget == minimum passes; one cent under refuses
  G2  verifier partitions     age, schedule, exact serving/place-setting bounds
  G3  rate limiter mechanics  burst, refill, and bucket-memory bounding
  G4  email gate unit edges   length limits and subdomain disposables
"""
from __future__ import annotations

import time
from datetime import date, timedelta

import pytest

from iparty.core.emailcheck import validate_email_address
from iparty.core.exceptions import NoValidPlanError
from iparty.core.ratelimit import RateLimiter
from iparty.llm.client import MockClient
from iparty.orchestration.ttl_engine import TTLOrchestrator
from iparty.planning.feasibility import cheapest_compliant_draft, minimum_feasible_budget
from iparty.planning.grounding import ground_draft
from iparty.planning.models import PartyRequest, ScheduleSlot
from iparty.planning.planner import TTLPartyPlanner
from iparty.planning.verifier import verify_plan
from iparty.pricing.catalog import StaticCatalog

FUTURE = date.today() + timedelta(days=45)
CATALOG = StaticCatalog()


def request_for(guests: int, budget: float, **overrides) -> PartyRequest:
    body = dict(honoree_name="Boundary Kid", honoree_age=8, party_date=FUTURE,
                guest_count=guests, budget=budget, theme="Boundary",
                location_type="home")
    body.update(overrides)
    return PartyRequest(**body)


# ---------------------------------------------------------------------------
# G1. Feasibility boundary exactness
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("guests", [1, 15, 16, 17, 100, 350, 500])
async def test_budget_equal_to_minimum_is_feasible_one_cent_under_is_not(guests):
    probe = request_for(guests, 1_000_000.0)
    minimum = minimum_feasible_budget(probe, CATALOG)
    assert minimum is not None and minimum > 0

    planner = TTLPartyPlanner(MockClient(seed=guests), StaticCatalog(),
                              TTLOrchestrator(name=f"gap-exact-{guests}"))
    result = await planner.plan(request_for(guests, minimum))
    assert result.status == "verified"
    assert result.plan.total_cost <= minimum + 0.01

    with pytest.raises(NoValidPlanError) as exc_info:
        await planner.plan(request_for(guests, round(minimum - 0.01, 2)))
    assert exc_info.value.minimum_feasible_budget == pytest.approx(minimum, abs=0.01)


def test_minimum_budget_is_monotone_in_guest_count():
    """More guests can never make the cheapest compliant party cheaper."""
    minima = [minimum_feasible_budget(request_for(g, 1_000_000.0), CATALOG)
              for g in (1, 10, 50, 100, 250, 500)]
    assert all(m is not None for m in minima)
    assert minima == sorted(minima)


# ---------------------------------------------------------------------------
# G2. Verifier partitions the other suites never trip
# ---------------------------------------------------------------------------
def _grounded_baseline(guests: int, honoree_age: int = 8):
    req = request_for(guests, 5_000.0, honoree_age=honoree_age)
    draft = cheapest_compliant_draft(req, CATALOG)
    assert draft is not None
    return req, draft


def test_age_inappropriate_activity_is_a_hard_error():
    """A bounce house (ages 3-12) must fail verification for a 30-year-old."""
    req, draft = _grounded_baseline(guests=20, honoree_age=30)
    draft = draft.model_copy(update={"activities": [
        type(draft.activities[0])(sku="ACT-BOUNCE", quantity=1)
    ]})
    plan = ground_draft(draft, CATALOG, req.guest_count)
    report = verify_plan(plan, req, CATALOG)
    assert not report.passed
    assert any(v.code == "AGE_INAPPROPRIATE" for v in report.violations)


def test_non_monotonic_schedule_is_a_hard_error():
    req, draft = _grounded_baseline(guests=12)
    draft = draft.model_copy(update={"schedule": [
        ScheduleSlot(start="15:00", end="16:00", activity="Cake"),
        ScheduleSlot(start="14:00", end="15:30", activity="Games"),  # overlaps backwards
    ]})
    plan = ground_draft(draft, CATALOG, req.guest_count)
    report = verify_plan(plan, req, CATALOG)
    assert not report.passed
    assert any(v.code == "SCHEDULE_NOT_MONOTONIC" for v in report.violations)


def test_backwards_single_slot_is_a_hard_error():
    req, draft = _grounded_baseline(guests=12)
    draft = draft.model_copy(update={"schedule": [
        ScheduleSlot(start="16:00", end="14:00", activity="Time travel"),
        ScheduleSlot(start="16:30", end="17:00", activity="Goodbyes"),
    ]})
    plan = ground_draft(draft, CATALOG, req.guest_count)
    report = verify_plan(plan, req, CATALOG)
    assert not report.passed
    assert any(v.code == "SCHEDULE_NOT_MONOTONIC" for v in report.violations)


def test_food_servings_boundary_exact_cover_passes_one_short_fails():
    """FD-VEGGIE serves 12/unit: 2 units == 24 guests passes; 23 servings can't
    happen, so drop to 1 unit (12) for 24 guests and the verifier must flag it."""
    req, draft = _grounded_baseline(guests=24)
    veggie_only = [s for s in draft.food if s.sku]  # copy shape
    sel_cls = type(veggie_only[0]) if veggie_only else None
    assert sel_cls is not None

    exact = draft.model_copy(update={"food": [sel_cls(sku="FD-VEGGIE", quantity=2)]})
    plan = ground_draft(exact, CATALOG, req.guest_count)
    report = verify_plan(plan, req, CATALOG)
    assert not any(v.code == "FOOD_UNDERSCALED" for v in report.violations)

    short = draft.model_copy(update={"food": [sel_cls(sku="FD-VEGGIE", quantity=1)]})
    plan = ground_draft(short, CATALOG, req.guest_count)
    report = verify_plan(plan, req, CATALOG)
    assert not report.passed
    assert any(v.code == "FOOD_UNDERSCALED" for v in report.violations)


def test_supplies_place_settings_boundary_exact_cover_passes_one_pack_short_fails():
    """SUP-BASIC covers 16/pack: 2 packs == 32 guests passes; 1 pack fails."""
    req, draft = _grounded_baseline(guests=32)
    sel_cls = type(draft.supplies[0])

    exact = draft.model_copy(update={"supplies": [sel_cls(sku="SUP-BASIC", quantity=2)]})
    report = verify_plan(ground_draft(exact, CATALOG, req.guest_count), req, CATALOG)
    assert not any(v.code == "SUPPLIES_UNDERSCALED" for v in report.violations)

    short = draft.model_copy(update={"supplies": [sel_cls(sku="SUP-BASIC", quantity=1)]})
    report = verify_plan(ground_draft(short, CATALOG, req.guest_count), req, CATALOG)
    assert not report.passed
    assert any(v.code == "SUPPLIES_UNDERSCALED" for v in report.violations)


def test_decor_only_supplies_cannot_satisfy_place_settings():
    """SUP-DECOR (serves=0) is pure decor: alone it must fail the coverage check."""
    req, draft = _grounded_baseline(guests=10)
    sel_cls = type(draft.supplies[0])
    decor = draft.model_copy(update={"supplies": [sel_cls(sku="SUP-DECOR", quantity=3)]})
    report = verify_plan(ground_draft(decor, CATALOG, req.guest_count), req, CATALOG)
    assert not report.passed
    assert any(v.code == "SUPPLIES_UNDERSCALED" for v in report.violations)


# ---------------------------------------------------------------------------
# G3. Rate limiter mechanics (unit level — untested anywhere else)
# ---------------------------------------------------------------------------
def test_burst_is_honored_then_exhausted():
    rl = RateLimiter()
    allowed = [rl.allow("k", rate_per_min=60, burst=3) for _ in range(5)]
    assert allowed == [True, True, True, False, False]


def test_tokens_refill_over_time():
    rl = RateLimiter()
    assert rl.allow("k", rate_per_min=600, burst=1)      # drain the bucket
    assert not rl.allow("k", rate_per_min=600, burst=1)  # immediately denied
    time.sleep(0.12)                                     # 600/min = 10/s -> ~1.2 tokens
    assert rl.allow("k", rate_per_min=600, burst=1)


def test_bucket_memory_is_bounded_under_key_flood():
    rl = RateLimiter()
    for i in range(100_001):
        rl.allow(f"flood-{i}", rate_per_min=60, burst=1)
    assert len(rl._buckets) <= 50_001  # eviction kept the map bounded


def test_keys_are_isolated():
    rl = RateLimiter()
    assert rl.allow("a", rate_per_min=60, burst=1)
    assert not rl.allow("a", rate_per_min=60, burst=1)
    assert rl.allow("b", rate_per_min=60, burst=1)  # a's exhaustion never leaks to b


# ---------------------------------------------------------------------------
# G4. Email gate unit edges beyond the adversarial matrix
# ---------------------------------------------------------------------------
def test_length_limits_enforced():
    assert not validate_email_address(("x" * 65) + "@example.com")     # local > 64
    assert not validate_email_address("user@" + ("d" * 250) + ".com")  # total > 254
    assert validate_email_address(("x" * 64) + "@example.com")


def test_disposable_check_is_exact_never_fuzzy():
    # Similar-looking but NOT listed domains must pass: no fuzzy overblocking.
    assert validate_email_address("user@mailinator-fans.com")
    assert validate_email_address("user@tempmailer-review.org")
    # Any depth of subdomain under a listed domain is still disposable.
    assert not validate_email_address("user@a.b.yopmail.com")
