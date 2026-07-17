"""Tests for the JEPA-TTL bridge: encoder, online predictor, advisor, engine hooks."""
from datetime import date, timedelta

from fastapi.testclient import TestClient

from iparty.api.app import app
from iparty.orchestration.jepa_bridge import (
    HEADS, JepaAdvisor, OutcomePredictor, encode_plan, encode_request,
)
from iparty.planning.models import (
    LineItem, MenuItem, PartyPlan, PartyRequest, ScheduleSlot, VerificationReport, Violation,
)
from iparty.pricing.catalog import StaticCatalog

CAT = StaticCatalog()
FUTURE = date.today() + timedelta(days=30)


def make_request(**over):
    base = dict(honoree_name="Nia", honoree_age=7, party_date=FUTURE, guest_count=12,
                budget=500.0, theme="Space", dietary_restrictions="", location_type="home")
    base.update(over)
    return PartyRequest(**base)


def make_plan(total_ok=True, guests=12):
    price = 100.0 if total_ok else 900.0
    return PartyPlan(
        theme="Space", venue="Home / backyard setup",
        line_items=[
            LineItem(sku="VEN-HOME", category="venue", description="Home", quantity=1,
                     unit_price=0.0, subtotal=0.0),
            LineItem(sku="FD-PIZZA", category="food", description="Pizza", quantity=1,
                     unit_price=price / guests, subtotal=price),
            LineItem(sku="SUP-BASIC", category="supplies", description="Pack", quantity=1,
                     unit_price=35.0, subtotal=35.0),
            LineItem(sku="ACT-GAMES", category="activities", description="Games", quantity=1,
                     unit_price=45.0, subtotal=45.0),
        ],
        menu=[MenuItem(sku="FD-PIZZA", name="Pizza", servings=guests,
                       allergens=["wheat", "milk"], vegetarian=True)],
        schedule=[ScheduleSlot(start="14:00", end="15:00", activity="Games"),
                  ScheduleSlot(start="15:00", end="16:00", activity="Cake")],
        activities=["Games"], supplies=["Pack"],
    )


def report(passed, codes=()):
    return VerificationReport(
        passed=passed, score=1.0 if passed else 0.5, checks_total=10,
        checks_passed=10 if passed else 5,
        violations=[Violation(code=c, severity="error", message=c) for c in codes])


# ---- encoder ----
def test_request_encoding_is_deterministic_and_bounded():
    r = make_request(dietary_restrictions="vegan and nut allergy", guest_count=400)
    a, b = encode_request(r, CAT), encode_request(r, CAT)
    assert a == b
    assert all(-1.0 <= v <= 1.0 for v in a.values())
    assert a["n_allergens"] > 0 and a["veg"] == 1.0


def test_plan_encoding_separates_good_from_bad():
    r = make_request(budget=300.0)
    good = encode_plan(make_plan(total_ok=True), r, CAT)
    bad = encode_plan(make_plan(total_ok=False), r, CAT)
    assert bad["over_budget_margin"] > good["over_budget_margin"]


# ---- online predictor ----
def test_predictor_learns_budget_violations():
    pred = OutcomePredictor()
    r = make_request(budget=300.0)
    xg = encode_plan(make_plan(total_ok=True), r, CAT)
    xb = encode_plan(make_plan(total_ok=False), r, CAT)
    for _ in range(60):
        pred.learn(xg, report(True))
        pred.learn(xb, report(False, ["BUDGET_EXCEEDED"]))
    assert pred.energy(xb) > 0.7 > 0.3 > pred.energy(xg)
    assert pred.predict("BUDGET_EXCEEDED", xb) > 0.7
    assert "BUDGET_EXCEEDED" in pred.top_risks(xb)


def test_predictor_metrics_and_calibration_tracking():
    pred = OutcomePredictor()
    pred.record_assessment(0.9, passed=False)   # hit
    pred.record_assessment(0.1, passed=True)    # hit
    pred.record_assessment(0.9, passed=True)    # miss
    m = pred.metrics()
    assert m["assessments"] == 3
    assert m["calibration_accuracy"] == round(2 / 3, 3)


