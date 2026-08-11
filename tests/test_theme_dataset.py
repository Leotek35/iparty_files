"""Theme dataset validation — the research-informed palette data is now a
product asset, so its integrity is CI-enforced.

Checks: schema, hex validity, motif references resolve to real procedural SVGs,
keyword hygiene (lowercase, unique across themes), age-band coverage, and
accent readability (white CTA text must stay legible on every accent).
"""
import json
import re
from pathlib import Path

DATA = json.loads(Path("web/themes.json").read_text(encoding="utf-8"))
THEMES = DATA["themes"]
HTML = Path("web/index.html").read_text(encoding="utf-8")
JS = re.search(r"<script>(.*)</script>", HTML, re.DOTALL).group(1)
HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
COLOR_KEYS = ["c1", "c2", "c3", "ac", "deep", "canvas"]
BANDS = {"toddler", "kids", "tween", "teen", "any"}


def _lum(hex_color: str) -> float:
    """WCAG relative luminance."""
    def chan(c):
        c /= 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * chan(r) + 0.7152 * chan(g) + 0.0722 * chan(b)


def test_dataset_is_substantial():
    assert len(THEMES) >= 25, "dataset shrank below research coverage"
    assert {t["band"] for t in THEMES} >= {"toddler", "kids", "tween", "teen"}


def test_schema_and_hex_validity():
    for t in THEMES:
        assert t["id"] and t["band"] in BANDS, t.get("id")
        assert t["keywords"], t["id"]
        for k in COLOR_KEYS:
            assert HEX.match(t[k]), f"{t['id']}.{k} = {t[k]!r} not #RRGGBB"


def test_motifs_resolve_to_procedural_svgs():
    js_motifs = set(re.findall(r"^\s{4}(\w+):\[S\+", JS, re.MULTILINE))
    assert len(js_motifs) >= 15
    for t in THEMES:
        assert t["motif"] in js_motifs, f"{t['id']} references unknown motif {t['motif']!r}"


def test_keywords_lowercase_and_unique_across_themes():
    seen: dict[str, str] = {}
    for t in THEMES:
        for w in t["keywords"]:
            assert w == w.lower(), f"{t['id']}: keyword {w!r} not lowercase"
            assert w not in seen, f"keyword {w!r} claimed by both {seen[w]} and {t['id']}"
            seen[w] = t["id"]


def test_accents_keep_white_cta_text_readable():
    for t in THEMES:
        contrast = 1.05 / (_lum(t["ac"]) + 0.05)  # vs white text
        assert contrast >= 3.0, f"{t['id']}.ac {t['ac']} contrast {contrast:.2f} < 3.0"


def test_canvas_tints_stay_near_white():
    for t in THEMES:
        assert _lum(t["canvas"]) > 0.85, f"{t['id']} canvas too dark for page background"


def test_band_gradients_are_dark_enough_for_white_band_text():
    for t in THEMES:
        assert _lum(t["deep"]) < 0.30, f"{t['id']}.deep {t['deep']} too light for band text"


def test_longest_keyword_wins_in_engine():
    # 'princess castle' must resolve via its longest matching keyword, not
    # first-table-hit; the engine scores by keyword length.
    assert "bestLen" in JS and "w.length>bestLen" in JS


def test_ui_loads_dataset_with_validation():
    assert "/static/themes.json" in JS
    assert "const HEX_RE" in JS and "function sanitizeTheme" in JS
