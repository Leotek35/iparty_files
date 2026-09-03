"""100-profile MECE UX/UI matrix against the real iParty app (Playwright + axe-core).

Drives the shipped HTML the way a person would, one browser context per user
profile from tests/mece_profiles.py:

  desktop 1280x900 (every profile) and a stratified phone set at 390x844
    fill the form -> outcome (verified pass | infeasible | native-validation block)
    -> checks: page errors, horizontal overflow, clipped text, tap targets < 40px,
       axe-core WCAG 2.1 AA
    -> infeasible: the one-tap "Plan it at $min" retry must land on a verified pass
    -> verified: Make it a Living Pass -> guest RSVPs on a phone (some with an
       allergy / halal / an 8-person party to reach every host-panel state)
       -> host panel updates -> guest "Change my RSVP" is prefilled
    -> email profiles: booking modal with the bad email -> inline field message
  plus synthetic hard cases (unverifiable dietary at plan time, invalid invite
  link, tampered host link).

Writes <out>/results.json and a gate summary; exits non-zero with --strict when
a gate fails. Opt-in pytest wrapper: tests/ui/test_ui_matrix.py (IPARTY_UI=1).

    pip install playwright && playwright install chromium
    npm i axe-core            # optional; or IPARTY_AXE=/path/to/axe.min.js
    python scripts/ui_matrix.py --base http://127.0.0.1:8000 --out .ui-out --strict
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import sys
import time
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.mece_profiles import PROFILES_MECE, build_request  # noqa: E402

FUTURE = (date.today() + timedelta(days=45)).isoformat()
DESKTOP = {"width": 1280, "height": 900}
MOBILE = {"width": 390, "height": 844}
# two per partition, spread across the id range, plus the email/fuzz edges
MOBILE_SET = {"001", "016", "031", "046", "061", "077", "091", "008", "023", "038", "053", "068", "084", "096"}
CLIP_SELECTORS = (".pass .title, .pass .meta, .lv-pill, .lv-counts, .lv-links input, .line .what, .tag, .chip, "
                  ".chk .what, .chk .detail, #app-rsvp .title, .band .title, .fact .v, .done h2")
# containers whose children must never escape (a receipt amount pushed past the card edge on a phone)
ESCAPE_SELECTORS = ".line, .receipt, .lv-fix, .lv-fixtotal, .lv-links, .living, .checks, .facts, .done, form"  # not .pass: its overflow:hidden clips decoration by design
EXPECTED = {"pass": "verified", "pass_sanitized": "verified", "email_error": "verified",
            "feasibility_error": "infeasible", "validation_error": "blocked_native"}

JS_CHECKS = r"""
() => {
  const res = {overflow: document.documentElement.scrollWidth - window.innerWidth, clipped: [], small: []};
  const vis = (el) => { const r = el.getBoundingClientRect(); const cs = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none'; };
  document.querySelectorAll(%SEL%).forEach(el => {
    if (!vis(el) || (el.tagName === 'INPUT' && el.readOnly)) return;  // readonly link fields scroll by design; Copy/Share sit beside them
    const cs = getComputedStyle(el);
    const singleLine = cs.whiteSpace === 'nowrap' || cs.textOverflow === 'ellipsis' || el.tagName === 'INPUT';
    if (el.scrollWidth > el.clientWidth + 2 && (singleLine || cs.overflow === 'hidden' || cs.overflowX === 'hidden')) {
      res.clipped.push({sel: el.className || el.tagName, text: (el.value || el.textContent || '').trim().slice(0, 60),
                        scroll: el.scrollWidth, client: el.clientWidth});
    }
  });
  document.querySelectorAll(%ESC%).forEach(el => {
    if (!vis(el)) return;
    if (el.scrollWidth > el.clientWidth + 2) res.clipped.push({sel: 'escape:' + (el.className || el.tagName), text: (el.textContent || '').trim().slice(0, 60),
                                                              scroll: el.scrollWidth, client: el.clientWidth});
  });
  document.querySelectorAll('button, a.cta, a.btn-quiet, input:not([type=hidden]), select, summary').forEach(el => {
    if (!vis(el)) return; const r = el.getBoundingClientRect();
    if (r.height < 40 || r.width < 40) res.small.push({tag: el.tagName, text: (el.textContent || el.value || el.id || '').trim().slice(0, 40),
                                                        w: Math.round(r.width), h: Math.round(r.height)});
  });
  return res;
}
""".replace("%SEL%", json.dumps(CLIP_SELECTORS)).replace("%ESC%", json.dumps(ESCAPE_SELECTORS))

AXE_RUN = ("async () => { const r = await axe.run(document, {runOnly:{type:'tag', values:['wcag2a','wcag2aa','wcag21aa']}});"
           " return r.violations.map(v => ({id: v.id, impact: v.impact, help: v.help, count: v.nodes.length,"
           " nodes: v.nodes.slice(0,3).map(n => ({target: n.target.join(' '), summary: (n.failureSummary||'').slice(0,160)}))})); }")


def find_axe() -> str | None:
    for cand in (os.environ.get("IPARTY_AXE"), ROOT / "node_modules/axe-core/axe.min.js",
                 Path.cwd() / "node_modules/axe-core/axe.min.js"):
        if cand and Path(cand).is_file():
            return Path(cand).read_text(encoding="utf-8")
    return None


def form_values(p: dict) -> dict:
    try:
        r = build_request(p)
        return {"honoree_name": r.honoree_name, "honoree_age": r.honoree_age, "party_date": r.party_date.isoformat(),
                "guest_count": r.guest_count, "budget": r.budget, "theme": r.theme,
                "dietary_restrictions": r.dietary_restrictions, "location_type": r.location_type}
    except Exception:  # noqa: BLE001 — profiles whose values must be rejected by the form
        return {"honoree_name": p["name"], "honoree_age": 30, "party_date": FUTURE, "guest_count": p["guests"],
                "budget": p["budget"], "theme": p["theme"], "dietary_restrictions": "", "location_type": "home"}


def guest_dietary(pid: str) -> tuple[str, int, int]:
    """(dietary, party_size, repeats) chosen to reach every host-panel state across the matrix."""
    last = pid[-1]
    if last == "7":
        return ("peanut allergy", 1, 1)
    if last == "3":
        return ("halal", 1, 1)
    if last == "5":
        return ("", 8, 3)  # overflow -> attention on most plans
    return ("", 2, 1)


class Matrix:
    def __init__(self, base: str, out: Path, axe_src: str | None, concurrency: int = 4, shots: bool = True):
        self.base = base.rstrip("/")
        self.out = out
        self.shots = out / "shots"
        self.shots.mkdir(parents=True, exist_ok=True)
        self.axe_src = axe_src
        self.sem = asyncio.Semaphore(concurrency)
        self.take_shots = shots
        self._ctx_n = 0

    # each context is a distinct client to the rate limiter (Render sets X-Forwarded-For)
    def _headers(self) -> dict:
        self._ctx_n += 1
        return {"X-Forwarded-For": f"10.77.{self._ctx_n >> 8 & 255}.{self._ctx_n & 255}"}

    async def context(self, browser, viewport):
        return await browser.new_context(viewport=viewport, device_scale_factor=1, extra_http_headers=self._headers())

    async def checks(self, page):
        return await page.evaluate(JS_CHECKS)

    async def axe(self, page):
        if not self.axe_src:
            return "skipped"
        try:
            # let entrance animations finish (axe mid-fade reads blended colours); skip spinners and cap the wait
            await page.evaluate("() => Promise.race([new Promise(r => setTimeout(r, 3000)), Promise.all(document.getAnimations()"
                                ".filter(a => a.effect && a.effect.getTiming().iterations !== Infinity).map(a => a.finished.catch(() => null)))])")
            await page.add_script_tag(content=self.axe_src)
            return await page.evaluate(AXE_RUN)
        except Exception as e:  # noqa: BLE001
            return [{"id": "axe-failed", "impact": "n/a", "help": str(e)[:120], "nodes": [], "count": 0}]

    async def shot(self, target, name: str, **kw):
        if not self.take_shots:
            return
        path = self.shots / name
        if not path.exists():
            with contextlib.suppress(Exception):
                await target.screenshot(path=str(path), **kw)

    @staticmethod
    def attach(page, sink: list):
        page.on("pageerror", lambda e: sink.append(f"pageerror: {e}"))
        page.on("console", lambda m: sink.append(f"console: {m.text}")
                if m.type == "error" and not any(s in m.text for s in (
                    "fonts.g", "ERR_TUNNEL", "net::ERR", "Failed to load resource: the server responded")) else None)

    async def host_journey(self, browser, p: dict, viewport: dict, label: str) -> dict:
        async with self.sem:
            rec = {"id": p["id"], "cat": p["cat"], "expect": p["expect"], "viewport": label, "errors": [], "states": {}}
            ctx = await self.context(browser, viewport)
            page = await ctx.new_page()
            self.attach(page, rec["errors"])
            try:
                t0 = time.time()
                await page.goto(self.base + "/", wait_until="networkidle")
                rec["load_s"] = round(time.time() - t0, 2)
                rec["default_date"] = await page.input_value("#party_date")
                v = form_values(p)
                rec["form"] = v
                for fid in ("honoree_name", "honoree_age", "party_date", "guest_count", "budget", "theme", "dietary_restrictions"):
                    await page.fill(f"#{fid}", str(v[fid]))
                await page.select_option("#location_type", v["location_type"])
                valid = await page.evaluate("document.getElementById('party-form').checkValidity()")
                if not valid:
                    rec["outcome"] = "blocked_native"
                    rec["validation"] = await page.evaluate(
                        "[...document.querySelectorAll('#party-form input,#party-form select')]"
                        ".filter(e=>!e.checkValidity()).map(e=>({id:e.id,value:e.value,msg:e.validationMessage}))")
                    rec["states"]["form"] = await self.checks(page)
                    rec["axe_form"] = await self.axe(page)
                    return rec
                t1 = time.time()
                await page.click("#submit-btn")
                await page.wait_for_function(
                    "() => { const r = document.getElementById('result'); return !!(r.querySelector('#live-btn') "
                    "|| /can.t be done|interrupted|unavailable|no valid|Something/i.test(r.innerText)); }", timeout=30000)
                rec["plan_s"] = round(time.time() - t1, 2)
                if await page.query_selector("#live-btn"):
                    rec["outcome"] = "verified"
                    rec["pass_total"] = await page.inner_text(".total .sum")
                    rec["schedule_times"] = await page.evaluate("[...document.querySelectorAll('.slot .t')].map(e=>e.textContent)")
                else:
                    rec["outcome"] = "infeasible"
                    rec["infeasible_text"] = (await page.inner_text("#result"))[:400]
                    rec["infeasible_buttons"] = await page.evaluate("[...document.querySelectorAll('#result button')].map(b=>b.textContent.trim())")
                rec["states"]["result"] = await self.checks(page)
                rec["axe_result"] = await self.axe(page)

                if rec["outcome"] == "infeasible":
                    await self.shot(page, f"infeasible_{label}.png")
                    if await page.query_selector("#retry-min"):
                        await page.click("#retry-min")
                        try:
                            await page.wait_for_selector("#live-btn", timeout=30000)
                            rec["retry_outcome"] = "verified"
                            rec["retry_total"] = await page.inner_text(".total .sum")
                        except Exception as e:  # noqa: BLE001
                            rec["retry_outcome"] = f"failed: {str(e)[:80]}"
                    else:
                        rec["retry_outcome"] = "no_button"
                    return rec

                # ---- Living Pass ----
                await page.click("#live-btn")
                await page.wait_for_selector(".lv-pill", timeout=20000)
                await page.wait_for_timeout(300)
                rec["living_headline_0"] = await page.inner_text(".lv-pill")
                invite = await page.input_value("#lv-invite")
                rec["states"]["living0"] = await self.checks(page)

                # ---- guest on a phone ----
                gctx = await self.context(browser, MOBILE)
                gpage = await gctx.new_page()
                gerr: list = []
                self.attach(gpage, gerr)
                dietary, size, repeats = guest_dietary(p["id"])
                for i in range(repeats):
                    await gpage.goto(invite, wait_until="networkidle")
                    await gpage.wait_for_selector("#g-name", timeout=10000)
                    await gpage.evaluate("localStorage.clear()")
                    if i == 0:
                        rec["states"]["guest_invite"] = await self.checks(gpage)
                        rec["guest_when"] = await gpage.inner_text(".fact .v")
                    await gpage.fill("#g-name", f"{v['honoree_name'].split()[0]} family {i + 1}")
                    await gpage.select_option("#g-size", str(size))
                    if dietary:
                        await gpage.fill("#g-diet", dietary)
                    await gpage.click("#g-submit")
                    await gpage.wait_for_selector(".done", timeout=10000)
                rec["guest_done"] = (await gpage.inner_text(".done"))[:220]
                rec["states"]["guest_done"] = await self.checks(gpage)
                # "Change my RSVP" must come back prefilled on the same device
                await gpage.click(".again")
                await gpage.wait_for_selector("#g-name", timeout=10000)
                rec["guest_prefill"] = {"name": await gpage.input_value("#g-name"), "size": await gpage.input_value("#g-size"),
                                        "diet": await gpage.input_value("#g-diet"),
                                        "cta": (await gpage.inner_text("#g-submit")).strip()}
                if p["id"] in MOBILE_SET:
                    rec["axe_guest"] = await self.axe(gpage)
                    await self.shot(gpage, "guest_invite.png", full_page=True)
                rec["guest_errors"] = gerr
                await gctx.close()

                # ---- host sees it (wait until every RSVP sent above has landed) ----
                for _ in range(40):
                    await page.wait_for_timeout(500)
                    counts = await page.inner_text(".lv-counts") if await page.query_selector(".lv-counts") else ""
                    if f"{repeats} going" in counts:
                        break
                rec["living_headline_1"] = await page.inner_text(".lv-pill")
                rec["living_counts"] = await page.inner_text(".lv-counts")
                rec["living_fix"] = [t[:120].replace("\n", " | ") for t in await page.locator(".lv-fix").all_inner_texts()]
                rec["living_codes"] = await page.evaluate("[...document.querySelectorAll('[data-code]')].map(e=>e.dataset.code)")
                rec["living_visible_codes"] = await page.evaluate(
                    "(document.getElementById('lv-status').innerText.match(/\\b[A-Z]{4,}(_[A-Z]+)+\\b/g)||[])")
                rec["living_guests"] = await page.evaluate("[...document.querySelectorAll('.lv-guests li')].map(e=>e.textContent.trim())")
                rec["living_right_size"] = await page.evaluate("!!document.querySelector('.lv-resize')")
                rec["states"]["living1"] = await self.checks(page)
                if p["id"] in MOBILE_SET or p["id"][-1] in "357":
                    rec["axe_living"] = await self.axe(page)
                h = rec["living_headline_1"]
                state = "attention" if "attention" in h else ("unverifiable" if "verified yet" in h else "verified")
                rec["living_state"] = state
                await self.shot(page.locator("#living"), f"living_{state}_{label}.png")

                # ---- the host acts on it: accept the fix / re-plan at the minimum ----
                btn = await page.query_selector('[data-apply="fix"], [data-apply="budget"]')
                if btn:
                    rec["apply_action"] = await btn.get_attribute("data-apply")
                    total_before = await page.inner_text(".total .sum")
                    await btn.click()
                    try:
                        await page.wait_for_function(
                            "() => /Still verified/.test(document.querySelector('.lv-pill')?.textContent || '')", timeout=15000)
                        rec["apply_outcome"] = "verified"
                        rec["apply_notice"] = (await page.inner_text("#lv-notice")) if await page.query_selector("#lv-notice") else ""
                        rec["apply_pass_total"] = {"before": total_before, "after": await page.inner_text(".total .sum")}
                        rec["states"]["living2"] = await self.checks(page)
                        if p["id"][-1] in "57":
                            rec["axe_applied"] = await self.axe(page)
                        await self.shot(page.locator("#living"), f"living_applied_{label}.png")
                    except Exception as e:  # noqa: BLE001
                        rec["apply_outcome"] = f"failed: {str(e)[:80]}"
                        rec["apply_pill"] = await page.inner_text(".lv-pill")
                elif state == "attention":
                    rec["apply_outcome"] = "no_button"

                # ---- email profiles: booking modal with the bad email ----
                if "email" in p:
                    await page.click("#book-btn")
                    await page.wait_for_selector("#book-form", timeout=8000)
                    await page.fill("#bk-name", v["honoree_name"])
                    await page.fill("#bk-email", p["email"])
                    await page.click("#bk-submit")
                    await page.wait_for_timeout(1200)
                    rec["booking_error"] = (await page.inner_text("#bk-err")).strip()[:200]
                    rec["booking_email_native_valid"] = await page.evaluate("document.getElementById('bk-email').checkValidity()")
                return rec
            except Exception as e:  # noqa: BLE001
                rec["outcome"] = rec.get("outcome", "exception")
                rec["exception"] = str(e)[:300]
                await self.shot(page, f"exc_{p['id']}_{label}.png")
                return rec
            finally:
                await ctx.close()

    async def synthetic(self, browser) -> list[dict]:
        """Hard-case UI states not reachable through profile values."""
        out = []
        async with self.sem:
            ctx = await self.context(browser, DESKTOP)
            page = await ctx.new_page()
            errs: list = []
            self.attach(page, errs)
            await page.goto(self.base + "/", wait_until="networkidle")
            for fid, val in (("honoree_name", "Layla"), ("honoree_age", "9"), ("party_date", FUTURE), ("guest_count", "20"),
                             ("budget", "5000"), ("theme", "Garden"), ("dietary_restrictions", "strictly halal")):
                await page.fill(f"#{fid}", val)
            await page.click("#submit-btn")
            await page.wait_for_function("() => /can.t be done|verify/i.test(document.getElementById('result').innerText)", timeout=30000)
            out.append({"case": "plan_unverifiable_dietary", "text": (await page.inner_text("#result"))[:500],
                        "buttons": await page.evaluate("[...document.querySelectorAll('#result button')].map(b=>b.textContent.trim())"),
                        "errors": errs, "checks": await self.checks(page), "axe": await self.axe(page)})
            await self.shot(page, "plan_unverifiable.png")
            g = await ctx.new_page()
            gerr: list = []
            self.attach(g, gerr)
            await g.goto(self.base + "/rsvp?p=not-a-real-plan-id-xyz", wait_until="networkidle")
            await g.wait_for_timeout(600)
            out.append({"case": "rsvp_invalid_link", "text": (await g.inner_text("#root"))[:200], "errors": gerr})
            await g.goto(self.base + "/rsvp", wait_until="networkidle")
            await g.wait_for_timeout(400)
            out.append({"case": "rsvp_missing_param", "text": (await g.inner_text("#root"))[:200]})
            h = await ctx.new_page()
            herr: list = []
            self.attach(h, herr)
            await h.goto(self.base + "/?living=AAAAAAAAAAAAAAAA&host=BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB", wait_until="networkidle")
            await h.wait_for_timeout(1500)
            out.append({"case": "host_link_tampered", "text": (await h.inner_text("#result"))[:300], "errors": herr})
            await ctx.close()
        return out

    async def run(self, profiles: list[dict], mobile: str = "set") -> dict:
        from playwright.async_api import async_playwright

        async with async_playwright() as pw:
            browser = await pw.chromium.launch()
            tasks = [self.host_journey(browser, p, DESKTOP, "desktop") for p in profiles]
            if mobile != "none":
                tasks += [self.host_journey(browser, p, MOBILE, "mobile") for p in profiles
                          if mobile == "all" or p["id"] in MOBILE_SET]
            t0 = time.time()
            records = await asyncio.gather(*tasks)
            synth = await self.synthetic(browser)
            await browser.close()
        results = {"records": records, "synthetic": synth, "elapsed_s": round(time.time() - t0, 1),
                   "axe": "on" if self.axe_src else "skipped"}
        results["summary"] = summarize(results)
        self.out.mkdir(parents=True, exist_ok=True)
        (self.out / "results.json").write_text(json.dumps(results, indent=1, default=str), encoding="utf-8")
        return results


# ---------------------------------------------------------------- gates
def _axe_serious(v) -> list:
    return [x for x in v if isinstance(x, dict) and x.get("impact") in ("serious", "critical")] if isinstance(v, list) else []


def summarize(results: dict) -> dict:
    recs = results["records"]
    s: dict = {"runs": len(recs), "outcomes": Counter(), "mismatches": [], "exceptions": [], "page_errors": [],
               "overflow": [], "clipped": [], "small_targets": [], "axe_serious": [], "visible_codes": [],
               "living_states": Counter(), "retry": Counter(), "guest_when_24h": [], "guest_prefill_missing": [],
               "guests_hidden": [], "booking_generic": [], "default_date_not_saturday": [], "apply": Counter(),
               "apply_failed": []}
    for r in recs:
        key = f"{r['id']}/{r['viewport']}"
        s["outcomes"][r.get("outcome", "none")] += 1
        if r.get("exception"):
            s["exceptions"].append((key, r["exception"][:100]))
        if EXPECTED.get(r["expect"]) != r.get("outcome"):
            s["mismatches"].append((key, r["expect"], r.get("outcome")))
        if r.get("errors") or r.get("guest_errors"):
            s["page_errors"].append((key, (r.get("errors") or r.get("guest_errors"))[:2]))
        for st, ch in r.get("states", {}).items():
            if ch.get("overflow", 0) > 0:
                s["overflow"].append((key, st, ch["overflow"]))
            for c in ch.get("clipped", []):
                s["clipped"].append((key, st, c["sel"], c["text"][:30]))
            for c in ch.get("small", []):
                s["small_targets"].append((key, st, c["tag"], c["text"][:30], c["w"], c["h"]))
        for k in ("axe_form", "axe_result", "axe_guest", "axe_living", "axe_applied"):
            for v in _axe_serious(r.get(k)):
                s["axe_serious"].append((key, k, v["id"], v["count"]))
        if r.get("living_visible_codes"):
            s["visible_codes"].append((key, r["living_visible_codes"]))
        if r.get("living_state"):
            s["living_states"][r["living_state"]] += 1
            if not r.get("living_guests"):
                s["guests_hidden"].append(key)
        if "apply_outcome" in r:
            ok = r["apply_outcome"] == "verified"
            s["apply"]["verified" if ok else ("no_button" if r["apply_outcome"] == "no_button" else "failed")] += 1
            if not ok:
                s["apply_failed"].append((key, r.get("apply_action"), r["apply_outcome"], r.get("apply_pill")))
        if "retry_outcome" in r:
            s["retry"][r["retry_outcome"] if r["retry_outcome"] in ("verified", "no_button") else "failed"] += 1
        if r.get("guest_when") and not any(m in r["guest_when"] for m in ("AM", "PM")):
            s["guest_when_24h"].append((key, r["guest_when"]))
        if r.get("guest_prefill") is not None and not r["guest_prefill"]["name"]:
            s["guest_prefill_missing"].append(key)
        if "booking_error" in r and r.get("booking_email_native_valid", True) and (
                "Something" in r["booking_error"] or not r["booking_error"]):
            s["booking_generic"].append((key, r["booking_error"]))
        dd = r.get("default_date")
        if dd and date.fromisoformat(dd).weekday() != 5:
            s["default_date_not_saturday"].append((key, dd))
    for x in results.get("synthetic", []):
        for v in _axe_serious(x.get("axe")):
            s["axe_serious"].append((x["case"], "axe", v["id"], v["count"]))
        if x.get("errors"):
            s["page_errors"].append((x["case"], x["errors"][:2]))
    s["gates"] = {
        "no_exceptions": not s["exceptions"], "outcomes_match_profile_expectations": not s["mismatches"],
        "no_page_errors": not s["page_errors"], "no_horizontal_overflow": not s["overflow"],
        "no_clipped_text": not s["clipped"], "no_small_tap_targets": not s["small_targets"],
        "no_serious_axe": not s["axe_serious"], "no_machine_codes_in_copy": not s["visible_codes"],
        "infeasible_retry_lands_on_a_pass": s["retry"].get("failed", 0) == 0 and s["retry"].get("no_button", 0) == 0,
        "guest_times_12h": not s["guest_when_24h"], "guest_prefill_works": not s["guest_prefill_missing"],
        "host_sees_names": not s["guests_hidden"], "booking_errors_specific": not s["booking_generic"],
        "default_date_is_saturday": not s["default_date_not_saturday"],
        "every_living_state_reached": {"verified", "attention", "unverifiable"} <= set(s["living_states"]),
        "accepting_a_fix_lands_verified": not s["apply_failed"] and s["apply"].get("verified", 0) > 0,
    }
    s["outcomes"] = dict(s["outcomes"])
    s["living_states"] = dict(s["living_states"])
    s["retry"] = dict(s["retry"])
    s["apply"] = dict(s["apply"])
    s["passed"] = all(s["gates"].values())
    return s


def print_summary(s: dict) -> None:
    print(f"runs {s['runs']} · outcomes {s['outcomes']} · living states {s['living_states']} · retry {s['retry']} · apply {s['apply']}")
    for gate, ok in s["gates"].items():
        print(f"  {'PASS' if ok else 'FAIL'}  {gate}")
    for k in ("exceptions", "mismatches", "page_errors", "overflow", "clipped", "small_targets", "axe_serious",
              "visible_codes", "guest_when_24h", "guest_prefill_missing", "guests_hidden", "booking_generic",
              "default_date_not_saturday", "apply_failed"):
        if s[k]:
            print(f"  {k} ({len(s[k])}): {s[k][:6]}")


def select(ids: str | None, cats: str | None) -> list[dict]:
    ps = PROFILES_MECE
    if ids:
        want = {x.strip().zfill(3) for x in ids.split(",")}
        ps = [p for p in ps if p["id"] in want]
    if cats:
        want = {x.strip() for x in cats.split(",")}
        ps = [p for p in ps if p["cat"] in want]
    return ps


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default=os.environ.get("IPARTY_BASE", "http://127.0.0.1:8000"))
    ap.add_argument("--out", default=".ui-out")
    ap.add_argument("--ids", help="comma-separated profile ids (default: all 100)")
    ap.add_argument("--cats", help="comma-separated partitions: diy,luxury,milestone,micro,tech,cultural,fuzz")
    ap.add_argument("--mobile", choices=("set", "all", "none"), default="set")
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--no-axe", action="store_true")
    ap.add_argument("--no-shots", action="store_true")
    ap.add_argument("--strict", action="store_true", help="exit 1 when any gate fails")
    a = ap.parse_args(argv)
    m = Matrix(a.base, Path(a.out), None if a.no_axe else find_axe(), a.concurrency, shots=not a.no_shots)
    results = asyncio.run(m.run(select(a.ids, a.cats), a.mobile))
    print_summary(results["summary"])
    print(f"axe: {results['axe']} · elapsed {results['elapsed_s']}s · {Path(a.out) / 'results.json'}")
    return 0 if (results["summary"]["passed"] or not a.strict) else 1


if __name__ == "__main__":
    sys.exit(main())