# ---- advisor ----
def test_candidate_budget_scales_with_difficulty_and_stays_bounded():
    easy = JepaAdvisor(make_request(), CAT, predictor=OutcomePredictor())
    hard = JepaAdvisor(make_request(
        dietary_restrictions="vegan, peanut, tree nut, wheat, soy and sesame allergies",
        guest_count=450, budget=900.0), CAT, predictor=OutcomePredictor())
    for adv in (easy, hard):
        for n in (1, 4, 10):
            assert 1 <= adv.candidate_budget(n) <= n
    assert hard.difficulty() > easy.difficulty()


def test_prehint_names_concrete_risks():
    pred = OutcomePredictor()
    adv = JepaAdvisor(make_request(dietary_restrictions="nut allergy"), CAT, predictor=pred)
    hint = adv.prehint()  # cold start: heads at 0.5 -> hints fire
    assert hint and "attempt" in hint


def test_all_heads_have_hint_coverage():
    from iparty.orchestration.jepa_bridge import _HINTS
    assert set(_HINTS) == set(HEADS) - {"ANY_FAIL"}


# ---- end to end ----
def test_bridge_end_to_end_keeps_plans_verified_and_exposes_metrics():
    client = TestClient(app)
    for i in range(5):
        r = client.post("/api/v1/plan", json={
            "honoree_name": f"Jep{i}", "honoree_age": 7,
            "party_date": FUTURE.isoformat(), "guest_count": 14, "budget": 700.0,
            "theme": "Space", "dietary_restrictions": "nut allergy",
            "location_type": "home"})
        assert r.status_code == 200
        assert r.json()["verification"]["passed"]
    m = client.get("/api/v1/metrics").json()
    assert m["jepa_predictor"]["examples_seen"] >= 5


# ---- suite-2 regressions (found by the 150-persona run) ----
def test_multilingual_dietary_aliases_are_enforced():
    from iparty.pricing.catalog import parse_forbidden_allergens, requires_vegetarian
    assert parse_forbidden_allergens("laktosefrei") == {"milk"}
    assert parse_forbidden_allergens("sans arachide") == {"peanut"}
    assert parse_forbidden_allergens("senza glutine") == {"wheat"}
    assert parse_forbidden_allergens("🥜❌") == {"peanut", "tree_nut"}
    assert requires_vegetarian("халяль") and requires_vegetarian("코셔")


def test_big_budget_never_ships_a_thin_flawed_plan():
    client = TestClient(app)
    r = client.post("/api/v1/plan", json={
        "honoree_name": "CH8", "honoree_age": 45, "party_date": FUTURE.isoformat(),
        "guest_count": 320, "budget": 12000.0, "theme": "Chaos 8",
        "dietary_restrictions": "peanut tree nut egg milk wheat soy allergies",
        "location_type": "home", "duration_hours": 6.0})
    assert r.status_code == 200
    plan = r.json()["plan"]
    assert plan["total_cost"] <= 12000.0
    assert len(plan["activities"]) >= 2


def test_candidate_budget_floors_at_two_for_repair_room():
    """Adaptive budget must never drop below 2 (when N allows), so a failed
    first candidate always gets a verifier-guided repair round."""
    from iparty.orchestration.jepa_bridge import OutcomePredictor
    easy = JepaAdvisor(make_request(budget=100000.0, guest_count=8), CAT,
                       predictor=OutcomePredictor())
    assert easy.candidate_budget(4) >= 2
    assert easy.candidate_budget(1) == 1   # respect a hard N=1 ceiling


def test_telemetry_exposes_jepa_block():
    client = TestClient(app)
    r = client.post("/api/v1/plan", json={
        "honoree_name": "Tel", "honoree_age": 7, "party_date": FUTURE.isoformat(),
        "guest_count": 14, "budget": 900.0, "theme": "Space",
        "dietary_restrictions": "vegan", "location_type": "home"})
    j = r.json()["telemetry"]["jepa"]
    assert j["enabled"] is True
    assert 0.0 <= j["difficulty"] <= 1.0
    assert j["candidate_budget"] >= 1
    assert isinstance(j["energy_trace"], list) and j["energy_trace"]
    assert j["energy_trace"][0]["verifier"] in ("PASS", "FAIL")
