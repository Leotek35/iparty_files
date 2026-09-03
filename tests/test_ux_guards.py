"""UX/UI guards from the 100-profile browser matrix (Playwright + axe-core).

Each guard locks in a finding that the real UI produced under a real user
profile — a phone that scrolled sideways, grey text below WCAG AA, a raw
`INSUFFICIENT_FOOD` code shown to a parent, a dead end after "can't be done".
They read the shipped HTML statically so they run in the ordinary suite; the
browser matrix itself is opt-in (`IPARTY_UI=1 pytest tests/ui`).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

INDEX = Path("web/index.html").read_text(encoding="utf-8")
RSVP = Path("web/rsvp.html").read_text(encoding="utf-8")
INDEX_JS = "\n".join(re.findall(r"<script>(.*?)</script>", INDEX, re.DOTALL))
RSVP_JS = "\n".join(re.findall(r"<script>(.*?)</script>", RSVP, re.DOTALL))


# ---------------------------------------------------------------- colour math
def _token(css: str, name: str) -> str:
    m = re.search(rf"--{re.escape(name)}\s*:\s*(#[0-9A-Fa-f]{{6}})", css)
    assert m, f"token --{name} not found"
    return m.group(1)


def _lum(hex6: str) -> float:
    def ch(v: int) -> float:
        c = v / 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (int(hex6[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(a: str, b: str) -> float:
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


@pytest.mark.parametrize("page,css", [("index", INDEX), ("rsvp", RSVP)])
def test_secondary_text_tokens_meet_wcag_aa_on_every_background(page, css):
    """U1: 121 axe contrast nodes came from --ink-3 (#AEAEB2, 2.0:1). Every grey
    text token must clear 4.5:1 on canvas, surface and the fill it sits on."""
    backgrounds = [_token(css, "canvas"), _token(css, "surface")]
    if "--fill:" in css:
        backgrounds.append(_token(css, "fill"))
    for tok in ("ink", "ink-2", "ink-3"):
        colour = _token(css, tok)
        for bg in backgrounds:
            assert contrast(colour, bg) >= 4.5, (page, tok, colour, bg, round(contrast(colour, bg), 2))


def test_live_cta_uses_the_aa_green_for_white_text():
    """U1: white on the bright --verify green is ~3.2:1; the Living Pass CTA and
    hover state must use the darker verify-text green."""
    assert contrast("#FFFFFF", _token(INDEX, "verify-text")) >= 4.5
    assert re.search(r"\.cta\.live\{background:var\(--verify-text\)\}", INDEX)
    hover = re.search(r"\.cta\.live:hover\{background:(#[0-9A-Fa-f]{6})\}", INDEX)
    assert hover and contrast("#FFFFFF", hover.group(1)) >= 4.5


# ---------------------------------------------------------------- layout
def test_stage_grid_items_may_shrink_so_phones_never_scroll_sideways():
    """E1: on 390px the .stage grid track widened to the pass's min-content
    (421px) and the whole page scrolled horizontally by 55px."""
    assert re.search(r"\.stage\s*>\s*\*\s*\{[^}]*min-width\s*:\s*0", INDEX)


def test_receipt_lines_truncate_instead_of_escaping_the_card():
    """Round 2: on a phone the fix receipt's amount was pushed 47–84 px past
    the card edge — a single implicit grid column sizes to the widest line's
    max-content, and a nowrap flex child without min-width:0 refuses to shrink."""
    assert re.search(r"\.line \.what\{[^}]*min-width\s*:\s*0", INDEX)
    assert re.search(r"\.line \.amt\{[^}]*flex\s*:\s*none", INDEX)
    for grid in (".receipt", ".checks", ".lv-links", ".lv-guests ul", ".modal form"):
        rule = re.search(re.escape(grid) + r"\{[^}]*\}", INDEX)
        assert rule and "grid-template-columns:minmax(0,1fr)" in rule.group(0), grid
    # and on phones the description wraps rather than losing its quantity to an ellipsis
    mobile = re.search(r"@media\(max-width:560px\)\{(.*?)\n\}", INDEX, re.DOTALL)
    assert mobile and re.search(r"\.line \.what\{[^}]*white-space:normal", mobile.group(1))


def test_theme_chips_are_finger_sized():
    """U2: theme chips measured 31px tall — below the 44px touch minimum."""
    m = re.search(r"\.chips button\{[^}]*min-height\s*:\s*(\d+)px", INDEX)
    assert m and int(m.group(1)) >= 44, m.group(0) if m else "no min-height on .chips button"


def test_infeasible_action_row_wraps_on_narrow_screens():
    assert re.search(r"\.fb-row\{[^}]*flex-wrap\s*:\s*wrap", INDEX)


# ---------------------------------------------------------------- form defaults
def test_allergy_field_starts_empty():
    """U7: the field defaulted to 'gluten-free', so most profiles silently
    planned a gluten-free party they never asked for."""
    m = re.search(r'<input id="dietary_restrictions"[^>]*>', INDEX)
    assert m and 'value=""' in m.group(0), m.group(0) if m else "field missing"


def test_default_date_is_a_saturday_three_weeks_out_and_set_once():
    """U8: a mid-week default date made every 'untouched' submission a
    Wednesday party. Exactly one default-setter, and it picks a Saturday."""
    setters = re.findall(r'\$\("party_date"\)\.value\s*=', INDEX_JS)
    assert len(setters) == 0
    setters = re.findall(r"\bd\.value\s*=\s*`\$\{t\.getFullYear\(\)\}", INDEX_JS)
    assert len(setters) == 1
    assert "while(t.getDay()!==6)" in INDEX_JS and "getDate()+21" in INDEX_JS
    assert "toISOString().slice(0,10)" not in INDEX_JS  # UTC drift made a local Saturday a Sunday


# ---------------------------------------------------------------- copy: human, not machine
def test_living_status_never_shows_machine_codes():
    """U3: hosts saw 'INSUFFICIENT_FOOD' next to the plain-English message."""
    m = re.search(r"function renderLiving\(.*?\n\}", INDEX_JS, re.DOTALL)
    assert m, "renderLiving missing"
    body = m.group(0)
    assert "lv-code" not in body
    assert 'data-code="${esc(a.code)}"' in body  # still available to tests and support
    assert not re.search(r">\$\{esc\(a\.code\)\}<", body)


def test_infeasible_screen_offers_a_one_tap_retry_at_the_minimum_budget():
    """U4: 'can't be done at $X — minimum is $Y' was a dead end."""
    assert 'id="retry-min"' in INDEX_JS
    assert re.search(r'\$\("budget"\)\.value\s*=\s*String\(Math\.ceil\(min\)\)', INDEX_JS)
    assert '$("party-form").requestSubmit()' in INDEX_JS


def test_booking_422_surfaces_the_field_message():
    """E5: a bad email showed the generic 'Something went wrong'."""
    assert "function fieldMessage(" in INDEX_JS
    assert re.search(r"r\.status===422 \? \(fieldMessage\(d\) \|\|", INDEX_JS)


def test_host_link_failures_have_specific_copy():
    """E3: a stale or mistyped host link spun forever on 'checking…'."""
    assert "This host link isn't valid" in INDEX_JS
    assert "This party can't be found" in INDEX_JS


def test_host_can_see_who_replied_and_share_the_invite():
    """U6/U9: the status showed counts but never names; no native share."""
    assert 'class="lv-guests"' in INDEX_JS and "lv-yes" in INDEX_JS and "lv-no" in INDEX_JS
    assert re.search(r"navigator\.share\?`<button[^`]*id=\"lv-share\"", INDEX_JS)


def test_every_proposal_on_the_host_panel_can_be_accepted():
    """Round 2: the panel showed a verified fix, a right-size plan and an honest
    minimum budget, and the host could act on none of them."""
    assert 'data-apply="fix"' in INDEX_JS and 'data-apply="right_size"' in INDEX_JS and 'data-apply="budget"' in INDEX_JS
    assert "async function applyProposal(" in INDEX_JS and "/apply`" in INDEX_JS
    assert '"X-Host-Token":LIVING.hostToken' in INDEX_JS
    assert "refreshPassInPlace(d.plan, d.request)" in INDEX_JS  # the pass above the panel shows what is now saved
    for needle in ("can't be verified for the current guest list", "Too many changes", "Network hiccup"):
        assert needle in INDEX_JS, needle


def test_right_size_copy_is_calm_and_distinguishes_final_from_early():
    """U5: 'save $518' after the first RSVP read as a demand to downsize."""
    assert "IF IT STAYS AT" in INDEX_JS and "No rush; this updates as more people respond." in INDEX_JS
    assert "EVERYONE HAS ANSWERED" in INDEX_JS and "rs.final" in INDEX_JS


# ---------------------------------------------------------------- time & guest page
def test_times_render_in_twelve_hour_clock_everywhere():
    """E6: the invite said '14:00–17:00' while the host page said the same in
    mono — parents read '2:00 PM'."""
    for js, page in ((INDEX_JS, "index"), (RSVP_JS, "rsvp")):
        assert re.search(r"(const|function) fmtTime", js), page
        assert 'hour:"numeric",minute:"2-digit"' in js, page
    assert "fmtTime(inv.starts)" in RSVP_JS and "fmtTime(inv.ends)" in RSVP_JS
    assert "fmtTime(s.start)" in INDEX_JS and "fmtTime(s.end)" in INDEX_JS
    assert not re.search(r"\$\{esc\(s\.start\)\}", INDEX_JS)


def test_guest_page_prefills_a_previous_answer_and_keeps_textcontent_only():
    """U11: 'Change my RSVP' returned a blank form. Prefill from the same
    device, without ever inserting server strings as HTML."""
    assert "function lastAnswers(" in RSVP_JS and "rememberAnswers(body)" in RSVP_JS
    assert "You've already replied from this device" in RSVP_JS
    assert "innerHTML" not in RSVP_JS and "insertAdjacentHTML" not in RSVP_JS


def test_guest_page_error_copy_covers_every_server_status():
    for needle in ("guest list is full", "Too many responses right now", "no longer available",
                   "Please check your name and party size", "Network hiccup"):
        assert needle in RSVP_JS, needle
