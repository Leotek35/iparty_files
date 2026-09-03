"""Living Pass — the host accepts a verified way forward (`POST /plans/{id}/apply`).

Round 2 of the browser matrix found the Living Pass could *show* a verified
fix, a right-size plan or an honest minimum budget but the host could not act
on any of them: every attention state was a dead end. Apply recomputes the
proposal server-side from the saved selections and the live guest list,
re-verifies it at the live headcount, and saves it — the plan id, host token
and guest list never change.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from iparty.api import living as living_api
from iparty.api.app import create_app
from iparty.core.config import settings
from iparty.core.store import store
from iparty.planning import living
from iparty.planning.models import PartyPlan, PartyRequest
from iparty.planning.verifier import verify_plan
from iparty.pricing.catalog import StaticCatalog

FUTURE = (date.today() + timedelta(days=30)).isoformat()
CAT = StaticCatalog()


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


def _plan(client, guests=8, budget=150.0, **extra):
    body = {"honoree_name": "Devon", "honoree_age": 8, "party_date": FUTURE, "guest_count": guests,
            "budget": budget, "theme": "Game Night", "location_type": "home", **extra}
    r = client.post("/api/v1/plans", json=body)
    assert r.status_code == 201, r.text
    d = r.json()
    return d["plan_id"], {"X-Host-Token": d["host_token"]}


def _rsvp(client, pid, name, attending=True, size=1, dietary=""):
    r = client.post(f"/api/v1/plans/{pid}/rsvp",
                    json={"guest_name": name, "attending": attending, "party_size": size, "dietary": dietary})
    assert r.status_code == 200, r.text
    return r.json()["guest_key"]


def _status(client, pid, hdr):
    r = client.get(f"/api/v1/plans/{pid}/status", headers=hdr)
    assert r.status_code == 200, r.text
    return r.json()


def _apply(client, pid, hdr, action, budget=None):
    body = {"action": action}
    if budget is not None:
        body["budget"] = budget
    return client.post(f"/api/v1/plans/{pid}/apply", json=body, headers=hdr)


def _saved_is_verified_for_live_guests(pid):
    saved = store.get_plan(pid)
    req = PartyRequest.model_validate(saved["request"])
    plan = PartyPlan.model_validate(saved["plan"])
    live = living.live_request(req, store.guests_for(pid))
    excluded = {e.lower() for e in living.unverifiable_needs(live.dietary_restrictions)}
    keep = [n for n in living.split_needs(live.dietary_restrictions) if n.lower() not in excluded]
    check = live.model_copy(update={"dietary_restrictions": "; ".join(keep)})
    return verify_plan(living.reground(plan, CAT, check.guest_count), check, CAT).passed


# ---------------------------------------------------------------- overflow -> fix -> verified
def test_overflow_fix_becomes_the_plan_and_the_state_goes_green(client):
    pid, hdr = _plan(client, guests=8, budget=650.0)
    for i in range(2):
        _rsvp(client, pid, f"family {i}", size=8)
    s = _status(client, pid, hdr)
    assert s["state"] == "attention" and s["fix"]["available"], s["headline"]
    expected_total = s["fix"]["new_total"]

    r = _apply(client, pid, hdr, "fix")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["applied"] == "fix"
    assert d["status"]["state"] == "verified" and d["status"]["fix"] is None
    assert d["status"]["planned_guests"] == 16 and d["status"]["confirmed_guests"] == 16
    assert d["status"]["saved_total"] == pytest.approx(expected_total, abs=0.01)
    assert d["pass"]["planned_guests"] == 16 and d["pass"]["total_cost"] == pytest.approx(expected_total, abs=0.01)
    # durable: a fresh status and the public pass agree, and the guest list survived
    s2 = _status(client, pid, hdr)
    assert s2["state"] == "verified" and s2["saved_total"] == pytest.approx(expected_total, abs=0.01)
    assert client.get(f"/api/v1/plans/{pid}").json()["total_cost"] == pytest.approx(expected_total, abs=0.01)
    assert client.get(f"/api/v1/plans/{pid}/guests", headers=hdr).json()["confirmed"] == 16
    assert _saved_is_verified_for_live_guests(pid)


def test_allergy_fix_keeps_the_planned_headcount(client):
    pid, hdr = _plan(client, guests=14, budget=650.0)
    for i in range(4):
        _rsvp(client, pid, f"g{i}")
    _rsvp(client, pid, "Ali", dietary="peanut allergy")
    s = _status(client, pid, hdr)
    assert s["state"] == "attention" and "ALLERGEN_VIOLATION" in [a["code"] for a in s["attention"]]
    d = _apply(client, pid, hdr, "fix").json()
    assert d["status"]["state"] == "verified"
    assert d["status"]["planned_guests"] == 14 and d["status"]["confirmed_guests"] == 5
    assert all("peanut" not in m["allergens"] for m in d["plan"]["menu"])
    assert _saved_is_verified_for_live_guests(pid)


# ---------------------------------------------------------------- no fix -> re-plan at the minimum
def test_no_fix_within_budget_then_replan_at_the_minimum(client):
    pid, hdr = _plan(client, guests=8, budget=150.0)
    for i in range(3):
        _rsvp(client, pid, f"family {i}", size=8)
    s = _status(client, pid, hdr)
    assert s["state"] == "attention" and s["fix"]["available"] is False
    minimum = s["fix"]["minimum_feasible_budget"]
    assert minimum and minimum > 150.0

    r = _apply(client, pid, hdr, "fix")
    assert r.status_code == 409 and r.json()["detail"]["error"] == "no_verified_plan"
    assert r.json()["detail"]["minimum_feasible_budget"] == pytest.approx(minimum)

    r = _apply(client, pid, hdr, "budget", budget=minimum - 1)
    assert r.status_code == 409  # still short

    r = _apply(client, pid, hdr, "budget", budget=minimum)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"]["state"] == "verified" and d["status"]["budget"] == pytest.approx(minimum)
    assert d["status"]["planned_guests"] == 24 and d["status"]["saved_total"] <= minimum + 0.01
    assert _saved_is_verified_for_live_guests(pid)


def test_budget_change_alone_keeps_the_hosts_selections(client):
    pid, hdr = _plan(client, guests=8, budget=650.0)
    _rsvp(client, pid, "g0", size=2)
    before = store.get_plan(pid)["plan"]
    d = _apply(client, pid, hdr, "budget", budget=900.0).json()
    assert d["status"]["state"] == "verified" and d["status"]["budget"] == 900.0
    after = store.get_plan(pid)["plan"]
    assert [li["sku"] for li in after["line_items"]] == [li["sku"] for li in before["line_items"]]


# ---------------------------------------------------------------- right-size
def test_right_size_adopts_the_confirmed_headcount(client):
    pid, hdr = _plan(client, guests=20, budget=900.0)
    for i in range(10):
        _rsvp(client, pid, f"g{i}")
    s = _status(client, pid, hdr)
    assert s["right_size"] and s["right_size"]["available"]
    new_total = s["right_size"]["new_total"]
    d = _apply(client, pid, hdr, "right_size").json()
    assert d["status"]["state"] == "verified"
    assert d["status"]["planned_guests"] == 10 and d["status"]["right_size"] is None
    assert d["status"]["saved_total"] == pytest.approx(new_total, abs=0.01)
    assert _saved_is_verified_for_live_guests(pid)


def test_right_size_is_refused_when_none_is_on_offer(client):
    pid, hdr = _plan(client, guests=20, budget=900.0)
    _rsvp(client, pid, "g0")
    r = _apply(client, pid, hdr, "right_size")
    assert r.status_code == 409 and r.json()["detail"]["error"] == "no_right_size"


# ---------------------------------------------------------------- contract & trust boundary
def test_apply_needs_the_host_token_and_a_known_plan(client):
    pid, hdr = _plan(client)
    assert _apply(client, pid, {"X-Host-Token": "not-the-token"}, "fix").status_code == 401
    assert _apply(client, pid, {}, "fix").status_code == 401
    assert _apply(client, "AAAAAAAAAAAAAAAA", hdr, "fix").status_code == 404


def test_apply_rejects_malformed_bodies_and_never_takes_a_plan_from_the_client(client):
    pid, hdr = _plan(client)
    assert client.post(f"/api/v1/plans/{pid}/apply", json={"action": "explode"}, headers=hdr).status_code == 422
    assert client.post(f"/api/v1/plans/{pid}/apply", json={"action": "budget", "budget": -5}, headers=hdr).status_code == 422
    assert client.post(f"/api/v1/plans/{pid}/apply", json={"action": "fix", "plan": {"total_cost": 0}},
                       headers=hdr).status_code == 422
    assert client.post(f"/api/v1/plans/{pid}/apply", json={"action": "budget"}, headers=hdr).status_code == 409


def test_apply_is_idempotent_and_never_saves_an_unverified_plan(client):
    pid, hdr = _plan(client, guests=8, budget=650.0)
    for i in range(2):
        _rsvp(client, pid, f"family {i}", size=8)
    first = _apply(client, pid, hdr, "fix").json()
    again = _apply(client, pid, hdr, "fix")
    assert again.status_code == 200 and again.json()["status"]["saved_total"] == first["status"]["saved_total"]
    saved = store.get_plan(pid)
    assert saved["verification"]["passed"] is True


def test_a_later_rsvp_re_verifies_against_the_applied_plan(client):
    pid, hdr = _plan(client, guests=8, budget=650.0)
    _rsvp(client, pid, "family 0", size=8)
    _rsvp(client, pid, "family 1", size=8)
    _apply(client, pid, hdr, "fix")
    assert _status(client, pid, hdr)["state"] == "verified"
    _rsvp(client, pid, "family 2", size=8)  # 24 now: the applied plan for 16 must trip again
    s = _status(client, pid, hdr)
    assert s["state"] == "attention" and s["planned_guests"] == 16 and s["confirmed_guests"] == 24
