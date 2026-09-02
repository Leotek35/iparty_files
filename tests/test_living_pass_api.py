"""Living Pass — API contract, credentials, adversarial input, persistence,
concurrency, and the frontend guards.

Two audiences, two credentials: the public plan_id (share/invite) can never
reveal the guest list or the host credential; the host token is required for
status and guests, compared in constant time, and never appears in any public
payload. RSVP input is hardened like every other capture surface.
"""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from iparty.api import living as living_api
from iparty.api.app import create_app
from iparty.core.config import settings
from iparty.core.store import PlanStore, store
from iparty.planning import living
from iparty.planning.models import PartyRequest
from iparty.pricing.catalog import unverifiable_dietary

FUTURE = (date.today() + timedelta(days=30)).isoformat()
BODY = {"honoree_name": "Aria", "honoree_age": 6, "party_date": FUTURE, "guest_count": 14,
        "budget": 650.0, "theme": "Under the Sea", "location_type": "home"}


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


def create(client, body=None):
    r = client.post("/api/v1/plans", json=body or BODY)
    assert r.status_code == 201, r.text
    return r.json()


def rsvp(client, pid, name="Guest", attending=True, size=1, dietary="", key=None, **extra):
    payload = {"guest_name": name, "attending": attending, "party_size": size, "dietary": dietary}
    if key:
        payload["guest_key"] = key
    payload.update(extra)
    return client.post(f"/api/v1/plans/{pid}/rsvp", json=payload)


# ---------------------------------------------------------------- contract
def test_create_returns_links_and_credentials(client):
    d = create(client)
    assert d["status"] == "verified" and d["total_cost"] > 0
    assert re.fullmatch(r"[A-Za-z0-9_\-]{16}", d["plan_id"])
    assert len(d["host_token"]) >= 32
    assert d["invite_url"].endswith(f"/rsvp?p={d['plan_id']}")
    assert d["plan_id"] in d["host_url"] and d["host_token"] in d["host_url"]


def test_create_honours_the_plan_status_contract(client):
    r = client.post("/api/v1/plans", json={**BODY, "guest_count": 100, "budget": 10.0})
    assert r.status_code == 409 and r.json()["detail"]["error"] == "no_valid_plan"
    r = client.post("/api/v1/plans", json={**BODY, "guest_count": 0})
    assert r.status_code == 422
    r = client.post("/api/v1/plans", json={**BODY, "dietary_restrictions": "keto"})
    assert r.status_code == 409


def test_public_pass_never_leaks_host_credential_or_guests(client):
    d = create(client)
    rsvp(client, d["plan_id"], name="Secret Family", dietary="tree nut allergy")
    public = client.get(f"/api/v1/plans/{d['plan_id']}")
    assert public.status_code == 200
    text = public.text
    assert d["host_token"] not in text
    assert "Secret Family" not in text and "tree nut" not in text
    invite = client.get(f"/api/v1/plans/{d['plan_id']}/rsvp").json()
    assert "Secret Family" not in json.dumps(invite)
    assert invite["confirmed_guests"] == 1  # social proof, not identities


def test_host_endpoints_require_the_host_token(client):
    d = create(client)
    pid = d["plan_id"]
    for path in (f"/api/v1/plans/{pid}/status", f"/api/v1/plans/{pid}/guests"):
        assert client.get(path).status_code == 401
        assert client.get(path, params={"host_token": "wrong"}).status_code == 401
        assert client.get(path, headers={"X-Host-Token": d["host_token"][:-1]}).status_code == 401
        assert client.get(path, headers={"X-Host-Token": d["host_token"]}).status_code == 200
        assert client.get(path, params={"host_token": d["host_token"]}).status_code == 200


