"""Living Pass right-size gate.

The UX matrix showed the "you could save $518" card appearing after the very
first RSVP — one early "yes" is not a smaller party, and the card read as a
demand to downsize. The offer must wait until the headcount is real: at
least half the planned seats confirmed, or every planned seat answered.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from iparty.api import living as living_api
from iparty.api.app import create_app
from iparty.core.config import settings
from iparty.core.store import store
from iparty.planning.feasibility import cheapest_compliant_draft
from iparty.planning.grounding import ground_draft
from iparty.planning.living import all_answered, headcount_settled
from iparty.planning.models import MenuItem, PartyPlan, PartyRequest, ScheduleSlot
from iparty.planning.verifier import verify_plan
from iparty.pricing.catalog import StaticCatalog

FUTURE = (date.today() + timedelta(days=30)).isoformat()


def _guests(yes: list[int], no: list[int]) -> list[dict]:
    rows = [{"guest_key": f"y{i}", "attending": True, "party_size": n} for i, n in enumerate(yes)]
    rows += [{"guest_key": f"n{i}", "attending": False, "party_size": n} for i, n in enumerate(no)]
    return rows


@pytest.mark.parametrize("planned,yes,no,settled", [
    (20, [1], [], False),            # first RSVP: too early
    (20, [2, 2, 2, 2], [], False),   # 8 of 20 confirmed, nobody declined
    (20, [5, 5], [], True),          # exactly half confirmed
    (20, [8, 4], [], True),          # over half
    (20, [2, 2, 2], [8, 6], True),   # 6 confirmed but 14 seats declined: everyone answered
    (20, [2, 2, 2], [8], False),     # 6 confirmed, 8 declined: 6 seats still silent
    (1, [], [1], True),              # everyone answered "no" — settled (right_size itself needs confirmed > 0)
    (14, [1] * 7, [], True),
    (15, [1] * 7, [], False),
])
def test_headcount_settled_rule(planned, yes, no, settled):
    assert headcount_settled(planned, _guests(yes, no)) is settled


def test_all_answered_counts_seats_not_responses():
    assert all_answered(10, _guests([4], [6])) is True
    assert all_answered(10, _guests([4], [5])) is False
    assert all_answered(10, _guests([1] * 3, [1] * 3)) is False


# ---------------------------------------------------------------- through the API
@pytest.fixture(autouse=True)
def _isolated(tmp_path):
    settings.PLANS_DB_PATH = str(tmp_path / "iparty.db")
    store.reset()
    living_api.reset_state()
    yield
    store.reset()
    living_api.reset_state()


@pytest.fixture()
def client():
    return TestClient(create_app())


def _plan(client, guests: int, budget: float):
    body = {"honoree_name": "Aria", "honoree_age": 6, "party_date": FUTURE, "guest_count": guests,
            "budget": budget, "theme": "Under the Sea", "location_type": "home"}
    r = client.post("/api/v1/plans", json=body)
    assert r.status_code == 201, r.text
    d = r.json()
    return d["plan_id"], {"X-Host-Token": d["host_token"]}


def _status(client, pid, hdr):
    r = client.get(f"/api/v1/plans/{pid}/status", headers=hdr)
    assert r.status_code == 200, r.text
    return r.json()


def _rsvp(client, pid, name, attending=True, size=1):
    r = client.post(f"/api/v1/plans/{pid}/rsvp",
                    json={"guest_name": name, "attending": attending, "party_size": size})
    assert r.status_code == 200, r.text


def test_no_right_size_after_the_first_yes(client):
    pid, hdr = _plan(client, 20, 900.0)
    _rsvp(client, pid, "Chen family", size=1)
    s = _status(client, pid, hdr)
    assert s["state"] == "verified" and s["confirmed_guests"] == 1
    assert s["right_size"] is None


def test_right_size_appears_once_half_have_confirmed_and_is_verified(client):
    pid, hdr = _plan(client, 20, 900.0)
    for i in range(10):
        _rsvp(client, pid, f"g{i}", size=1)
    s = _status(client, pid, hdr)
    rs = s["right_size"]
    assert rs and rs["available"] and rs["confirmed"] == 10 and rs["final"] is False
    assert rs["savings"] > 0 and rs["new_total"] == pytest.approx(rs["current_total"] - rs["savings"], abs=0.01)
    # the offer is a real verified plan for the live headcount
    req = PartyRequest(honoree_name="Aria", honoree_age=6, party_date=FUTURE, guest_count=10,
                       budget=900.0, theme="Under the Sea", location_type="home")
    catalog = StaticCatalog()
    cheap = ground_draft(cheapest_compliant_draft(req, catalog), catalog, 10)
    assert verify_plan(cheap, req, catalog).passed
    assert rs["new_total"] == pytest.approx(cheap.total_cost, abs=0.01)


def test_right_size_is_final_when_every_seat_has_answered(client):
    pid, hdr = _plan(client, 14, 650.0)
    for i in range(6):
        _rsvp(client, pid, f"g{i}", size=1)
    assert _status(client, pid, hdr)["right_size"] is None  # 6 of 14, 8 silent
    _rsvp(client, pid, "the office", attending=False, size=8)
    rs = _status(client, pid, hdr)["right_size"]
    assert rs and rs["available"] and rs["confirmed"] == 6 and rs["final"] is True


def test_no_right_size_when_everyone_planned_shows_up(client):
    pid, hdr = _plan(client, 14, 650.0)
    for i in range(7):
        _rsvp(client, pid, f"g{i}", size=2)
    s = _status(client, pid, hdr)
    assert s["confirmed_guests"] == 14 and s["right_size"] is None


# ---------------------------------------------------------------- copy hygiene
def test_allergen_violation_reads_like_english():
    """E4: hosts saw "contain peanut, tree_nut" for a PB&J — a catalog key, and
    an allergen the sandwich doesn't even have. Name only what's present, in
    plain words."""
    catalog = StaticCatalog()
    req = PartyRequest(honoree_name="Aria", honoree_age=6, party_date=FUTURE, guest_count=4,
                       budget=400.0, theme="Under the Sea", location_type="home",
                       dietary_restrictions="nut allergy")
    pbj = catalog.get("FD-PBJ")
    plan = PartyPlan(theme="Under the Sea", venue="home", line_items=[],
                     menu=[MenuItem(sku=pbj.sku, name=pbj.name, servings=8, allergens=sorted(pbj.allergens))],
                     schedule=[ScheduleSlot(start="14:00", end="15:00", activity="Cake")])
    msgs = [v.message for v in verify_plan(plan, req, catalog).violations if v.code == "ALLERGEN_VIOLATION"]
    assert msgs and msgs[0].endswith(f"{pbj.name} contain peanut.")
    assert "tree" not in msgs[0] and "_" not in msgs[0]

    plan.menu[0].allergens = ["peanut", "tree_nut"]
    msgs = [v.message for v in verify_plan(plan, req, catalog).violations if v.code == "ALLERGEN_VIOLATION"]
    assert msgs and "peanut, tree nut." in msgs[0] and "tree_nut" not in msgs[0]
