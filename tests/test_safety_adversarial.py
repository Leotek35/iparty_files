"""Adversarial tests written INDEPENDENTLY of the mock — these encode the
attacks that broke the previous version, so they can never silently regress."""
from datetime import date, timedelta

from iparty.pricing.catalog import StaticCatalog
from iparty.planning.grounding import ground_draft
from iparty.planning.models import PartyRequest, PlanDraft, ScheduleSlot, Selection
from iparty.planning.verifier import verify_plan

CAT = StaticCatalog()


def _req(diet="", guests=10, age=7, budget=600):
    return PartyRequest(honoree_name="Test", honoree_age=age,
                        party_date=date.today() + timedelta(days=20),
                        guest_count=guests, budget=budget, dietary_restrictions=diet)


def _sched():
    return [ScheduleSlot(start="14:00", end="15:00", activity="games"),
            ScheduleSlot(start="15:00", end="16:00", activity="cake")]


def test_peanut_dish_fails_nut_allergy():
    """The exact attack that passed before: a peanut item under a nut allergy."""
    req = _req(diet="severe nut allergy", guests=10)
    draft = PlanDraft(theme="t", venue_sku="VEN-HOME",
                      food=[Selection(sku="FD-PBJ", quantity=2)],  # PB&J = peanut
                      supplies=[Selection(sku="SUP-BASIC", quantity=1)],
                      activities=[Selection(sku="ACT-GAMES", quantity=1)],
                      schedule=_sched())
    report = verify_plan(ground_draft(draft, CAT, req.guest_count), req, CAT)
    assert not report.passed
    assert any(v.code == "ALLERGEN_VIOLATION" for v in report.violations)


def test_gluten_free_rejects_wheat_cake():
    req = _req(diet="gluten-free", guests=10)
    draft = PlanDraft(theme="t", venue_sku="VEN-HOME",
                      food=[Selection(sku="FD-CAKE", quantity=1)],  # regular cake = wheat
                      supplies=[Selection(sku="SUP-BASIC", quantity=1)],
                      activities=[Selection(sku="ACT-GAMES", quantity=1)],
                      schedule=_sched())
    report = verify_plan(ground_draft(draft, CAT, req.guest_count), req, CAT)
    assert not report.passed
    assert any(v.code == "ALLERGEN_VIOLATION" for v in report.violations)


def test_hallucinated_price_is_rejected():
    """Tamper a line item's price; realizability check must catch it."""
    req = _req(guests=10)
    plan = ground_draft(PlanDraft(theme="t", venue_sku="VEN-HOME",
                                  food=[Selection(sku="FD-FRUIT", quantity=1)],
                                  supplies=[Selection(sku="SUP-BASIC", quantity=1)],
                                  activities=[Selection(sku="ACT-GAMES", quantity=1)],
                                  schedule=_sched()), CAT, req.guest_count)
    # Hallucinate: pretend the fruit cost $0.01
    plan.line_items[1].subtotal = 0.01
    report = verify_plan(plan, req, CAT)
    assert not report.passed
    assert any(v.code == "PRICE_MISMATCH" for v in report.violations)


def test_unknown_sku_is_rejected():
    req = _req(guests=10)
    draft = PlanDraft(theme="t", venue_sku="VEN-HOME",
                      food=[Selection(sku="FD-FANTASY-UNICORN", quantity=1)],
                      supplies=[Selection(sku="SUP-BASIC", quantity=1)],
                      activities=[Selection(sku="ACT-GAMES", quantity=1)],
                      schedule=_sched())
    report = verify_plan(ground_draft(draft, CAT, req.guest_count), req, CAT)
    assert not report.passed
    assert any(v.code in ("UNREALIZABLE_SKU", "REALIZABLE") for v in report.violations)
