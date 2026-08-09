"""100-iteration adversarial loop harness: user simulation + penetration probes.

Each iteration builds a randomized hostile-ish user profile, sends it through the
live API, and asserts the product's safety/economic invariants. Every 5th
iteration also fires a rotating penetration probe. Findings are reported by
class, not just counted, so each one is actionable.

Usage:  PYTHONPATH=src python3 scripts/loop_harness.py --loops 100
"""
from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from iparty.pricing.catalog import (  # noqa: E402
    StaticCatalog,
    parse_forbidden_allergens,
    requires_vegetarian,
    unverifiable_dietary,
)

BASE = "http://127.0.0.1:8061"
CAT = StaticCatalog()

NAMES = ["Aria", "José", "Zoë", "Muhammad", "Priya", "Wei", "Ngũgĩ", "O'Brien",
         "Александр", "小明", "Fatima-Zahra", "Max", "<b>Bold</b>", "Ann-Marie",
         "  spaced  ", "X" * 90]
DIETS = ["", "", "nut allergy", "gluten-free", "vegan", "vegetarian", "dairy-free",
         "halal", "kosher", "no pork", "coeliac", "shellfish allergy", "sesame allergy",
         "peanut and tree nut allergy", "egg-free and dairy-free", "lactose intolerant",
         "NUT ALLERGY", "  vegan  ", "nut-free please"]
LOCS = ["home", "venue", "park", "restaurant"]
THEMES = ["", "Space", "Dinosaurs", "Frozen", "T" * 80, "<script>x</script>"]


def _hdrs(headers) -> dict:
    """HTTP header names are case-insensitive; normalise so probes can't be
    fooled by server casing (this bug produced a false PEN-CTYPE finding)."""
    return {k.lower(): v for k, v in dict(headers).items()}


