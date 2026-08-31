"""Adversarial security & fuzzing — concurrency races, hostile input, email gate.

Ports the classic double-booking race onto this app's real guarantee: booking
capture has a per-session cap protected by a mutex, so N simultaneous attempts
must yield EXACTLY the cap in acceptances — no lost updates, no over-admission —
while the JSONL ledger and the GBV counters stay exactly consistent.
"""
from __future__ import annotations

import asyncio
import json
from datetime import date, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from iparty.api import bookings
from iparty.api.app import create_app
from iparty.core.config import settings
from iparty.core.emailcheck import validate_email_address

FUTURE = (date.today() + timedelta(days=21)).isoformat()


@pytest.fixture(autouse=True)
def _isolated_bookings(tmp_path):
    settings.BOOKINGS_PATH = str(tmp_path / "bookings.jsonl")
    bookings.reset_state()
    yield
    bookings.reset_state()


def booking_body(session: str, email: str = "organizer@example.com") -> dict:
    return {
        "session_id": session,
        "name": "Race Organizer",
        "contact_email": email,
        "party": {"party_date": FUTURE, "guest_count": 20, "budget": 500.0,
                  "total_cost": 240.0, "theme": "Limited VIP Cabana",
                  "location_type": "venue"},
    }


async def test_high_concurrency_session_cap_race():
    """50 simultaneous booking attempts for one session: exactly the cap wins.

    Each request carries a distinct client IP (X-Forwarded-For) so the
    per-client rate limit stays out of the way and the SESSION cap's mutex is
    what's actually under test.
    """
    session = "bot-race-session-42"
    cap = settings.BOOKINGS_MAX_PER_SESSION
    async with AsyncClient(transport=ASGITransport(app=create_app()),
                           base_url="http://testserver") as client:
        async def attempt(i: int):
            return await client.post(
                "/api/v1/bookings", json=booking_body(session),
                headers={"X-Forwarded-For": f"10.9.{i // 250}.{i % 250}"},
            )

        results = await asyncio.gather(*(attempt(i) for i in range(50)))
        codes = [r.status_code for r in results]
        assert codes.count(201) == cap, f"Race detected! Acceptances: {codes.count(201)} != {cap}"
        assert codes.count(429) == 50 - cap
        assert all(r.json()["detail"]["error"] == "too_many_bookings"
                   for r in results if r.status_code == 429)

        # Ledger and counters agree exactly with the admissions.
        summary = (await client.get("/api/v1/bookings/summary")).json()
        assert summary["total_bookings"] == cap
        assert summary["gbv_pipeline"] == pytest.approx(240.0 * cap, abs=0.01)
    with open(settings.BOOKINGS_PATH, encoding="utf-8") as fh:
        lines = [json.loads(x) for x in fh.read().splitlines()]
    assert len(lines) == cap
    assert len({rec["ref"] for rec in lines}) == cap  # unique refs, no dup writes


async def test_concurrent_plans_share_one_orchestrator_safely():
    """A burst of parallel /plan calls through the shared orchestrator must all
    verify — no cross-request breaker trips, no event-loop starvation."""
    def body(i: int) -> dict:
        return {"honoree_name": f"Burst Kid {i}", "honoree_age": 6 + (i % 5),
                "party_date": FUTURE, "guest_count": 10 + i, "budget": 900.0 + 10 * i,
                "theme": "Concurrency", "location_type": "home"}

    async with AsyncClient(transport=ASGITransport(app=create_app()),
                           base_url="http://testserver") as client:
        results = await asyncio.gather(*(
            client.post("/api/v1/plan", json=body(i),
                        headers={"X-Forwarded-For": f"10.77.0.{i}"})
            for i in range(15)
        ))
    assert [r.status_code for r in results] == [200] * 15
    for r in results:
        payload = r.json()
        assert payload["status"] == "verified"
        assert payload["plan"]["total_cost"] <= payload["request"]["budget"] + 0.01


