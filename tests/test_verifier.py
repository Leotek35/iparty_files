from datetime import date, timedelta

from iparty.pricing.catalog import StaticCatalog
from iparty.planning.feasibility import cheapest_compliant_draft
from iparty.planning.grounding import ground_draft
from iparty.planning.models import PartyRequest
from iparty.planning.verifier import verify_plan

CAT = StaticCatalog()


def _req(budget=500, guests=10, diet="", age=7):
    return PartyRequest(honoree_name="Sam", honoree_age=age,
                        party_date=date.today() + timedelta(days=20),
                        guest_count=guests, budget=budget, theme="Dinosaurs",
                        dietary_restrictions=diet)


def _grounded_cheapest(req):
    return ground_draft(cheapest_compliant_draft(req, CAT), CAT, req.guest_count)


def test_cheapest_plan_passes():
    req = _req(budget=500)
    report = verify_plan(_grounded_cheapest(req), req, CAT)
    assert report.passed, [v.code for v in report.violations]


def test_over_budget_fails():
    req = _req(budget=20, guests=30)  # impossible on $20
    report = verify_plan(_grounded_cheapest(req), req, CAT)
    assert not report.passed
    assert any(v.code == "BUDGET_EXCEEDED" for v in report.violations)
