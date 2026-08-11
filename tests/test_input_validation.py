"""Email typo detection + phone validation — loop-engineered coverage.

Loop 1: typo engine unit truth table (catches, and crucially, non-catches).
Loop 2: endpoint enforcement with structured did_you_mean 422s.
Loop 3: phone normalization/rejection on both bookings and vendors; UI wiring.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from iparty.api import bookings, vendors
from iparty.api.app import create_app
from iparty.core.config import settings
from iparty.core.emailcheck import suggest_email

FUTURE = (date.today() + timedelta(days=30)).isoformat()


@pytest.fixture(autouse=True)
def _isolated(tmp_path):
    settings.BOOKINGS_PATH = str(tmp_path / "b.jsonl")
    settings.VENDORS_PATH = str(tmp_path / "v.jsonl")
    bookings.reset_state()
    vendors.reset_state()
    yield
    bookings.reset_state()
    vendors.reset_state()


@pytest.fixture()
def client():
    return TestClient(create_app())


def bk(email="parent@gmail.com", phone=""):
    return {"session_id": "sess-valid-0001", "name": "Leo",
            "contact_email": email, "contact_phone": phone,
            "party": {"party_date": FUTURE, "guest_count": 10, "budget": 350.0,
                      "total_cost": 85.5, "theme": "Bluey", "location_type": "home"}}


def vn(email="cakes@gmail.com", phone=""):
    return {"business_name": "Sunny Bakes", "contact_email": email,
            "contact_phone": phone, "category": "cake"}


# ---------- Loop 1: typo engine truth table ----------

@pytest.mark.parametrize("bad,fixed", [
    ("leo@gamail.com", "leo@gmail.com"),
    ("leo@gmial.com", "leo@gmail.com"),
    ("leo@gnail.com", "leo@gmail.com"),
    ("leo@yaho.com", "leo@yahoo.com"),
    ("leo@hotmial.com", "leo@hotmail.com"),
    ("leo@outlok.com", "leo@outlook.com"),
    ("leo@iclod.com", "leo@icloud.com"),
    ("leo@gmail.con", "leo@gmail.com"),
    ("leo@gmail.cmo", "leo@gmail.com"),
    ("leo@leotek.con", "leo@leotek.com"),
])
def test_typos_are_caught_with_correct_suggestion(bad, fixed):
    assert suggest_email(bad) == fixed


@pytest.mark.parametrize("ok", [
    "leo@gmail.com", "info@leotek.tech", "a@university.edu",
    "x@some-company.io", "leo@proton.me", "team@sunnybakes.shop",
])
def test_legit_domains_are_never_flagged(ok):
    assert suggest_email(ok) is None, f"{ok} falsely flagged"


# ---------- Loop 2: endpoint enforcement ----------

def test_booking_rejects_typo_email_with_suggestion(client):
    r = client.post("/api/v1/bookings", json=bk(email="leo@gamail.com"))
    assert r.status_code == 422
    det = r.json()["detail"]
    assert det["error"] == "email_typo"
    assert det["did_you_mean"] == "leo@gmail.com"


def test_vendor_rejects_typo_email_with_suggestion(client):
    r = client.post("/api/v1/vendors", json=vn(email="cakes@yahooo.com"))
    assert r.status_code == 422
    assert r.json()["detail"]["did_you_mean"] == "cakes@yahoo.com"


def test_corrected_email_is_accepted(client):
    assert client.post("/api/v1/bookings", json=bk(email="leo@gmail.com")).status_code == 201


# ---------- Loop 3: phone validation ----------

@pytest.mark.parametrize("phone,stored", [
    ("+1 (415) 555-0172", "+14155550172"),
    ("072 123 4567", "0721234567"),
    ("415.555.0172", "4155550172"),
    ("", ""),
])
def test_valid_phones_normalized(client, phone, stored):
    r = client.post("/api/v1/bookings", json=bk(phone=phone))
    assert r.status_code == 201, phone
    import json as _json
    with open(settings.BOOKINGS_PATH, encoding="utf-8") as fh:
        assert _json.loads(fh.readlines()[-1])["contact_phone"] == stored


@pytest.mark.parametrize("phone", ["12345", "phone-me", "+123456789012345678",
                                   "555-CALL-NOW", "1234567890123456"])
def test_bad_phones_rejected_on_both_endpoints(client, phone):
    assert client.post("/api/v1/bookings", json=bk(phone=phone)).status_code == 422
    assert client.post("/api/v1/vendors", json=vn(phone=phone)).status_code == 422


# ---------- UI wiring guards ----------

HTML = Path("web/index.html").read_text(encoding="utf-8")
JS = re.search(r"<script>(.*)</script>", HTML, re.DOTALL).group(1)


def test_ui_has_phone_fields():
    assert 'id="bk-phone"' in HTML and 'id="vn-phone"' in HTML
    assert "contact_phone" in JS


def test_ui_mirrors_typo_engine_with_live_hints():
    for marker in ["function emailSuggestion", "function wireEmailHint",
                   "function showDidYouMean", "did_you_mean"]:
        assert marker in JS, f"client validation lost: {marker}"
    assert 'wireEmailHint("bk-email"' in JS and 'wireEmailHint("vn-email"' in JS