def post(path: str, body, headers=None, timeout=30):
    h = {"Content-Type": "application/json"}
    h.update(headers or {})
    data = body if isinstance(body, bytes) else json.dumps(body).encode()
    req = urllib.request.Request(BASE + path, data=data, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return r.status, _hdrs(r.headers), (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, _hdrs(e.headers), (json.loads(raw) if raw else None)
        except json.JSONDecodeError:
            return e.code, _hdrs(e.headers), None
    except Exception as exc:  # noqa: BLE001
        return "ERR", {}, str(exc)


def get(path: str, headers=None):
    req = urllib.request.Request(BASE + path, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read()
            return r.status, _hdrs(r.headers), (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        return e.code, _hdrs(e.headers), None
    except Exception as exc:  # noqa: BLE001
        return "ERR", {}, str(exc)


def profile(rng: random.Random) -> dict:
    return {
        "honoree_name": rng.choice(NAMES),
        "honoree_age": rng.choice([1, 2, 3, 5, 7, 9, 12, 14, 16, 17]),
        "party_date": (date.today() + timedelta(days=rng.randint(1, 200))).isoformat(),
        "guest_count": rng.choice([1, 2, 6, 10, 14, 22, 35, 60, 120, 300]),
        "budget": rng.choice([20, 45, 95, 180, 320, 550, 900, 1800, 5000]),
        "theme": rng.choice(THEMES),
        "dietary_restrictions": rng.choice(DIETS),
        "location_type": rng.choice(LOCS),
    }


def check_invariants(req: dict, body: dict, findings: list) -> None:
    """Safety + economic invariants that must hold for EVERY verified plan."""
    plan = body["plan"]
    diet = req["dietary_restrictions"]

    if plan["total_cost"] > req["budget"] + 0.01:
        findings.append(("INV-BUDGET", f"{plan['total_cost']} > {req['budget']}"))

    servings = sum(m["servings"] for m in plan["menu"])
    if servings < req["guest_count"]:
        findings.append(("INV-PORTIONS", f"{servings} servings < {req['guest_count']} guests"))

    forbidden = parse_forbidden_allergens(diet)
    if forbidden:
        for m in plan["menu"]:
            if forbidden & set(m["allergens"]):
                findings.append(("INV-ALLERGEN", f"{diet}: {m['name']} has {m['allergens']}"))

    if requires_vegetarian(diet):
        for m in plan["menu"]:
            sku = m.get("sku")
            item = CAT.get(sku) if sku else None
            if item is not None and not item.vegetarian:
                findings.append(("INV-VEGETARIAN", f"{diet}: {m['name']} not vegetarian"))

    if unverifiable_dietary(diet) is not None:
        findings.append(("INV-FAIL-CLOSED", f"unverifiable '{diet}' shipped as verified"))

    if plan["total_cost"] <= 0:
        findings.append(("INV-PRICE", "non-positive total"))

    for li in plan["line_items"]:
        if li["subtotal"] < 0 or li["quantity"] < 1:
            findings.append(("INV-LINEITEM", f"{li['description']} qty={li['quantity']}"))


def pen_probe(idx: int, findings: list) -> str:
    """Rotating penetration probes; returns the probe name."""
    d = (date.today() + timedelta(days=15)).isoformat()
    ok = {"honoree_name": "A", "honoree_age": 6, "party_date": d, "guest_count": 10,
          "budget": 600, "theme": "", "dietary_restrictions": "", "location_type": "home"}
    probes = [
        ("headers-CSP", lambda: (
            "content-security-policy" in {k.lower() for k in get("/health")[1]}
            or findings.append(("PEN-HEADERS", "CSP missing")))),
        ("json-not-html", lambda: (
            "application/json" in post("/api/v1/plan", {**ok, "honoree_name": "<script>a()</script>"})[1]
            .get("content-type", "")
            or findings.append(("PEN-CTYPE", "plan response not JSON")))),
        ("oversized-field", lambda: (
            post("/api/v1/plan", {**ok, "honoree_name": "x" * 50000})[0] == 422
            or findings.append(("PEN-OVERSIZE", "huge field not rejected")))),
        ("traversal-session", lambda: (
            post("/api/v1/events", {"session_id": "../../etc/passwd", "event": "page_view",
                                    "meta": {}})[0] == 422
            or findings.append(("PEN-TRAVERSAL", "traversal session_id accepted")))),
        ("meta-injection", lambda: (
            post("/api/v1/events", {"session_id": "pen-00001-abcd", "event": "page_view",
                                    "meta": {"evil": "y" * 50000}})[0] == 422
            or findings.append(("PEN-META", "unwhitelisted meta accepted")))),
        ("bad-method", lambda: (
            get("/api/v1/plan")[0] in (405, 404)
            or findings.append(("PEN-METHOD", "GET /plan not rejected")))),
        ("negative-budget", lambda: (
            post("/api/v1/plan", {**ok, "budget": -50})[0] == 422
            or findings.append(("PEN-NEGATIVE", "negative budget accepted")))),
        ("past-date", lambda: (
            post("/api/v1/plan", {**ok, "party_date": "2020-01-01"})[0] == 422
            or findings.append(("PEN-PASTDATE", "past date accepted")))),
        ("null-injection", lambda: (
            post("/api/v1/plan", {**ok, "honoree_name": None})[0] == 422
            or findings.append(("PEN-NULL", "null name accepted")))),
        ("malformed-json", lambda: (
            post("/api/v1/plan", b'{"honoree_name": "x", ')[0] in (400, 422)
            or findings.append(("PEN-MALFORMED", "malformed JSON not rejected")))),
    ]
    name, fn = probes[idx % len(probes)]
    try:
        fn()
    except Exception as exc:  # noqa: BLE001
        findings.append(("PEN-CRASH", f"{name}: {type(exc).__name__} {exc}"))
    return name


def main(loops: int, seed: int) -> int:
    rng = random.Random(seed)
    env = {**os.environ, "PYTHONPATH": "src", "EVENTS_PATH": "data/loop.jsonl",
           "PLAN_RATE_PER_MIN": "100000", "EVENTS_RATE_PER_MIN": "100000"}
    srv = subprocess.Popen(
        ["python3", "-m", "uvicorn", "iparty.api.app:app", "--host", "127.0.0.1", "--port", "8061"],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(4)
    findings: list[tuple[str, str]] = []
    statuses: Counter = Counter()
    probes_run: Counter = Counter()
    latencies: list[float] = []
    try:
        for i in range(loops):
            req = profile(rng)
            t0 = time.monotonic()
            st, _h, body = post("/api/v1/plan", req)
            latencies.append(time.monotonic() - t0)
            statuses[st] += 1
            if st == 200:
                check_invariants(req, body, findings)
            elif st == 409:
                det = (body or {}).get("detail", {})
                if not det.get("violations"):
                    findings.append(("INV-REFUSAL", "409 without violations"))
            elif st == 422:
                pass  # malformed by construction (e.g. 90-char name) — correct rejection
            else:
                findings.append(("INV-STATUS", f"unexpected status {st}"))
            if i % 5 == 0:
                probes_run[pen_probe(i // 5, findings)] += 1
            if (i + 1) % 25 == 0:
                print(f"  loop {i+1}/{loops}  findings so far: {len(findings)}")
    finally:
        srv.terminate()

    lat = sorted(latencies)
    print("\n" + "=" * 60)
    print(f"LOOPS: {loops}   pen-probes fired: {sum(probes_run.values())} "
          f"({len(probes_run)} distinct)")
    print(f"STATUS: {dict(statuses)}")
    print(f"LATENCY p50/p95: {lat[len(lat)//2]*1000:.0f}ms / {lat[int(len(lat)*.95)-1]*1000:.0f}ms")
    print("=" * 60)
    if findings:
        print("FINDINGS:")
        for cls, _detail in Counter(f"{c} :: {d}" for c, d in findings).most_common():
            print(f"  {cls}")
        return 1
    print("NO INVARIANT OR PENETRATION FAILURES ACROSS ALL LOOPS.")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--loops", type=int, default=100)
    ap.add_argument("--seed", type=int, default=7)
    raise SystemExit(main(*vars(ap.parse_args()).values()))
