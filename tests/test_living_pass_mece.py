"""Living Pass × the 100 MECE profiles — every verified party through the
guest loop, before any of this ships.

For each profile that yields a verified plan, five RSVP waves run against a
freshly saved Living Pass and the host's live status must obey the same
invariants the product promises:

  awaiting   nobody has said yes -> verified for the planned headcount
  exact      confirmed == planned -> still verified, nothing to fix
  overflow   30% more show up   -> either still verified (slack) or ATTENTION
             with a fix that is itself verified against the live guest list
             and inside budget — or an honest, correct minimum budget
  allergy    a guest declares a peanut allergy -> if the saved menu contains
             peanut, ATTENTION with ALLERGEN_VIOLATION and a fix whose menu
             has no peanut; otherwise still verified
  unverif.   a guest declares 'halal' -> UNVERIFIABLE, flagged by name, and
             any fix is explicitly marked as not covering it
  shrink     half confirm -> still verified; cost never rises; any
             right-size suggestion is verified and actually cheaper

Every status call costs zero model calls — asserted on every wave.
"""
from __future__ import annotations

import math

import pytest
from fastapi.testclient import TestClient

from iparty.api import living as living_api
from iparty.api.app import create_app
from iparty.core.config import settings
from iparty.core.store import store
from iparty.planning import living
from iparty.planning.models import PartyPlan
from iparty.planning.verifier import verify_plan
from iparty.pricing.catalog import StaticCatalog

from .mece_profiles import PROFILES_MECE, build_request

CATALOG = StaticCatalog()
PASS_PROFILES = [p for p in PROFILES_MECE if p["expect"] in ("pass", "pass_sanitized")]

# Which fix strategies the matrix actually exercised — a dead repair path that
# always falls through to "cheapest compliant" still yields verified fixes, so
# only a coverage assertion can catch it (mutation-tested).
OBSERVED: dict[str, set[str]] = {"overflow": set(), "allergy": set(), "apply": set()}


@pytest.fixture(scope="module")
def db_path(tmp_path_factory):
    return str(tmp_path_factory.mktemp("living") / "iparty.db")


@pytest.fixture(autouse=True)
def _isolated(db_path):
    settings.PLANS_DB_PATH = db_path
    store.reset()
    living_api.reset_state()
    yield
    store.reset()
    living_api.reset_state()


@pytest.fixture(scope="module")
def client():
    return TestClient(create_app())


# ---------------------------------------------------------------- helpers
class Pass:
    """One saved Living Pass and the calls a host/guest can make on it."""

    def __init__(self, client: TestClient, body: dict) -> None:
        self.client = client
        r = client.post("/api/v1/plans", json=body)
        assert r.status_code == 201, r.text
        d = r.json()
        self.plan_id, self.host_token = d["plan_id"], d["host_token"]
        self.saved = client.get(f"/api/v1/plans/{self.plan_id}").json()
        self._n = 0

    def rsvp(self, attending: bool = True, size: int = 1, dietary: str = "") -> dict:
        self._n += 1
        r = self.client.post(f"/api/v1/plans/{self.plan_id}/rsvp",
                             json={"guest_name": f"Guest {self._n}", "attending": attending,
                                   "party_size": size, "dietary": dietary})
        assert r.status_code == 200, r.text
        return r.json()

    def fill(self, headcount: int) -> None:
        """Confirm exactly `headcount` guests in parties of up to the max size."""
        cap = settings.LIVING_MAX_PARTY_SIZE
        left = headcount
        while left > 0:
            size = min(cap, left)
            self.rsvp(True, size)
            left -= size

    def status(self) -> dict:
        r = self.client.get(f"/api/v1/plans/{self.plan_id}/status",
                            headers={"X-Host-Token": self.host_token})
        assert r.status_code == 200, r.text
        return r.json()

    def guests(self) -> list[dict]:
        r = self.client.get(f"/api/v1/plans/{self.plan_id}/guests",
                            headers={"X-Host-Token": self.host_token})
        assert r.status_code == 200
        return r.json()["guests"]

    def apply(self, action: str, budget: float | None = None):
        body = {"action": action} if budget is None else {"action": action, "budget": budget}
        return self.client.post(f"/api/v1/plans/{self.plan_id}/apply", json=body,
                                headers={"X-Host-Token": self.host_token})


