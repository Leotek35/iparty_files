"""Static frontend guards from the multi-role loop pipeline.

These lock in the Security, PM, and Legal loop findings so they can never
silently regress: XSS escaping in every HTML sink, and truthful copy.
"""
import re
from pathlib import Path

HTML = Path("web/index.html").read_text()
JS = re.search(r"<script>(.*)</script>", HTML, re.DOTALL).group(1)

USER_STRINGS = (r"req\.honoree_name|req\.dietary_restrictions|p\.theme|p\.venue|"
                r"m\.name|li\.description|s\.activity|p\.notes|v\.message")


def _owner_function(pos: int) -> str:
    owner = "top-level"
    for m in re.finditer(r"function (\w+)", JS):
        if m.start() < pos:
            owner = m.group(1)
        else:
            break
    return owner


def test_esc_helper_exists():
    assert "const esc" in JS


def test_no_unescaped_user_strings_in_html_sinks():
    html_sinks = {"renderPass", "renderInfeasible", "verifyingSkeleton",
                  "checklistFor", "renderTelemetry", "renderUnavailable"}
    raw = [m for m in re.finditer(r"\$\{(?:" + USER_STRINGS + r")\}", JS)
           if _owner_function(m.start()) in html_sinks]
    assert not raw, f"unescaped user strings in HTML sinks: {len(raw)}"


def test_no_overclaims_in_copy():
    banned = [r"guarantee[sd]?\s+(the\s+)?(party|safe|safety|allergen)",
              r"100%\s*safe", r"allerg\w*[-\s]free\b", r"\breal catalog\b", r"medical"]
    hits = [m.group(0) for pat in banned for m in re.finditer(pat, HTML, re.IGNORECASE)]
    assert not hits, hits


def test_funnel_events_present_in_ui():
    for ev in ["page_view", "form_started", "plan_requested", "plan_verified",
               "plan_infeasible", "plan_unavailable", "plan_copied",
               "plan_downloaded", "booking_interest", "feedback_answered"]:
        assert ev in JS, f"UI no longer fires {ev}"


def test_security_headers_middleware():
    app_src = Path("src/iparty/api/app.py").read_text()
    for header in ["X-Content-Type-Options", "X-Frame-Options", "Referrer-Policy"]:
        assert header in app_src