@pytest.mark.parametrize("bad_email", [
    "user@localhost",                       # no TLD
    "plainaddress",                         # no @
    "@missingusername.com",                 # empty local part
    "username@.com.my",                     # domain label starts with a dot
    "user@mailinator.com",                  # disposable inbox
    "user@tempmail.com",                    # disposable inbox
    "test@disposablemail.com",              # disposable inbox
    "user@sub.mailinator.com",              # disposable via subdomain
    "admin@127.0.0.1",                      # IP-literal domain
    "<script>alert(1)</script>@test.com",   # hostile local part
    "user@malformed..com",                  # consecutive dots in domain
    "double..dot@example.com",              # consecutive dots in local part
    ".leading@example.com",                 # local part starts with a dot
    "trailing.@example.com",                # local part ends with a dot
    "user@-hyphen.com",                     # label starts with a hyphen
    "user@example.c",                       # TLD too short
])
def test_email_security_boundary_enforcement(bad_email):
    assert validate_email_address(bad_email) is False, \
        f"Email gate allowed security vector: {bad_email}"


@pytest.mark.parametrize("good_email", [
    "parent@example.com",
    "info@leotek.tech",
    "first.last+party@sub.domain.co",
    "ORGANIZER@GMAIL.COM",
])
def test_email_gate_never_blocks_legitimate_addresses(good_email):
    assert validate_email_address(good_email) is True


@pytest.mark.parametrize("vector_email", ["user@malformed..com", "test@disposablemail.com"])
@pytest.mark.parametrize("endpoint,payload_fn", [
    ("/api/v1/bookings", lambda em: booking_body("sess-email-gate-1", em)),
    ("/api/v1/vendors", lambda em: {"business_name": "Fly-By-Night Ltd",
                                    "contact_email": em, "category": "food"}),
])
async def test_capture_endpoints_reject_undeliverable_emails(endpoint, payload_fn, vector_email):
    """Both capture surfaces (demand and supply) enforce the same email gate."""
    async with AsyncClient(transport=ASGITransport(app=create_app()),
                           base_url="http://testserver") as client:
        res = await client.post(endpoint, json=payload_fn(vector_email))
    assert res.status_code == 422


@pytest.mark.parametrize("hostile_theme", [
    "'; DROP TABLE bookings; --",
    "<script>alert('xss')</script>",
    "{{7*7}}${{config}}",
    "A" * 120,
    "نص عربي مع 🎈 وحروف",
    "垂直\t水平",
])
async def test_plan_endpoint_treats_hostile_themes_as_inert_data(hostile_theme):
    body = {"honoree_name": "Fuzz Target", "honoree_age": 8, "party_date": FUTURE,
            "guest_count": 10, "budget": 600.0, "theme": hostile_theme,
            "location_type": "home"}
    async with AsyncClient(transport=ASGITransport(app=create_app()),
                           base_url="http://testserver") as client:
        res = await client.post("/api/v1/plan", json=body)
    assert res.status_code == 200  # hostile text is data, never an error path
    assert res.headers["content-type"].startswith("application/json")
    echoed = res.json()["request"]["theme"]
    assert "\x00" not in echoed
    assert echoed == "".join(ch for ch in hostile_theme if ch >= " " or ch in "\t")


def test_control_characters_never_survive_request_models():
    from iparty.planning.models import PartyRequest

    req = PartyRequest(honoree_name="Eve\x00lyn", honoree_age=9, party_date=FUTURE,
                       guest_count=10, budget=500.0, theme="Bell\x07 Party",
                       dietary_restrictions="nut\x1b free")
    assert req.honoree_name == "Evelyn"
    assert req.theme == "Bell Party"
    assert req.dietary_restrictions == "nut free"


def test_numeric_boundary_fuzz_rejected_at_the_model():
    from pydantic import ValidationError

    from iparty.planning.models import PartyRequest

    base = dict(honoree_name="Edge", honoree_age=10, party_date=FUTURE,
                guest_count=10, budget=500.0)
    for mutation in ({"budget": float("inf")}, {"budget": float("nan")},
                     {"budget": 0}, {"budget": -0.01}, {"budget": 1_000_000.01},
                     {"guest_count": 0}, {"guest_count": 501},
                     {"honoree_age": 0}, {"honoree_age": 121},
                     {"honoree_name": "\x00\x01\x02"}):
        with pytest.raises(ValidationError):
            PartyRequest(**{**base, **mutation})