@pytest.mark.parametrize("bad_id", ["nope", "x" * 65, "../etc/passwd", "AAAAAAAAAAAAAAAA", "%00"])
def test_unknown_or_malformed_plan_ids_are_404(client, bad_id):
    assert client.get(f"/api/v1/plans/{bad_id}").status_code == 404
    assert client.get(f"/api/v1/plans/{bad_id}/rsvp").status_code == 404
    assert rsvp(client, bad_id).status_code == 404
    assert client.get(f"/api/v1/plans/{bad_id}/status", params={"host_token": "x"}).status_code == 404


# ---------------------------------------------------------------- RSVP semantics
def test_rsvp_headcount_math_and_updates(client):
    d = create(client)
    pid, tok = d["plan_id"], d["host_token"]
    a = rsvp(client, pid, "Chens", True, 3).json()
    b = rsvp(client, pid, "Lees", True, 2).json()
    rsvp(client, pid, "Nguyens", False, 4)
    assert a["status"] == "received" and b["confirmed_guests"] == 5
    st = client.get(f"/api/v1/plans/{pid}/status", headers={"X-Host-Token": tok}).json()
    assert st["confirmed_guests"] == 5 and st["responses"] == {"going": 2, "declined": 1}

    # Updating my own response replaces it — never a duplicate row.
    upd = rsvp(client, pid, "Chens", True, 1, key=a["guest_key"]).json()
    assert upd["status"] == "updated" and upd["guest_key"] == a["guest_key"]
    assert upd["confirmed_guests"] == 3
    # Flipping to "can't make it" removes my party from the headcount.
    flip = rsvp(client, pid, "Lees", False, 2, key=b["guest_key"]).json()
    assert flip["confirmed_guests"] == 1
    guests = client.get(f"/api/v1/plans/{pid}/guests", headers={"X-Host-Token": tok}).json()
    assert guests["confirmed"] == 1 and len(guests["guests"]) == 3


def test_forged_guest_key_cannot_mint_or_hijack_rows(client):
    d = create(client)
    pid = d["plan_id"]
    other = create(client)
    theirs = rsvp(client, other["plan_id"], "Other Party", True, 2).json()["guest_key"]
    # A key from a different plan (or a made-up one) is treated as a fresh response here.
    r = rsvp(client, pid, "Impostor", True, 8, key=theirs).json()
    assert r["status"] == "received" and r["guest_key"] != theirs
    r2 = rsvp(client, pid, "Made Up", True, 1, key="A" * 20).json()
    assert r2["status"] == "received" and r2["guest_key"] != "A" * 20
    # The other party's row is untouched.
    g = client.get(f"/api/v1/plans/{other['plan_id']}/guests",
                   headers={"X-Host-Token": other["host_token"]}).json()
    assert g["guests"][0]["name"] == "Other Party" and g["guests"][0]["party_size"] == 2


@pytest.mark.parametrize("mutation,code", [
    ({"party_size": 0}, 422),
    ({"party_size": 9}, 422),
    ({"party_size": 500}, 422),
    ({"guest_name": ""}, 422),
    ({"guest_name": "\x00\x01"}, 422),
    ({"guest_name": "x" * 81}, 422),
    ({"dietary": "x" * 201}, 422),
    ({"attending": "maybe"}, 422),
    ({"guest_key": "short"}, 422),
    ({"guest_key": "has spaces here"}, 422),
    ({"email": "smuggled@example.com"}, 422),      # extra keys forbidden
])
def test_rsvp_input_hardening(client, mutation, code):
    d = create(client)
    assert rsvp(client, d["plan_id"], **mutation).status_code == code


