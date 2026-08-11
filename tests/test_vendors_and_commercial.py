"""Commercial layer — vendor supply capture + unit-economics instrumentation.

Loop 1 (functional): vendor lead happy path, idempotency by email, summary.
Loop 2 (validation/abuse): email shapes, bad category, extra keys, rate limit.
Loop 3 (economics invariants): GBV pipeline math, take-rate bounds, fee
transparency in UI, no-PII guarantees.
"""
from __future__ import annotations

import json
import re
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from iparty.api import bookings, vendors
from iparty.api.app import create_app
from iparty.core.config import settings
from iparty.core.ratelimit import limiter

FUTURE = (date.today() + timedelta(days=30)).isoformat()


def vendor_body(email="cakes@example.com"):
    return {"business_name": "Sunny Bakes", "contact_email": email,
            "category": "cake", "city": "Austin"}


def booking_body(session, total):
    return {"session_id": session, "name": "Leo", "contact_email": "leo@example.com",
            "party": {"party_date": FUTURE, "guest_count": 10, "budget": 500.0,
                      "total_cost": total, "theme": "Space", "location_type": "home"}}


@pytest.fixture(autouse=True)
def _isolated(tmp_path):
    settings.VENDORS_PATH = str(tmp_path / "vendor_leads.jsonl")
    settings.BOOKINGS_PATH = str(tmp_path / "bookings.jsonl")
    vendors.reset_state()
    bookings.reset_state()
    yield
    vendors.reset_state()
    bookings.reset_state()


@pytest.fixture()
def client():
    return TestClient(create_app())


# ---------- Loop 1: vendor supply ----------

def test_vendor_lead_happy_path(client):
    r = client.post("/api/v1/vendors", json=vendor_body())
    assert r.status_code == 201 and r.json()["status"] == "received"
    assert client.get("/api/v1/vendors/summary").json()["total_leads"] == 1


def test_vendor_resubmission_is_idempotent(client):
    client.post("/api/v1/vendors", json=vendor_body())
    r = client.post("/api/v1/vendors", json=vendor_body())
    assert r.status_code == 201 and r.json()["status"] == "already_registered"
    assert client.get("/api/v1/vendors/summary").json()["total_leads"] == 1


def test_vendor_summary_has_no_pii(client):
    client.post("/api/v1/vendors", json=vendor_body())
    text = client.get("/api/v1/vendors/summary").text.lower()
    for leak in ("sunny", "example.com", "austin"):
        assert leak not in text


# ---------- Loop 2: validation / abuse ----------

def test_vendor_validation(client):
    bad = vendor_body(email="not-an-email")
    assert client.post("/api/v1/vendors", json=bad).status_code == 422
    bad = vendor_body()
    bad["category"] = "weapons"
    assert client.post("/api/v1/vendors", json=bad).status_code == 422
    bad = vendor_body()
    bad["is_admin"] = True
    assert client.post("/api/v1/vendors", json=bad).status_code == 422


def test_vendor_rate_limited(client):
    limiter._buckets.clear()
    settings.VENDORS_RATE_PER_MIN = 1
    try:
        codes = [client.post("/api/v1/vendors",
                             json=vendor_body(email=f"v{i}@example.com")).status_code
                 for i in range(12)]
        assert 429 in codes
    finally:
        settings.VENDORS_RATE_PER_MIN = 100_000
        limiter._buckets.clear()


# ---------- Loop 3: unit-economics invariants ----------

def test_gbv_pipeline_and_take_math(client):
    client.post("/api/v1/bookings", json=booking_body("sess-econ-0001", 217.50))
    client.post("/api/v1/bookings", json=booking_body("sess-econ-0002", 85.50))
    s = client.get("/api/v1/bookings/summary").json()
    assert s["gbv_pipeline"] == pytest.approx(303.00)
    assert s["commission_rate"] == settings.COMMISSION_RATE
    assert s["est_take_revenue"] == pytest.approx(round(303.00 * settings.COMMISSION_RATE, 2))


def test_take_rate_within_benchmark_bounds():
    # Service-marketplace benchmarks are 15-30%; config hard-caps at 35%.
    assert 0.10 <= settings.COMMISSION_RATE <= 0.30


def test_fee_transparency_shown_to_families():
    html = Path("web/index.html").read_text(encoding="utf-8")
    assert "15% platform fee" in html, "fee disclosure removed from booking modal"
    assert "never a markup" in html


def test_vendor_form_wired_in_ui():
    html = Path("web/index.html").read_text(encoding="utf-8")
    js = re.search(r"<script>(.*)</script>", html, re.DOTALL).group(1)
    assert 'id="vendor-form"' in html and "/api/v1/vendors" in js


def test_vendor_lead_persisted(client):
    client.post("/api/v1/vendors", json=vendor_body())
    with open(settings.VENDORS_PATH, encoding="utf-8") as fh:
        rec = json.loads(fh.readline())
    assert rec["category"] == "cake" and rec["ref"].startswith("VN-")
