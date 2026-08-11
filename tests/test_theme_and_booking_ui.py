"""Static guards for the dynamic theme engine + booking flow (loop findings).

Security loop: the free-text theme must NEVER reach an HTML/CSS sink — it is
only matched against the keyword table. Booking modal sinks must escape.
Product loop: ambient background + themed pass must react to the theme input.
"""
import re
from pathlib import Path

HTML = Path("web/index.html").read_text(encoding="utf-8")
JS = re.search(r"<script>(.*)</script>", HTML, re.DOTALL).group(1)


# ---------- theme engine presence & wiring ----------

def test_theme_engine_core_present():
    for marker in ["let THEME_DATA", "function themeFor", "function motifSVG",
                   "function applyAmbient", "function themeHead", "function sanitizeTheme"]:
        assert marker in JS, f"theme engine lost: {marker}"


def test_ambient_layers_in_dom_and_css():
    assert 'id="amb-grad"' in HTML and 'id="amb-motif"' in HTML
    assert "ambDrift" in HTML and "motifDrift" in HTML, "ambient animations missing"
    assert "prefers-reduced-motion" in HTML


def test_theme_input_live_wired():
    assert re.search(r'\$\("theme"\)\.addEventListener\("input"', JS)
    assert "applyAmbient($(\"theme\").value)" in JS, "no initial ambient application"


def test_result_pass_gets_themed():
    assert re.search(r'themeHead\(\$\("pass-band"\)', JS), "verified pass no longer themed"


def test_bluey_theme_exists_with_paws():
    import json
    data = json.loads(Path("web/themes.json").read_text(encoding="utf-8"))
    bluey = next(t for t in data["themes"] if t["id"] == "bluey")
    assert bluey["motif"] == "paws" and "paws" in JS


def test_hero_pass_reacts_to_theme():
    assert 'id="hero-band"' in HTML
    assert 'themeHead($("hero-band")' in JS


# ---------- security: theme text must never hit a sink ----------

def test_theme_text_never_interpolated_into_html_or_css():
    # The raw theme input may only be passed to themeFor()/applyAmbient();
    # any template interpolation of it is an XSS/CSS-injection vector.
    assert not re.search(r"\$\{[^}]*\$\(\"theme\"\)", JS)
    assert not re.search(r"innerHTML[^\n]*\$\(\"theme\"\)\.value", JS)
    # style assignments built from the fixed palette only, never from user text
    for m in re.finditer(r"style\.background\s*=\s*`([^`]*)`", JS):
        assert "value" not in m.group(1), "user text flowing into CSS"


def test_motifs_are_procedural_data_uris():
    assert "encodeURIComponent" in JS
    assert not re.search(r"url\(['\"]?https?://", HTML), "external asset crept in"


# ---------- booking flow ----------

def test_booking_modal_present_and_wired():
    for marker in ["function openBooking", 'id="book-form"', "bk-email",
                   "/api/v1/bookings", "booking_ref"]:
        assert marker in JS, f"booking flow lost: {marker}"
    assert re.search(r'\$\("book-btn"\)\.addEventListener\("click",\s*\(\)=>openBooking', JS)


def _booking_segment():
    start = JS.index("function openBooking")
    end = JS.find("\nfunction ", start + 10)
    return JS[start:end if end > 0 else len(JS)]


def test_booking_sinks_escaped():
    # every interpolation inside openBooking's template literals must be esc()'d,
    # fmt()'d, or a purely numeric/fixed value.
    seg = _booking_segment()
    # th.* colors are safe: hex-validated by sanitizeTheme() before use.
    allowed = re.compile(
        r"esc\(|fmt\(|req\.guest_count|req\.honoree_age|th\.c1|th\.c2|th\.deep|size|url\.replace")
    for m in re.finditer(r"\$\{([^}]+)\}", seg):
        assert allowed.match(m.group(1).strip()), f"unescaped modal sink: {m.group(1)!r}"


def test_booking_modal_a11y():
    # Triage A11Y-1: dialog semantics + focus restoration on close.
    seg = _booking_segment()
    assert 'role="dialog"' in seg and 'aria-modal="true"' in seg
    assert "opener.focus()" in seg


def test_booking_error_paths_handled():
    for code in ["429", "422"]:
        assert code in _booking_segment(), f"no UX for HTTP {code}"


def test_ticket_rendered_on_success():
    seg = _booking_segment()
    assert "PARTY TICKET" in seg and "t-ref" in seg
