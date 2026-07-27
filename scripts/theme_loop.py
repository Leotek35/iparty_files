"""Loop-engineering harness for the dynamic theme engine.

Runs 100 realistic customer theme strings through BOTH:
  1. the browser theme engine (extracted from web/index.html, run in node), and
  2. the live planning API (so a theme can never break plan verification),
then reports coverage, mismatches, and end-to-end health.

Usage: python scripts/theme_loop.py
Exit code is non-zero if any sample regresses.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

from fastapi.testclient import TestClient  # noqa: E402
from theme_samples import SAMPLES  # noqa: E402

from iparty.api.app import app  # noqa: E402


def run_theme_engine(themes: list[str]) -> list[dict]:
    """Extract the theme engine from the shipped UI and evaluate it in node."""
    with open(os.path.join(ROOT, "web", "index.html")) as fh:
        html = fh.read()
    block = re.search(r"const THEMES = \[[\s\S]*?function applyAmbient[\s\S]*?\n\}", html)
    if not block:
        raise SystemExit("theme engine not found in web/index.html")
    script = (
        block.group(0)
        + "\nconst __in=JSON.parse(process.argv[2]);"
        + "const __out=__in.map(t=>{const th=themeFor(t);const m=motifSVG(th.m);"
        + "return {theme:t,motif:th.m,c1:th.c1,c2:th.c2,ac:th.ac,"
        + "svg_ok:m[0].indexOf('<svg')===0,tile:m[1],amb:hexA(th.c1,0.12)};});"
        + "console.log(JSON.stringify(__out));"
    )
    js = os.path.join("/tmp", "_theme_probe.js")
    with open(js, "w") as fh:
        fh.write(script)
    out = subprocess.run(["node", js, json.dumps(themes)],
                         capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def main() -> int:
    themes = [t for t, _ in SAMPLES]
    expected = [e for _, e in SAMPLES]
    results = run_theme_engine(themes)

    client = TestClient(app)
    future = (date.today() + timedelta(days=30)).isoformat()

    hex_re = re.compile(r"^#[0-9A-Fa-f]{6}$")
    themed = mismatches = api_fail = invalid = 0
    problems: list[str] = []

    for i, r in enumerate(results):
        theme, want = themes[i], expected[i]
        # 1. engine output must always be structurally valid
        if not (hex_re.match(r["c1"]) and hex_re.match(r["c2"]) and r["svg_ok"]):
            invalid += 1
            problems.append(f"INVALID  {theme!r}: {r}")
        # 2. coverage: did we produce a distinctive skin?
        if r["motif"] != "confetti" or (want == "confetti"):
            themed += 1
        # 3. expectation match
        if want is not None and r["motif"] != want:
            mismatches += 1
            problems.append(f"MISMATCH {theme!r}: got {r['motif']}, expected {want}")
        # 4. end-to-end: the theme must never break planning
        resp = client.post("/api/v1/plan", json={
            "honoree_name": "Sample", "honoree_age": 7, "party_date": future,
            "guest_count": 12, "budget": 900.0, "theme": theme,
            "dietary_restrictions": "", "location_type": "home"})
        if resp.status_code != 200 or not resp.json()["verification"]["passed"]:
            api_fail += 1
            problems.append(f"API      {theme!r}: HTTP {resp.status_code}")

    distinct = len({r["motif"] for r in results})
    print(f"samples: {len(results)} | distinct motifs used: {distinct}")
    print(f"themed (non-generic or intentionally generic): {themed}/{len(results)}")
    print(f"expectation mismatches: {mismatches} | invalid engine output: {invalid} | api failures: {api_fail}")
    if problems:
        print("\n--- problems ---")
        for p in problems[:40]:
            print(" ", p)
    ok = (mismatches == 0 and invalid == 0 and api_fail == 0)
    print("\nRESULT:", "PASS" if ok else "NEEDS REFINEMENT")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
