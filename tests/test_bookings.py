"""Booking flow — functional + adversarial coverage, loop-engineered.

Loop 1 (functional): happy path, ref format, persistence, summary privacy.
Loop 2 (validation): email shapes, length caps, extra-key smuggling, control chars.
Loop 3 (abuse): per-session flood cap, hostile unicode/markup payloads, PII leakage.
"""
from __future__ import annotations

import json
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from iparty.api import bookings
from iparty.api.app import create_app
from iparty.core.config import settings

FUTURE = (date.today() + timedelta(days=30)).isoformat()


def good_body(session="sess-booking-0001", email="parent@example.com"):
    return {
        "session_id": session,
        "name": "Leo W",
        "contact_email": email,
        "notes": "Please call after 5pm",
        "party": {"party_date": FUTURE, "guest_count": 10, "budget": 350.0,
                  "total_cost": 85.5, "theme": "Bluey", "location_type": "home"},
    }


@pytest.fixture(autouse=True)
def _isolated_bookings(tmp_path):
    settings.BOOKINGS_PATH = str(tmp_path / "bookings.jsonl")
    bookings.reset_state()
    yield
    bookings.reset_state()


@pytest.fixture()
def client():
    return TestClient(create_app())


# ---------- Loop 1: functional ----------

def test_booking_happy_path_returns_ref(client):
    r = client.post("/api/v1/bookings", json=good_body())
    assert r.status_code == 201
    d = r.json()
    assert d["status"] == "received"
    assert d["booking_ref"].startswith("IP-") and len(d["booking_ref"]) == 11
    assert all(c.isalnum() or c == "-" for c in d["booking_ref"])


def test_booking_persists_jsonl(client):
    client.post("/api/v1/bookings", json=good_body())
    with open(settings.BOOKINGS_PATH, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["contact_email"] == "parent@example.com"
    assert rec["party"]["theme"] == "Bluey"


def test_summary_has_counts_but_never_pii(client):
    client.post("/api/v1/bookings", json=good_body())
    r = client.get("/api/v1/bookings/summary")
    assert r.status_code == 200
    text = r.text.lower()
    assert r.json()["total_bookings"] == 1
    for leak in ("leo", "example.com", "5pm", "bluey"):
        assert leak not in text, f"summary leaked PII: {leak}"


# ---------- Loop 2: validation ----------

@pytest.mark.parametrize("email", ["not-an-email", "a@b", "a b@c.com", "x@y.z" + "q" * 120, ""])
def test_bad_emails_rejected(client, email):
    r = client.post("/api/v1/bookings", json=good_body(email=email))
    assert r.status_code == 422


def test_extra_keys_forbidden(client):
    body = good_body()
    body["is_admin"] = True
    assert client.post("/api/v1/bookings", json=body).status_code == 422
    body = good_body()
    body["party"]["unit_price_override"] = 0
    assert client.post("/api/v1/bookings", json=body).status_code == 422


def test_length_caps_enforced(client):
    body = good_body()
    body["notes"] = "x" * 301
    assert client.post("/api/v1/bookings", json=body).status_code == 422
    body = good_body()
    body["name"] = "x" * 101
    assert client.post("/api/v1/bookings", json=body).status_code == 422


def test_bad_session_ids_rejected(client):
    for sid in ["short", "x" * 65, "bad sid with spaces!", "<script>aaaa</script>"]:
        assert client.post("/api/v1/bookings", json=good_body(session=sid)).status_code == 422


def test_control_chars_stripped_from_stored_record(client):
    body = good_body()
    body["name"] = "Leo\x00\x08W\x1b[31m"
    r = client.post("/api/v1/bookings", json=body)
    assert r.status_code == 201
    with open(settings.BOOKINGS_PATH, encoding="utf-8") as fh:
        rec = json.loads(fh.readline())
    assert "\x00" not in rec["name"] and "\x1b" not in rec["name"]


# ---------- Loop 3: abuse ----------

def test_flood_capped_per_session(client):
    codes = [client.post("/api/v1/bookings", json=good_body()).status_code for _ in range(6)]
    assert codes.count(201) == settings.BOOKINGS_MAX_PER_SESSION
    assert codes[-1] == 429


def test_flood_cap_is_per_session_not_global(client):
    for _i in range(settings.BOOKINGS_MAX_PER_SESSION):
        assert client.post("/api/v1/bookings", json=good_body()).status_code == 201
    r = client.post("/api/v1/bookings", json=good_body(session="sess-other-9999"))
    assert r.status_code == 201


def test_hostile_markup_is_stored_not_executed_and_response_is_json(client):
    body = good_body()
    body["name"] = "<img src=x onerror=alert(1)>"
    body["notes"] = "'; DROP TABLE bookings; --"
    r = client.post("/api/v1/bookings", json=body)
    assert r.status_code == 201
    assert "application/json" in r.headers["content-type"]
    # Response must never reflect the hostile input.
    assert "onerror" not in r.text and "DROP TABLE" not in r.text


def test_unicode_names_accepted(client):
    body = good_body()
    body["name"] = "Zoë Müller-Ałeksándra 王小明"
    assert client.post("/api/v1/bookings", json=body).status_code == 201


def test_security_headers_on_bookings(client):
    r = client.post("/api/v1/bookings", json=good_body())
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert "content-security-policy" in {k.lower() for k in r.headers}
