"""Property-based tests (Hypothesis) — break the circular 'mock tests verifier'
problem by asserting invariants over RANDOM inputs the author never hand-picked."""
from datetime import date, timedelta

from hypothesis import given, settings, strategies as st

from iparty.pricing.catalog import ALLERGENS, StaticCatalog
from iparty.planning.grounding import ground_draft
from iparty.planning.models import PartyRequest, PlanDraft, ScheduleSlot, Selection
from iparty.planning.verifier import verify_plan

CAT = StaticCatalog()
FOOD_SKUS = [i.sku for i in CAT.by_category("food")]
ACT_SKUS = [i.sku for i in CAT.by_category("activities")]
SUP_SKUS = [i.sku for i in CAT.by_category("supplies")]
VEN_SKUS = [i.sku for i in CAT.by_category("venue")]


def _sched():
    return [ScheduleSlot(start="14:00", end="15:00", activity="a"),
            ScheduleSlot(start="15:00", end="16:00", activity="b")]


@settings(max_examples=200, deadline=None)
@given(
    guests=st.integers(min_value=1, max_value=60),
    budget=st.floats(min_value=10, max_value=3000),
    food=st.lists(st.tuples(st.sampled_from(FOOD_SKUS), st.integers(1, 6)), min_size=1, max_size=4),
    venue=st.sampled_from(VEN_SKUS),
    act=st.sampled_from(ACT_SKUS),
)
def test_invariant_overbudget_always_fails(guests, budget, food, venue, act):
    req = PartyRequest(honoree_name="P", honoree_age=7,
                       party_date=date.today() + timedelta(days=10),
                       guest_count=guests, budget=budget)
    draft = PlanDraft(theme="t", venue_sku=venue,
                      food=[Selection(sku=s, quantity=q) for s, q in food],
                      supplies=[Selection(sku="SUP-BASIC", quantity=1)],
                      activities=[Selection(sku=act, quantity=1)],
                      schedule=_sched())
    plan = ground_draft(draft, CAT, guests)
    report = verify_plan(plan, req, CAT)
    # INVARIANT: a passing plan must never exceed budget.
    if report.passed:
        assert plan.total_cost <= req.budget + 0.01


@settings(max_examples=200, deadline=None)
@given(
    guests=st.integers(min_value=1, max_value=40),
    allergen=st.sampled_from(sorted(ALLERGENS)),
    food=st.lists(st.sampled_from(FOOD_SKUS), min_size=1, max_size=4),
)
def test_invariant_passing_plan_is_allergen_safe(guests, allergen, food):
    # Map the raw allergen back to a restriction phrase the parser understands.
    phrase = {"peanut": "peanut", "tree_nut": "tree nut", "wheat": "gluten",
              "milk": "dairy", "egg": "egg", "soy": "soy", "fish": "fish",
              "shellfish": "shellfish", "sesame": "sesame"}[allergen]
    req = PartyRequest(honoree_name="P", honoree_age=7,
                       party_date=date.today() + timedelta(days=10),
                       guest_count=guests, budget=5000, dietary_restrictions=phrase)
    draft = PlanDraft(theme="t", venue_sku="VEN-HOME",
                      food=[Selection(sku=s, quantity=3) for s in food],
                      supplies=[Selection(sku="SUP-BASIC", quantity=1)],
                      activities=[Selection(sku="ACT-GAMES", quantity=1)],
                      schedule=_sched())
    plan = ground_draft(draft, CAT, guests)
    report = verify_plan(plan, req, CAT)
    # INVARIANT: if the plan passes, no served menu item may contain the allergen.
    if report.passed:
        for m in plan.menu:
            assert allergen not in m.allergens
