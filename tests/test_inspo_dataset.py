"""Inspo board accuracy invariants — CI-enforced like the theme dataset.

Impeccable-accuracy contract: every theme in themes.json has a matching inspo
entry (no theme ever renders an empty board), games exist for every age band,
outbound discovery goes ONLY to Pinterest/TikTok search URLs built from
encodeURIComponent'd text, and all rendered strings pass through esc().
"""
import json
import re
from pathlib import Path

INSPO = json.loads(Path("web/inspo.json").read_text(encoding="utf-8"))
THEMES = json.loads(Path("web/themes.json").read_text(encoding="utf-8"))["themes"]
HTML = Path("web/index.html").read_text(encoding="utf-8")
JS = re.search(r"<script>(.*)</script>", HTML, re.DOTALL).group(1)


def test_every_theme_has_full_inspo_coverage():
    inspo_ids = set(INSPO["themes"].keys())
    for t in THEMES:
        assert t["id"] in inspo_ids, f"theme {t['id']} has no inspo entry"
        e = INSPO["themes"][t["id"]]
        assert len(e["decor"]) == 3, f"{t['id']}: need exactly 3 decor ideas"
        assert isinstance(e["game"], str) and len(e["game"]) > 10
        assert len(e["treats"]) == 2, f"{t['id']}: need exactly 2 treats"


def test_no_orphan_inspo_entries():
    theme_ids = {t["id"] for t in THEMES}
    for tid in INSPO["themes"]:
        assert tid in theme_ids, f"inspo entry {tid!r} references a deleted theme"


def test_games_exist_for_every_age_band():
    for band in ("toddler", "kids", "tween", "teen"):
        games = INSPO["games_by_band"][band]
        assert len(games) >= 3, f"band {band} needs >=3 games"
        for g in games:
            assert 8 < len(g) <= 90


def test_age_appropriateness_markers():
    # Research-grounded gates: no elimination-style classics for toddlers;
    # no toddler games leaking into the teen pool.
    toddler = " ".join(INSPO["games_by_band"]["toddler"]).lower()
    teen = " ".join(INSPO["games_by_band"]["teen"]).lower()
    for banned in ("musical chairs", "elimination", "trivia"):
        assert banned not in toddler, f"toddler band contains {banned!r}"
    for banned in ("bubble", "sensory bin", "duck, duck"):
        assert banned not in teen, f"teen band contains {banned!r}"


def test_no_copyrighted_asset_urls_in_inspo():
    text = json.dumps(INSPO).lower()
    assert "http" not in text, "inspo dataset must not embed external URLs"


def test_ui_renders_inspo_with_escaping_and_safe_links():
    assert "function inspoHTML" in JS and "function bandFor" in JS
    seg = JS[JS.index("function inspoHTML"):JS.index("function inspoHTML") + 1600]
    assert "esc(x)" in seg, "inspo items must be escaped"
    assert "encodeURIComponent" in seg, "search query must be URI-encoded"
    for allowed in ("https://www.pinterest.com/search/pins/?q=", "https://www.tiktok.com/search?q="):
        assert allowed in seg
    urls = re.findall(r'https://[^"\'`\s)]+', seg)
    for u in urls:
        assert u.startswith(("https://www.pinterest.com/", "https://www.tiktok.com/")), \
            f"unexpected outbound domain in inspo: {u}"
    assert 'rel="noopener noreferrer"' in seg


def test_ui_pro_max_checklist_applied():
    # Items adopted from the ui-ux-pro-max design system generation.
    assert "Baloo 2" in HTML, "playful display font lost"
    assert 'href="#vendors"' in HTML, "marketplace pattern: vendor CTA in nav"
    assert 'id="theme-chips"' in HTML, "popular-searches suggestions lost"
    assert "prefers-reduced-motion" in HTML
    app_src = Path("src/iparty/api/app.py").read_text(encoding="utf-8")
    assert "fonts.googleapis.com" in app_src and "fonts.gstatic.com" in app_src, \
        "CSP must allowlist the font origins it uses"