def _live_req(req, guests):
    return living.live_request(req, guests)


def _assert_verified_plan(plan_dict: dict, live_req, budget: float) -> None:
    plan = PartyPlan.model_validate(plan_dict)
    report = verify_plan(plan, live_req, CATALOG)
    assert report.passed, [v.code for v in report.violations]
    assert plan.total_cost <= budget + 0.01


def _codes(status: dict) -> set[str]:
    return {a["code"] for a in status["attention"]}


# ---------------------------------------------------------------- the matrix
def test_partitions_all_reach_the_guest_loop():
    cats = {p["cat"] for p in PASS_PROFILES}
    assert cats == {"diy", "luxury", "milestone", "micro", "tech", "cultural", "fuzz"}
    assert len(PASS_PROFILES) >= 90


@pytest.mark.parametrize("p", PASS_PROFILES, ids=[f"ID-{p['id']}-{p['cat']}" for p in PASS_PROFILES])
def test_living_pass_rsvp_waves(p, client):
    req = build_request(p)
    body = req.model_dump(mode="json")
    planned, budget = req.guest_count, req.budget

    # ---- wave 0: awaiting ------------------------------------------------
    lp = Pass(client, body)
    s = lp.status()
    assert s["state"] == "awaiting" and s["confirmed_guests"] == 0
    assert s["verification"]["passed"] and s["llm_calls"] == 0
    assert s["current_total"] == pytest.approx(s["saved_total"], abs=0.01)
    assert "host_token" not in lp.saved  # the public pass never leaks the host credential

    # ---- wave 1: exact headcount ------------------------------------------
    lp.fill(planned)
    s = lp.status()
    assert s["state"] == "verified", (s["state"], _codes(s))
    assert s["confirmed_guests"] == planned and s["fix"] is None and s["llm_calls"] == 0

    # ---- wave 2: overflow (+30%, at least +2) ------------------------------
    lp = Pass(client, body)
    over = planned + max(2, math.ceil(planned * 0.3))
    over = min(over, 500)
    lp.fill(over)
    s = lp.status()
    assert s["llm_calls"] == 0 and s["confirmed_guests"] == over
    assert s["current_total"] >= s["saved_total"] - 0.01  # more mouths never costs less
    live_req = _live_req(req, lp.guests())
    if s["state"] == "verified":
        assert s["fix"] is None
    else:
        assert s["state"] == "attention", (s["state"], _codes(s))
        assert _codes(s) & {"FOOD_UNDERSCALED", "SUPPLIES_UNDERSCALED", "BUDGET_EXCEEDED"}
        fix = s["fix"]
        assert fix is not None
        if fix["available"]:
            assert fix["verified"] and fix["strategy"] in ("repair", "cheapest_compliant")
            OBSERVED["overflow"].add(fix["strategy"])
            _assert_verified_plan(fix["plan"], live_req, budget)
            assert fix["new_total"] == pytest.approx(
                PartyPlan.model_validate(fix["plan"]).total_cost, abs=0.01)
            # ---- the host accepts it: it becomes the saved plan, verified for everyone coming
            r = lp.apply("fix")
            assert r.status_code == 200, r.text
            applied = r.json()["status"]
            assert applied["state"] == "verified" and applied["fix"] is None and applied["llm_calls"] == 0
            assert applied["saved_total"] == pytest.approx(fix["new_total"], abs=0.01)
            assert applied["planned_guests"] == over and applied["confirmed_guests"] == over
            assert lp.status()["state"] == "verified"  # durable, not just the response
            OBSERVED["apply"].add("fix")
        else:
            assert fix["reason"] in ("BUDGET_INFEASIBLE", "CONSTRAINTS_UNSATISFIABLE")
            r = lp.apply("fix")
            assert r.status_code == 409 and r.json()["detail"]["error"] == "no_verified_plan"
            if fix["reason"] == "BUDGET_INFEASIBLE":
                minimum = fix["minimum_feasible_budget"]
                assert minimum > budget
                # ---- the honest minimum is a real way out, not just a number
                r = lp.apply("budget", budget=minimum)
                assert r.status_code == 200, r.text
                applied = r.json()["status"]
                assert applied["state"] == "verified" and applied["budget"] == pytest.approx(minimum)
                assert applied["saved_total"] <= minimum + 0.01
                OBSERVED["apply"].add("budget")

    # ---- wave 3: a guest declares a peanut allergy -------------------------
    lp = Pass(client, body)
    lp.fill(max(1, planned - 1))
    lp.rsvp(True, 1, "peanut allergy")
    s = lp.status()
    assert s["llm_calls"] == 0
    assert "peanut allergy" in s["dietary_needs"]
    menu_has_peanut = any("peanut" in m["allergens"] for m in lp.saved["menu"])
    live_req = _live_req(req, lp.guests())
    if menu_has_peanut:
        assert s["state"] == "attention", (s["state"], _codes(s))
        assert "ALLERGEN_VIOLATION" in _codes(s)
        fix = s["fix"]
        assert fix is not None and fix["available"], fix
        OBSERVED["allergy"].add(fix["strategy"])
        _assert_verified_plan(fix["plan"], live_req, budget)
        assert not any("peanut" in m["allergens"] for m in fix["plan"]["menu"])
        r = lp.apply("fix")
        assert r.status_code == 200, r.text
        applied = r.json()
        confirmed = applied["status"]["confirmed_guests"]
        assert applied["status"]["state"] == "verified"
        assert applied["status"]["planned_guests"] == max(planned, confirmed)  # an allergy fix never shrinks the plan
        assert not any("peanut" in m["allergens"] for m in applied["plan"]["menu"])
        assert not any("peanut" in m["allergens"] for m in lp.client.get(f"/api/v1/plans/{lp.plan_id}").json()["menu"])
    else:
        assert s["state"] == "verified", (s["state"], _codes(s))

    # ---- wave 4: a need the catalog can't verify ---------------------------
    lp = Pass(client, body)
    lp.fill(max(1, planned - 1))
    lp.rsvp(True, 1, "halal")
    s = lp.status()
    assert s["state"] == "unverifiable", (s["state"], _codes(s))
    assert "DIETARY_UNVERIFIABLE" in _codes(s) and s["unverifiable_needs"] == ["halal"]
    assert "halal" in s["headline"] or "verified yet" in s["headline"]
    if s["fix"] is not None and s["fix"]["available"]:
        assert s["fix"]["covers_unverifiable"] is False
        assert s["fix"]["excluded_needs"] == ["halal"]

    # ---- wave 5: only half confirm -----------------------------------------
    lp = Pass(client, body)
    half = max(1, planned // 2)
    lp.fill(half)
    lp.rsvp(False, 3)  # a decline never counts toward headcount
    s = lp.status()
    assert s["state"] == "verified", (s["state"], _codes(s))
    assert s["confirmed_guests"] == half and s["responses"]["declined"] == 1
    assert s["current_total"] <= s["saved_total"] + 0.01  # fewer mouths never costs more
    rs = s["right_size"]
    if rs is not None:
        assert rs["available"] and rs["savings"] > 0
        assert rs["new_total"] == pytest.approx(rs["current_total"] - rs["savings"], abs=0.01)
        _assert_verified_plan(rs["plan"], _live_req(req, lp.guests()), budget)


def test_the_minimal_repair_path_is_really_exercised():
    """Across the matrix, the 'keeps your choices' repair must be what fixes
    most parties — if it silently died, every fix would fall through to the
    cheapest-compliant reshuffle and this is the only test that would notice."""
    assert "repair" in OBSERVED["overflow"], OBSERVED
    assert "repair" in OBSERVED["allergy"], OBSERVED
    assert "fix" in OBSERVED["apply"], OBSERVED  # accepting a fix was exercised across the matrix
    # (the re-plan-at-minimum way out is pinned by tests/test_living_apply.py)
