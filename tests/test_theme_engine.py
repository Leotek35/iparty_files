"""Theme-engine regressions found by the 100-sample loop (scripts/theme_loop.py).

The engine lives in web/index.html and runs in the browser, so these tests
evaluate it in node — the same code the customer actually gets.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

UI = Path(__file__).resolve().parents[1] / "web" / "index.html"
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not available")


def _eval_themes(themes):
    html = UI.read_text()
    block = re.search(r"const THEMES = \[[\s\S]*?function applyAmbient[\s\S]*?\n\}", html)
    assert block, "theme engine not found in web/index.html"
    script = (block.group(0) +
              "\nconst i=JSON.parse(process.argv[2]);"
              "console.log(JSON.stringify(i.map(t=>{const th=themeFor(t);const m=motifSVG(th.m);"
              "return{motif:th.m,c1:th.c1,c2:th.c2,svg:m[0].slice(0,4),amb:hexA(th.c1,0.12)};})));")
    tmp = Path("/tmp/_theme_test.js")
    tmp.write_text(script)
    out = subprocess.run(["node", str(tmp), json.dumps(themes)],
                         capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


@pytest.mark.parametrize("theme,motif", [
    ("Spider-Man", "web"), ("Frozen", "snow"), ("Space adventure", "stars"),
    ("Under the Sea", "waves"), ("Dino explorers", "leaves"), ("Racing cars", "checkers"),
    ("Disco party", "notes"), ("Unicorn magic", "confetti"), ("Valentine tea", "hearts"),
    ("Batman", "burst"),
])
def test_core_themes_map_to_expected_motifs(theme, motif):
    assert _eval_themes([theme])[0]["motif"] == motif


@pytest.mark.parametrize("theme,motif", [
    # defects the 100-sample loop surfaced — must never regress
    ("Wonder Woman", "burst"), ("polar express", "snow"), ("Jurassic party", "leaves"),
    ("T-rex takeover", "leaves"), ("Hot wheels", "checkers"), ("Monster trucks", "checkers"),
    ("Karaoke night", "notes"),
    # precedence: a specific phrase must beat a broad substring
    ("Pop star", "notes"),          # "pop star" > "star"
    ("Ocean explorers", "waves"),   # "ocean" must win, not a generic word
])
def test_loop_discovered_theme_regressions(theme, motif):
    assert _eval_themes([theme])[0]["motif"] == motif


def test_generic_themes_fall_back_gracefully():
    for r in _eval_themes(["Birthday bash", "Tea party", "Graduation", ""]):
        assert r["motif"] == "confetti"
        assert re.fullmatch(r"#[0-9A-Fa-f]{6}", r["c1"])


@pytest.mark.parametrize("payload", [
    'red");background:url(//evil.com/x);--x:"',
    "</script><script>alert(1)</script>",
    "expression(alert(1))",
    "__proto__", "constructor", "spider" * 5000, "‮evil",
])
def test_hostile_theme_text_cannot_escape_the_lookup_table(payload):
    """User text only SELECTS a theme; it never becomes a color or URL."""
    r = _eval_themes([payload])[0]
    assert re.fullmatch(r"#[0-9A-Fa-f]{6}", r["c1"])
    assert re.fullmatch(r"#[0-9A-Fa-f]{6}", r["c2"])
    assert re.fullmatch(r"#[0-9A-Fa-f]{8}", r["amb"])
    assert r["svg"] == "<svg"
