"""100-user-profile MECE matrix — the whole demand spectrum in one table.

Seven mutually exclusive partitions that together cover the market the app
can meet (collectively exhaustive by construction):

  1. diy       (001-015)  budget & DIY at-home parties
  2. luxury    (016-030)  high-budget / VIP events
  3. milestone (031-045)  weddings, quinceaneras, mitzvahs, anniversaries
  4. micro     (046-060)  micro-events, studios, pop-ups
  5. tech      (061-076)  tech & gaming events
  6. cultural  (077-090)  cultural & dietary-constrained events
  7. fuzz      (091-100)  boundary, fuzzing & adversarial inputs

Each profile runs the REAL pipeline end to end: request validation
(PartyRequest) -> feasibility precheck -> verified best-of-N planning against
the grounded catalog -> plan-level invariants. Expectations:

  pass             request validates and a VERIFIED plan is produced
  pass_sanitized   as `pass`, plus hostile text is neutralised (data, not code)
  validation_error the request is rejected at the model boundary
  feasibility_error the planner refuses honestly with the minimum budget
  email_error      the contact email is rejected by the email gate
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from iparty.core.emailcheck import validate_email_address
from iparty.core.exceptions import NoValidPlanError
from iparty.llm.client import MockClient
from iparty.orchestration.ttl_engine import TTLOrchestrator
from iparty.planning.planner import TTLPartyPlanner
from iparty.pricing.catalog import StaticCatalog

from .mece_profiles import FUTURE, PROFILES_MECE, build_request  # noqa: F401


def _fresh_planner(profile_id: str) -> tuple[TTLPartyPlanner, StaticCatalog]:
    """Deterministic, isolated pipeline per profile: no cross-profile state."""
    catalog = StaticCatalog()
    planner = TTLPartyPlanner(
        MockClient(seed=int(profile_id)), catalog, TTLOrchestrator(name=f"mece-{profile_id}")
    )
    return planner, catalog


def test_profiles_are_mutually_exclusive():
    """MECE property: 100 unique IDs, each in exactly one of the 7 partitions."""
    ids = [p["id"] for p in PROFILES_MECE]
    assert len(ids) == len(set(ids)) == 100, "Profile IDs must be unique and total 100."
    categories = {p["cat"] for p in PROFILES_MECE}
    assert categories == {"diy", "luxury", "milestone", "micro", "tech", "cultural", "fuzz"}
    sizes = {c: sum(1 for p in PROFILES_MECE if p["cat"] == c) for c in categories}
    assert sum(sizes.values()) == 100  # collectively exhaustive over the table


def test_expectation_labels_are_a_closed_set():
    allowed = {"pass", "pass_sanitized", "validation_error", "feasibility_error", "email_error"}
    assert {p["expect"] for p in PROFILES_MECE} <= allowed


@pytest.mark.parametrize("p", PROFILES_MECE, ids=[f"ID-{p['id']}-{p['cat']}" for p in PROFILES_MECE])
async def test_mece_profile_execution_matrix(p):
    expect = p["expect"]

    # 1. Email gate (profiles that carry a contact email)
    if "email" in p:
        valid_email = validate_email_address(p["email"])
        if expect == "email_error":
            assert not valid_email, f"Profile {p['id']} allowed invalid email: {p['email']}"
            return
        assert valid_email, f"Profile {p['id']} rejected a legitimate email: {p['email']}"

    # 2. Request-model validation
    try:
        req = build_request(p)
    except (ValueError, ValidationError):
        assert expect == "validation_error", f"Profile {p['id']} raised unexpected validation error."
        return
    assert expect != "validation_error", f"Profile {p['id']} should have been rejected at validation."

    # 3. Feasibility + verified planning (the real pipeline, mock backend)
    planner, catalog = _fresh_planner(p["id"])
    try:
        result = await planner.plan(req)
    except NoValidPlanError as exc:
        assert expect == "feasibility_error", (
            f"Profile {p['id']} was refused unexpectedly: {exc.message} {exc.violations}"
        )
        assert exc.minimum_feasible_budget is not None
        assert exc.minimum_feasible_budget > req.budget
        return
    assert expect != "feasibility_error", f"Profile {p['id']} passed feasibility but should have failed."

    # 4. Verified-plan invariants: budget, scaling, and catalog grounding
    assert result.status == "verified" and result.verification.passed
    plan = result.plan
    assert plan.total_cost <= req.budget + 0.01, f"Profile {p['id']} plan exceeds budget."
    assert sum(m.servings for m in plan.menu) >= req.guest_count
    for li in plan.line_items:
        item = catalog.get(li.sku)
        assert item is not None, f"Catalog grounding failed: unknown SKU {li.sku} in profile {p['id']}"
        assert abs(item.price_for(li.quantity, req.guest_count) - li.subtotal) <= 0.01

    # 5. Hostile text stays data: control chars stripped, content not executed
    if expect == "pass_sanitized":
        assert "\x00" not in req.theme and "\x00" not in plan.theme
        if p["id"] == "094":
            # SQL-looking text survives untouched as inert data.
            assert plan.theme == p["theme"]
        if p["id"] == "095":
            assert "🎉" in plan.theme  # legitimate unicode/emoji preserved