def test_hostile_rsvp_text_is_stored_inert_and_stripped(client):
    d = create(client)
    pid, tok = d["plan_id"], d["host_token"]
    name = "<script>alert(1)</script> Zoë\x00\x07"
    diet = "'; DROP TABLE guests; -- \x1b[31m peanut"
    assert rsvp(client, pid, name, True, 1, diet).status_code == 200
    g = client.get(f"/api/v1/plans/{pid}/guests", headers={"X-Host-Token": tok}).json()["guests"][0]
    assert g["name"] == "<script>alert(1)</script> Zoë"      # inert text, control chars gone
    assert "\x00" not in g["name"] and "\x1b" not in g["dietary"]
    assert "DROP TABLE" in g["dietary"]                            # data, never executed
    # It still flows into the live picture as a real need.
    st = client.get(f"/api/v1/plans/{pid}/status", headers={"X-Host-Token": tok}).json()
    assert any("peanut" in n for n in st["dietary_needs"])
    # And the table is still there.
    assert client.get(f"/api/v1/plans/{pid}/rsvp").status_code == 200


def test_guest_list_cap_returns_429(client, monkeypatch):
    monkeypatch.setattr(settings, "LIVING_MAX_GUESTS_PER_PLAN", 3)
    d = create(client)
    for i in range(3):
        assert rsvp(client, d["plan_id"], f"G{i}").status_code == 200
    r = rsvp(client, d["plan_id"], "One too many")
    assert r.status_code == 429 and r.json()["detail"]["error"] == "plan_full"


def test_rsvp_rate_limit_per_client(client, monkeypatch):
    monkeypatch.setattr(settings, "LIVING_RSVP_RATE_PER_MIN", 1)
    d = create(client)
    codes = [rsvp(client, d["plan_id"], f"G{i}").status_code for i in range(12)]
    assert 429 in codes and codes[0] == 200


# ---------------------------------------------------------------- persistence & concurrency
def test_living_pass_survives_a_restart(client, tmp_path):
    d = create(client)
    pid, tok = d["plan_id"], d["host_token"]
    rsvp(client, pid, "Before restart", True, 4, "vegetarian")
    # A brand-new store instance on the same file sees everything.
    fresh = PlanStore(str(tmp_path / "iparty.db"))
    saved = fresh.get_plan(pid)
    assert saved is not None and saved["host_token"] == tok
    assert fresh.guests_for(pid)[0]["party_size"] == 4
    living_api.reset_state()  # drop the in-memory status cache too
    st = client.get(f"/api/v1/plans/{pid}/status", headers={"X-Host-Token": tok}).json()
    assert st["confirmed_guests"] == 4 and "vegetarian" in st["dietary_needs"]


def test_concurrent_rsvps_are_all_recorded_exactly_once(client):
    d = create(client)
    pid, tok = d["plan_id"], d["host_token"]

    def go(i):
        return client.post(f"/api/v1/plans/{pid}/rsvp",
                           json={"guest_name": f"Fam {i}", "attending": True, "party_size": 2},
                           headers={"X-Forwarded-For": f"10.5.0.{i}"}).status_code

    with ThreadPoolExecutor(max_workers=16) as ex:
        codes = list(ex.map(go, range(40)))
    assert codes.count(200) == 40
    g = client.get(f"/api/v1/plans/{pid}/guests", headers={"X-Host-Token": tok}).json()
    assert len(g["guests"]) == 40 and g["confirmed"] == 80
    st = client.get(f"/api/v1/plans/{pid}/status", headers={"X-Host-Token": tok}).json()
    assert st["confirmed_guests"] == 80


def test_status_is_cached_per_guest_list_and_invalidates_on_change(client):
    d = create(client)
    pid, tok = d["plan_id"], d["host_token"]
    hdr = {"X-Host-Token": tok}
    a = client.get(f"/api/v1/plans/{pid}/status", headers=hdr).json()
    b = client.get(f"/api/v1/plans/{pid}/status", headers=hdr).json()
    assert a == b and a["state"] == "awaiting"
    rsvp(client, pid, "New", True, 2)
    c = client.get(f"/api/v1/plans/{pid}/status", headers=hdr).json()
    assert c["state"] == "verified" and c["confirmed_guests"] == 2


