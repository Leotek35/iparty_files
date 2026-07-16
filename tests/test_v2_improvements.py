"""Regression tests for the v1.1 delight iteration (persona-loop findings)."""
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from iparty.api.app import app
from iparty.pricing.catalog import StaticCatalog, unrecognized_restrictions, requires_vegetarian

client = TestClient(app)
FUTURE = (date.today() + timedelta(days=30)).isoformat()


def base_req(**over):
    r = {"honoree_name": "Nia", "honoree_age": 7, "party_date": FUTURE,
         "guest_count": 12, "budget": 500.0, "theme": "Space",
         "dietary_restrictions": "", "location_type": "home"}
    r.update(over)
    return r


def post(payload):
    return client.post("/api/v1/plan", json=payload)


# ---- budget floor: modest budgets must now be servable (ACT-CLASSIC @ $12) ----
def test_forty_dollar_party_is_feasible():
    r = post(base_req(guest_count=8, budget=80.0, theme=""))
    assert r.status_code == 200, r.text
    assert r.json()["plan"]["total_cost"] <= 80.0


# ---- honest dietary handling ----
def test_unrecognized_diet_is_acknowledged_not_ignored():
    r = post(base_req(dietary_restrictions="keto"))
    assert r.status_code == 200
    body = r.json()
    warns = [v["code"] for v in body["verification"]["violations"]]
    assert "UNVERIFIED_RESTRICTION" in warns
    assert "keto" in body["plan"]["notes"].lower()


def test_kosher_maps_to_vegetarian_menu_with_note():
    assert requires_vegetarian("kosher")
    r = post(base_req(dietary_restrictions="kosher", budget=800.0))
    assert r.status_code == 200
    body = r.json()
    assert all(m["vegetarian"] for m in body["plan"]["menu"])
    assert "vegetarian" in body["plan"]["notes"].lower()


def test_unrecognized_parser():
    assert unrecognized_restrictions("keto, gluten-free") == ["keto"]
    assert unrecognized_restrictions("nut allergy and vegan") == []
    assert unrecognized_restrictions("") == []


# ---- time window control ----
def test_evening_party_schedule_respects_window():
    r = post(base_req(start_time="18:00", duration_hours=3.0))
    assert r.status_code == 200
    sched = r.json()["plan"]["schedule"]
    assert sched[0]["start"] >= "18:00"
    assert sched[-1]["end"] <= "21:01"


def test_default_time_fields_backwards_compatible():
    r = post(base_req())  # no start_time/duration/special_requests sent
    assert r.status_code == 200
    assert r.json()["plan"]["schedule"][0]["start"] == "14:00"


def test_bad_start_time_rejected():
    assert post(base_req(start_time="25:99")).status_code == 422


# ---- special requests surface in the plan ----
def test_special_requests_reach_the_notes():
    r = post(base_req(special_requests="wheelchair access and quiet music"))
    assert r.status_code == 200
    assert "wheelchair access" in r.json()["plan"]["notes"]


# ---- budget-aware enrichment: richer plans, never over budget ----
@pytest.mark.parametrize("budget,guests", [(1500.0, 20), (5000.0, 40), (10000.0, 60)])
def test_generous_budgets_get_rich_plans_within_budget(budget, guests):
    r = post(base_req(budget=budget, guest_count=guests, honoree_name=f"Rich{int(budget)}"))
    assert r.status_code == 200
    plan = r.json()["plan"]
    assert plan["total_cost"] <= budget
    assert len(plan["activities"]) >= 2, plan["activities"]
    assert plan["total_cost"] >= budget * 0.25


# ---- new catalog items keep age gates ----
def test_age_gates_still_verified():
    cat = StaticCatalog()
    karaoke = cat.get("ACT-KARAOKE")
    assert karaoke.min_age == 8
    r = post(base_req(honoree_age=1, budget=2000.0, theme="First"))
    assert r.status_code == 200
    acts = r.json()["plan"]["line_items"]
    names = [li["description"] for li in acts if li["category"] == "activities"]
    assert names, "baby party still gets activities"
    assert "Karaoke setup (3 hr)" not in names
