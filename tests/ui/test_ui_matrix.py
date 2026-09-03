"""Opt-in browser matrix: the 100 MECE user profiles through the shipped UI.

    IPARTY_UI=1 pytest tests/ui -q            # stratified 17-profile smoke (desktop + phone)
    IPARTY_UI=1 IPARTY_UI_FULL=1 pytest tests/ui -q   # all 100 profiles

Needs `pip install playwright && playwright install chromium`; axe-core is
picked up from node_modules/axe-core or IPARTY_AXE when present, otherwise
the accessibility gate is skipped (reported, not failed).
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

pytestmark = pytest.mark.skipif(os.environ.get("IPARTY_UI") != "1", reason="browser matrix is opt-in: IPARTY_UI=1")

SMOKE_IDS = sorted({"001", "016", "031", "046", "061", "077", "091", "008", "023", "038", "053", "068", "084", "096",
                    "005", "027", "043"})  # two per partition + every host-panel state (ids ending 3/5/7)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    pytest.importorskip("playwright")
    port = _free_port()
    env = {**os.environ, "LLM_BACKEND": "mock", "PLANS_DB_PATH": str(tmp_path_factory.mktemp("db") / "iparty.db"),
           "PYTHONPATH": str(ROOT / "src")}
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "iparty.api.app:app", "--host", "127.0.0.1",
                             "--port", str(port), "--log-level", "warning"], cwd=ROOT, env=env)
    base = f"http://127.0.0.1:{port}"
    import httpx
    for _ in range(100):
        try:
            if httpx.get(base + "/health", timeout=1).status_code == 200:
                break
        except Exception:  # noqa: BLE001
            time.sleep(0.2)
    else:
        proc.kill()
        raise RuntimeError("server did not start")
    yield base
    proc.terminate()
    proc.wait(timeout=10)


@pytest.fixture(scope="module")
def results(server, tmp_path_factory):
    import asyncio

    from scripts.ui_matrix import Matrix, find_axe, select

    full = os.environ.get("IPARTY_UI_FULL") == "1"
    profiles = select(None, None) if full else select(",".join(SMOKE_IDS), None)
    out = Path(os.environ.get("IPARTY_UI_OUT", tmp_path_factory.mktemp("ui")))
    m = Matrix(server, out, find_axe(), concurrency=4, shots=True)
    return asyncio.run(m.run(profiles, mobile="all" if not full else "set"))


def test_every_profile_reaches_its_expected_outcome(results):
    s = results["summary"]
    assert not s["exceptions"], s["exceptions"]
    assert not s["mismatches"], s["mismatches"]
    assert not s["page_errors"], s["page_errors"]


def test_nothing_overflows_clips_or_is_too_small_to_tap(results):
    s = results["summary"]
    assert not s["overflow"], s["overflow"]
    assert not s["clipped"], s["clipped"]
    assert not s["small_targets"], s["small_targets"]


def test_no_serious_accessibility_violations(results):
    if results["axe"] == "skipped":
        pytest.skip("axe-core not installed (npm i axe-core or IPARTY_AXE=...)")
    assert not results["summary"]["axe_serious"], results["summary"]["axe_serious"]


def test_copy_is_human_and_flows_have_no_dead_ends(results):
    s = results["summary"]
    assert not s["visible_codes"], s["visible_codes"]
    assert s["retry"].get("failed", 0) == 0 and s["retry"].get("no_button", 0) == 0, s["retry"]
    assert not s["guest_when_24h"], s["guest_when_24h"]
    assert not s["guest_prefill_missing"], s["guest_prefill_missing"]
    assert not s["guests_hidden"], s["guests_hidden"]
    assert not s["booking_generic"], s["booking_generic"]
    assert not s["default_date_not_saturday"], s["default_date_not_saturday"]


def test_every_living_pass_state_was_exercised(results):
    assert {"verified", "attention", "unverifiable"} <= set(results["summary"]["living_states"]), results["summary"]["living_states"]


def test_accepting_a_fix_makes_the_plan_verified_again(results):
    s = results["summary"]
    assert not s["apply_failed"], s["apply_failed"]
    assert s["apply"].get("verified", 0) > 0, s["apply"]
