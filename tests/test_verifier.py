from datetime import date, timedelta

from iparty.planning.models import LineItem, MenuItem, PartyPlan, PartyRequest, ScheduleSlot
from iparty.planning.verifier import verify_plan


def _req(budget=500, guests=10, diet=""):
    return PartyRequest(
        honoree_name="Sam", honoree_age=7, party_date=date.today() + timedelta(days=20),
        guest_count=guests, budget=budget, theme="Dinosaurs", dietary_restrictions=diet,
    )


def _good_plan(req):
    return PartyPlan(
        theme="Dinosaurs", venue="Backyard",
        line_items=[
            LineItem(category="venue", description="home", quantity=1, unit_cost=0),
            LineItem(category="food", description="catering", quantity=req.guest_count, unit_cost=10),
            LineItem(category="supplies", description="supplies", quantity=1, unit_cost=80),
            LineItem(category="activities", description="games", quantity=1, unit_cost=120),
        ],
        menu=[MenuItem(name="cake", servings=req.guest_count + 4, dietary_tags=[])],
        schedule=[ScheduleSlot(start="14:00", end="15:00", activity="games"),
                  ScheduleSlot(start="15:00", end="16:00", activity="cake")],
        activities=["treasure hunt"], supplies=["plates", "cups"], notes="",
    )


def test_good_plan_passes():
    req = _req()
    report = verify_plan(_good_plan(req), req)
    assert report.passed
    assert report.score == 1.0 or report.checks_passed >= report.checks_total - 1


def test_over_budget_fails():
    req = _req(budget=100)
    plan = _good_plan(_req(budget=500))  # ~300 cost vs 100 budget
    report = verify_plan(plan, req)
    assert not report.passed
    assert any(v.code == "BUDGET_EXCEEDED" for v in report.violations)


def test_underscaled_food_fails():
    req = _req(guests=50)
    plan = _good_plan(_req(guests=5))
    report = verify_plan(plan, req)
    assert not report.passed
    assert any(v.code == "FOOD_UNDERSCALED" for v in report.violations)


def test_missing_category_fails():
    req = _req()
    plan = _good_plan(req)
    plan.line_items = [li for li in plan.line_items if li.category != "activities"]
    report = verify_plan(plan, req)
    assert not report.passed
    assert any(v.code == "MISSING_ACTIVITIES" for v in report.violations)


def test_dietary_unaddressed_fails():
    req = _req(diet="nut allergy")
    plan = _good_plan(req)  # no dietary tags, no note
    report = verify_plan(plan, req)
    assert not report.passed
    assert any(v.code == "DIETARY_UNADDRESSED" for v in report.violations)