# ---------------------------------------------------------------- honesty of dietary parsing
def test_compound_needs_are_judged_piece_by_piece():
    # A need we understand must never let one we don't hide behind it.
    assert unverifiable_dietary("gluten free; halal") == "halal"
    assert unverifiable_dietary("nut allergy, kosher") == "kosher"
    assert unverifiable_dietary("vegetarian and dairy free") is None
    assert unverifiable_dietary("") is None


def test_merge_dietary_dedupes_and_caps():
    merged = living.merge_dietary("Gluten free", ["gluten free", "peanut allergy", "", "  "])
    assert merged == "Gluten free; peanut allergy"
    long = living.merge_dietary("", ["x" * 400])
    assert len(long) <= living.MAX_DIETARY_LEN


def test_live_request_never_uses_a_past_party_date():
    saved = PartyRequest(**{**BODY, "party_date": FUTURE})
    past = saved.model_copy(update={"party_date": date.today()})
    req = living.live_request(past, [{"attending": True, "party_size": 3, "dietary": ""}])
    assert req.guest_count == 3 and req.party_date >= date.today()


# ---------------------------------------------------------------- frontend guards
INDEX = Path("web/index.html").read_text()
RSVP_HTML = Path("web/rsvp.html").read_text()
BANNED = [r"guarantee[sd]?\s+(the\s+)?(party|safe|safety|allergen)", r"100%\s*safe",
          r"allerg\w*[-\s]free\b", r"\breal catalog\b", r"medical"]


def test_rsvp_page_is_served_with_security_headers(client):
    r = client.get("/rsvp")
    assert r.status_code == 200 and "You're invited" in r.text
    assert r.headers["X-Frame-Options"] == "DENY" and "Content-Security-Policy" in r.headers


def test_rsvp_page_renders_server_strings_only_via_textContent():
    js = re.search(r"<script>(.*)</script>", RSVP_HTML, re.DOTALL).group(1)
    assert "innerHTML" not in js and "insertAdjacentHTML" not in js
    assert "textContent" in js and "encodeURIComponent(planId)" in js


def test_host_ui_is_wired_and_escapes_live_status():
    js = re.search(r"<script>(.*)</script>", INDEX, re.DOTALL).group(1)
    for needle in ("function renderLiving", "function startLiving", 'id="live-btn"',
                   "X-Host-Token", "living_created", "/api/v1/plans"):
        assert needle in js or needle in INDEX, needle
    body = js[js.index("function renderLiving("):js.index("// A host returning")]
    # Every interpolated server string in the status renderer goes through esc()
    # — directly, or list-wise via .map(esc).
    body = re.sub(r"\([\w.]+\|\|\[\]\)\.map\(esc\)", "ESCAPED_LIST", body)
    for m in re.finditer(r"\$\{(?!esc\()([^}]*)\}", body):
        expr = m.group(1)
        assert not re.search(r"\b(s|a|li|fix|rs|n)\.(headline|message|description|code|excluded_needs)\b",
                             expr), f"unescaped server string in renderLiving: {expr}"


def test_default_form_values_pass_native_validation():
    """A form whose defaults fail the browser's own validation never submits.
    (Caught live: budget had min=1 step=10, so 650 — and every round number —
    was 'invalid'. Every numeric default must sit on its min/step grid.)"""
    for m in re.finditer(r'<input id="(\w+)" type="number"([^>]*)>', INDEX):
        attrs = dict(re.findall(r'(\w+)="([^"]*)"', m.group(2)))
        if "value" not in attrs:
            continue
        value, lo = float(attrs["value"]), float(attrs.get("min", 0))
        step = attrs.get("step", "1")
        assert step == "any" or (value - lo) % float(step) == 0, (m.group(1), attrs)
        assert value >= lo and (not attrs.get("max") or value <= float(attrs["max"]))


def test_no_overclaims_in_living_copy():
    hits = [m.group(0) for pat in BANNED for html in (INDEX, RSVP_HTML)
            for m in re.finditer(pat, html, re.IGNORECASE)]
    assert not hits, hits
