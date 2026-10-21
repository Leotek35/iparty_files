"""Render s0_model.py into the Sprint 0 kanban page (db-backed), the sprint markdown and the db seed."""
import html
import json
import sys
from pathlib import Path
from pathlib import Path as _P

sys.path.insert(0, str(_P(__file__).resolve().parents[1]))
sys.path.insert(0, str(_P(__file__).resolve().parents[1] / "sprints"))
import architecture_model as A  # docs/architecture_model.py
import s0_model as M  # docs/sprints/s0_model.py
import s1_model as S1  # docs/sprints/s1_model.py

HERE = Path(__file__).resolve().parents[1]  # docs/
OUT_HTML = HERE / "tools" / "out" / "s0-kanban.html"
OUT_MD = HERE / "sprints" / "S0.md"
OUT_MD1 = HERE / "sprints" / "S1.md"
OUT_ROAD = HERE / "sprints" / "ROAD_TO_YC.md"
OUT_SEED = HERE / "tools" / "out" / "s0_seed.json"
OUT_SEED1 = HERE / "tools" / "out" / "s1_seed.json"
OUT_HTML.parent.mkdir(parents=True, exist_ok=True)
for _c in M.CARDS:
    _c.setdefault("sprint", "S0")
ALL_CARDS = M.CARDS + S1.CARDS
ALL_DAYS = M.DAYS + S1.DAYS
ALL_QA = [dict(q, sprint="S0") for q in M.QA_GATE] + [dict(q, sprint="S1") for q in S1.QA_GATE]

def esc(s):
    return html.escape(str(s), quote=True)

RESEARCH = [
    ("Engine and data (digest, checked 21 Oct 2026)", [
        ("Graded reward", "Planner-R1's dense shaped reward (λ all 1, schema-gated) made an 8B model beat GPT-5 on TravelPlanner; sparse pass/fail collapsed it. Adopt partial credit per rule with tolerances, safety weight 1.0, budget/servings 0.7, completeness 0.3; add TourPlanner's sigmoid gate (τ 0.75, k 28) for soft rewards in S1.", "https://arxiv.org/abs/2509.25779"),
        ("Candidate log", "TRL 1.16.0 (15 Oct 2026) GRPO wants prompt-only rows, SFT wants prompt-completion; log one row per candidate with catalog_sha256, verifier_version, model_id, usage; the Claude API has no seed, so replay only the verifier.", "https://huggingface.co/docs/trl/main/en/dataset_formats"),
        ("DPP pick of three", "Chen, Zhang & Zhou's fast greedy MAP (NeurIPS 2018): L = diag(q)·S·diag(q), q = exp(α·R), cosine S over normalized descriptor blocks; YouTube kept the kernel PSD after a 'catastrophic cliff'. θ = 0.6 to start.", "https://arxiv.org/abs/1709.05135"),
        ("CP-SAT spike", "OR-Tools 9.15 (Jan 2026): Booleans per slot candidate, AddExactlyOne, integer cents, hints from the composer, assumptions + SufficientAssumptionsForInfeasibility for explanations; ~600 Booleans solve in tens of milliseconds.", "https://developers.google.com/optimization/reference/python/sat/python/cp_model"),
        ("Verbalized Sampling", "Five responses with verbalized probabilities, tails below 0.10; 1.6–2.1× diversity, no accuracy loss; probabilities are a tail filter, not weights. Wrap PlanDraft in {candidates:[{probability, plan}]}.", "https://arxiv.org/abs/2510.01171"),
        ("Backprompting", "Send every violation at once as a structured list from the sound verifier (4.6× lift in the LLM-Modulo travel study); self-critique collapses; cap at 3 rounds and keep the best-R draft.", "https://arxiv.org/abs/2405.20625"),
        ("Prompt caching and tiers", "Haiku 5.5 $0.10/$0.50 per MTok with 0.05× cache reads; 512-token minimum cacheable prefix on 5.5 models (4,096 on Haiku 4.5); 20k calls ≈ $9. Sonnet 5.5 $2/$10 for hard briefs only.", "https://platform.claude.com/docs/en/build-with-claude/prompt-caching"),
        ("Judge rubric", "G-Eval form-filling with rationale before verdict; swap order for pairwise; 10 self-contained items weighted 1.0/0.7/0.3; calibrate on 150–200 human labels (Spearman ≥ 0.5 with CI lower bound > 0.3).", "https://arxiv.org/abs/2303.16634"),
        ("Benchmark statistics", "Mirror TravelPlanner's delivery, micro/macro and final pass; Miller's paired and clustered SEs; ~315–785 paired cases to detect a 5-point gap — a 50-case bench only sees 15–20-point gaps.", "https://arxiv.org/abs/2411.00640"),
        ("Playwright + axe", "Playwright 1.62, axe-core 4.13; block on serious/critical; radiogroup keyboard pattern for the picker; assert the concept_picked payload.", "https://playwright.dev/docs/accessibility-testing"),
        ("GRPO feasibility", "Qwen3-8B LoRA, G=8, vLLM colocate on one H100 ≈ 1 min/step; RunPod community H100 ≈ $2.69/h; $150 ≈ 5–10 pilot runs.", "https://www.runpod.io/pricing"),
    ]),
    ("Marketplace ops and compliance (research, not legal advice; checked 21 Oct 2026)", [
        ("YC Winter 2027", "On-time deadline Sun 2 Nov, 8 pm PT; decision by 11 Dec; late applications considered without timing; founder video = 1 minute of founders only, demo in the product link.", "https://www.ycombinator.com/apply"),
        ("Insurance", "Venues ask $1M/$2M GL + additional insured; Thimble ≈ $42–49/month, Next $25–45/month, but platform GL often excludes contractors' work: add contingent liability + occupational accident via a broker; ask about abuse & molestation and host liquor.", "https://thecoylegroup.com/insurance-by-industry/technology-business-insurance/gig-economy-platform-insurance/"),
        ("Stripe", "Be the disclosed seller; Connect separate charges and transfers to pay vendors and dashers (platform is business of record); Managed Payments is digital-only and excludes marketplaces; 1099-NEC threshold $2,000 for 2026, platform files for Express accounts.", "https://docs.stripe.com/connect/separate-charges-and-transfers"),
        ("Gig onboarding", "Instacart: 18+, ID + SSN, background check 5–10 business days; Taskrabbit event setup $20–35/h; Checkr Essential $54.99 with 1–2 day turnaround; FCRA applies once you screen.", "https://www.techradar.com/pro/checkr-review"),
        ("Vendors and Places terms", "Collect permit, COI, price list, minimums, lead times, windows, big-9 declarations; Google Places: no caching beyond exceptions, place_id indefinitely, lat/lng ≤ 30 days — drop the 24 h details cache.", "https://developers.google.com/maps/documentation/places/web-service/policies"),
        ("Food and allergens", "Source from permitted facilities (cottage food is direct-sale only in most states, e.g. California Class A ≤ $75k); FDA Food Code 2022 §3-602.12(C) written big-9 notification for unpackaged food where adopted; pass vendor declarations through verbatim.", "https://california.public.law/codes/health_and_safety_code_section_113758"),
        ("Take rates", "Instacart transaction revenue 7.2% of GTV (Q2 2026, ~10% with ads); DoorDash net revenue margin 13.5%, contribution 5% of GOV; a curated, fulfilled bundle supports a 20–30% blended take with ≥ 10% contribution after dasher pay, Stripe (~3%), insurance and refunds.", "https://www.prnewswire.com/news-releases/instacart-announces-second-quarter-2026-financial-results-302845378.html"),
    ]),
]

LAWYER = ["Independent-contractor classification of party dashers (ABC-test states) and the IC agreement",
          "Whether iParty needs its own retail food permit as seller of record of food it does not prepare",
          "Allergen disclosure wording and liability allocation with vendors",
          "FCRA-compliant screening flow, re-check cadence, disqualifying-offence matrix for kids-present work",
          "Terms of service: refunds, the Guarantee cap, arbitration, venue damage allocation",
          "Sales-tax treatment of a mixed bundle with Stripe Tax; 1099-NEC filings at the $2,000 threshold",
          "Google Maps Platform terms if any Places details cache beyond place_id and lat/lng is kept",
          "Insurance programme review: contractor exclusions, additional-insured endorsements, abuse & molestation, host liquor"]

CARD_NODES = {}
for n in A.NODES:
    for c in n.get("cards", []):
        CARD_NODES.setdefault(c, []).append(n["id"])
MODEL_JSON = json.dumps(dict(sprint=S1.SPRINT, sprints=[M.SPRINT["id"], S1.SPRINT["id"]], deadline=S1.DEADLINE, lanes=M.LANES, days=ALL_DAYS, cards=ALL_CARDS, qa=ALL_QA, yc=S1.YC_CHECKLIST, cardNodes=CARD_NODES, reference=A.REFERENCE_URL, today=M.SPRINT["today"]), ensure_ascii=False)

def card_html(c):
    lane_name, owner_desc, dom = M.LANES[c["lane"]]
    return (f'<article class="card {dom} prio-{c["prio"]}" draggable="true" data-id="{c["id"]}" data-status="{c["status"]}" tabindex="0" role="button" aria-label="{esc(c["id"])} {esc(c["title"])}">'
            f'<header><span class="cid">{c["id"]} · {c.get("sprint", "S0")}</span><span class="prio">{c["prio"]}</span></header>'
            f'<h4>{esc(c["title"])}</h4>'
            f'<p class="meta"><span>{esc(c["owner"])}</span><span>{c["est"]} h</span><span>{esc(c["day"])}</span></p>'
            f'<p class="deps">{("after " + ", ".join(c["deps"])) if c["deps"] else "no dependencies"}</p>'
            f'<p class="blocked" hidden></p></article>')

def columns_html():
    out = []
    for cid, cname in M.SPRINT["columns"]:
        cards = [c for c in ALL_CARDS if c["status"] == cid]
        wip = S1.SPRINT["wip"].get(cid)
        out.append(f'<section class="col" data-col="{cid}"><header><h3>{esc(cname)}</h3><span class="count" data-count="{cid}">{len(cards)}</span>{(f"<span class=wip>WIP {wip}</span>") if wip else ""}</header>'
                   f'<div class="cards" data-col="{cid}">' + "".join(card_html(c) for c in cards) + '</div></section>')
    return "".join(out)

def tests_html():
    rows = []
    for c in ALL_CARDS:
        rows.append(f'<tr id="tests-{c["id"]}"><td><a href="#{c["id"]}">{c["id"]}</a><br><strong>{esc(c["title"])}</strong><br><span class="dim">{esc(c["owner"])} · {esc(c["day"])}</span></td>'
                    f'<td><ol>' + "".join(f'<li>{esc(t)}</li>' for t in c["tests"]) + '</ol></td>'
                    '<td><ul>' + "".join(f'<li>{esc(q)}</li>' for q in c["qa"]) + '</ul></td>'
                    '<td><ul>' + "".join(f'<li>{esc(d)}</li>' for d in c["dod"]) + '</ul></td></tr>')
    return '<div class="table-wrap"><table class="tests"><thead><tr><th>Card</th><th>Acceptance tests (written before the code)</th><th>QA (what the reviewer verifies)</th><th>Definition of done</th></tr></thead><tbody>' + "".join(rows) + '</tbody></table></div>'

def qa_html():
    out = []
    for sid, name, items in (("S0", "Sprint 0 exit gate · Sun 25 Oct", M.QA_GATE), ("S1", "Sprint 1 exit gate · Sun 1 Nov", S1.QA_GATE)):
        out.append(f'<h3>{esc(name)}</h3><ul class="qa">' + "".join(
            f'<li data-qid="{q["id"]}"><label><input type="checkbox" id="qa-{q["id"]}" data-qid="{q["id"]}"> <span class="qid">{q["id"]}</span> {esc(q["text"])} <span class="dim">— {esc(q["owner"])}</span></label></li>' for q in items) + '</ul>')
    return "".join(out)

def yc_html():
    d = S1.DEADLINE
    out = [f'<p class="gate"><strong>{esc(d["label"])}: {esc(d["when"])}.</strong> Submit {esc(d["submit"])}. Freeze: {esc(d["freeze"])}. <a href="{esc(d["source"])}" rel="noopener">ycombinator.com/apply</a></p>',
           '<h3>Evidence checklist</h3><p class="notice">What the form asks, the evidence we bring, and where it comes from. Shared ticks.</p><ul class="qa yc">' + "".join(
               f'<li data-yid="{y["id"]}"><label><input type="checkbox" id="yc-{y["id"]}" data-yid="{y["id"]}"> <span class="qid">{y["id"]}</span> <span class="body"><strong>{esc(y["ask"])}</strong><br>{esc(y["evidence"])} <span class="dim">— {esc(y["source"])} · {esc(y["owner"])}</span></span></label></li>' for y in S1.YC_CHECKLIST) + '</ul>',
           '<h3>Day by day</h3><div class="table-wrap"><table class="daily"><thead><tr><th>Day</th><th>Sprint</th><th>Critical path</th></tr></thead><tbody>' + "".join(
               f'<tr><td><strong>{esc(day)}</strong></td><td>{esc(sp)}</td><td>{esc(txt)}</td></tr>' for day, sp, txt in S1.DAILY) + '</tbody></table></div>',
           '<h3>What is cut until after 2 November</h3><ul>' + "".join(f'<li>{esc(c)}</li>' for c in S1.CUTS) + '</ul>']
    return "".join(out)

def research_html():
    out = []
    for title, items in RESEARCH:
        out.append(f'<h3>{esc(title)}</h3><dl class="research">' + "".join(f'<dt>{esc(k)}</dt><dd>{esc(v)} <a href="{esc(u)}" rel="noopener">source</a></dd>' for k, v, u in items) + '</dl>')
    out.append('<h3>Questions for counsel</h3><ol>' + "".join(f'<li>{esc(x)}</li>' for x in LAWYER) + '</ol>')
    out.append('<h3>The planning protocol (applied to S1–S8)</h3><dl class="research">' + "".join(f'<dt>{esc(k)}</dt><dd>{esc(v)}</dd>' for k, v in M.PROTOCOL) + '</dl>')
    out.append('<h3>S1 research brief (drafted now, run on Sunday)</h3><ul>' + "".join(f'<li>{esc(x)}</li>' for x in M.S1_BRIEF) + '</ul>')
    return "".join(out)

CSS = r"""
/* Layout: a sprint board — five columns that scroll sideways on narrow screens, a drawer for the selected card,
   and three reference tabs (test plan, QA gate, research) that read like the memo pages. */
:root {
  --bg: #f7f8f6; --bg-2: #eef1ec; --fg: #16211d; --fg-2: #4b5751; --line: #d3d9d3; --accent: #0e6f63; --accent-2: #b8442f; --panel: #ffffff;
  --dom-engine: #c2521f; --dom-data: #5f6b7a; --dom-surfaces: #2f7bd7; --dom-fulfil: #a3417f; --dom-users: #6b5bd2;
  --display: "Bricolage Grotesque", "Avenir Next", "Helvetica Neue", Arial, sans-serif;
  --body: "Literata", Georgia, "Times New Roman", serif;
  --mono: "IBM Plex Mono", "SFMono-Regular", Menlo, Consolas, monospace;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { --bg: #121816; --bg-2: #1b2320; --fg: #e8ece8; --fg-2: #a9b3ad; --line: #2e3934; --accent: #5fc2b3; --accent-2: #f08a74; --panel: #171e1b;
  --dom-engine: #f0996f; --dom-data: #a8b4c2; --dom-surfaces: #7fb3f0; --dom-fulfil: #e08bc6; --dom-users: #a99af5; color-scheme: dark; } }
:root[data-theme="dark"] { --bg: #121816; --bg-2: #1b2320; --fg: #e8ece8; --fg-2: #a9b3ad; --line: #2e3934; --accent: #5fc2b3; --accent-2: #f08a74; --panel: #171e1b;
  --dom-engine: #f0996f; --dom-data: #a8b4c2; --dom-surfaces: #7fb3f0; --dom-fulfil: #e08bc6; --dom-users: #a99af5; color-scheme: dark; }
* { box-sizing: border-box; }
body { background: var(--bg); color: var(--fg); font-family: var(--body); font-size: 16px; line-height: 1.55;
  padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)); padding-block: 0 64px; }
a { color: var(--accent); text-decoration-thickness: 1px; text-underline-offset: 2px; }
a:focus-visible, button:focus-visible, .card:focus-visible, .tab:focus-visible, input:focus-visible, textarea:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.wrap { max-width: 1560px; margin: 0 auto; }
header.masthead { padding-block: 32px 18px; border-bottom: 1px solid var(--line); display: flex; flex-wrap: wrap; gap: 14px 40px; justify-content: space-between; align-items: end; }
.eyebrow { font-family: var(--mono); font-size: 12px; letter-spacing: .08em; text-transform: uppercase; color: var(--fg-2); margin: 0 0 10px; }
h1 { font-family: var(--display); font-weight: 800; font-size: clamp(28px, 4vw, 42px); line-height: 1.02; letter-spacing: -.02em; margin: 0 0 10px; text-wrap: balance; }
h1 em { font-style: normal; color: var(--accent-2); }
.goal { max-width: 78ch; margin: 0; color: var(--fg-2); }
.stats { display: flex; gap: 18px; flex-wrap: wrap; font-family: var(--mono); font-size: 12px; color: var(--fg-2); }
.stats b { color: var(--fg); font-size: 20px; font-family: var(--display); display: block; }
.live { font-family: var(--mono); font-size: 12px; color: var(--fg-2); margin: 10px 0 0; }
.live b { color: var(--accent); }
.tabs { display: flex; gap: 6px; flex-wrap: wrap; margin: 18px 0 14px; }
.tab { font-family: var(--display); font-weight: 700; font-size: 14px; padding: 8px 14px; border: 1px solid var(--line); border-radius: 999px; background: var(--panel); color: var(--fg); cursor: pointer; }
.tab[aria-selected="true"] { background: var(--fg); color: var(--bg); border-color: var(--fg); }
.view { display: none; } .view.active { display: block; }
.board { display: grid; grid-auto-flow: column; grid-auto-columns: minmax(250px, 1fr); gap: 12px; overflow-x: auto; padding-bottom: 8px; }
.col { background: var(--bg-2); border: 1px solid var(--line); border-radius: 8px; min-width: 0; display: flex; flex-direction: column; min-height: 320px; }
.col header { display: flex; align-items: center; gap: 8px; padding: 10px 12px; border-bottom: 1px solid var(--line); }
.col h3 { font-family: var(--display); font-size: 14px; margin: 0; flex: 1; }
.count, .wip { font-family: var(--mono); font-size: 11px; padding: 2px 7px; border-radius: 999px; border: 1px solid var(--line); background: var(--panel); }
.col.over-wip .wip { color: var(--accent-2); border-color: var(--accent-2); }
.cards { display: flex; flex-direction: column; gap: 8px; padding: 10px; flex: 1; min-height: 120px; }
.col.drop .cards { outline: 2px dashed var(--accent); outline-offset: -6px; }
.card { background: var(--panel); border: 1px solid var(--line); border-left: 4px solid var(--dom); border-radius: 6px; padding: 8px 10px; cursor: grab; --dom: var(--fg-2); }
.card.dom-engine { --dom: var(--dom-engine); } .card.dom-data { --dom: var(--dom-data); } .card.dom-surfaces { --dom: var(--dom-surfaces); } .card.dom-fulfil { --dom: var(--dom-fulfil); } .card.dom-users { --dom: var(--dom-users); }
.card:hover { border-color: var(--dom); } .card.dragging { opacity: .5; } .card.selected { box-shadow: 0 0 0 2px var(--dom); }
.card header { display: flex; justify-content: space-between; font-family: var(--mono); font-size: 11px; color: var(--dom); letter-spacing: .04em; }
.card .prio { color: var(--fg-2); } .card.prio-P0 .prio { color: var(--accent-2); font-weight: 700; }
.card h4 { font-family: var(--display); font-size: 14.5px; margin: 4px 0 6px; line-height: 1.25; text-transform: none; letter-spacing: 0; color: var(--fg); }
.card .meta { display: flex; flex-wrap: wrap; gap: 4px 10px; font-family: var(--mono); font-size: 11px; color: var(--fg-2); margin: 0 0 4px; }
.card .deps { font-size: 12px; color: var(--fg-2); margin: 0; font-family: var(--display); }
.card .blocked { font-family: var(--mono); font-size: 11px; color: var(--accent-2); margin: 4px 0 0; }
.card.is-blocked { border-style: dashed; }
.card .wait { font-family: var(--mono); font-size: 11px; color: var(--accent-2); margin: 4px 0 0; }
.card.hide-f { display: none; } .card.adhoc { border-style: dotted; }
.progress { margin: 10px 0 6px; max-width: 900px; } .bar { height: 10px; background: var(--bg-2); border: 1px solid var(--line); border-radius: 999px; overflow: hidden; display: flex; }
.bar span { display: block; height: 100%; } #bar-done { background: var(--accent); } #bar-doing { background: color-mix(in srgb, var(--accent) 35%, transparent); }
.toolbar { display: flex; flex-wrap: wrap; gap: 8px 10px; align-items: center; margin: 10px 0 12px; font-family: var(--display); font-size: 14px; }
.toolbar .k { font-family: var(--mono); font-size: 11px; letter-spacing: .06em; text-transform: uppercase; color: var(--fg-2); margin-left: 6px; }
.toolbar label { display: inline-flex; gap: 6px; align-items: center; } .toolbar select { padding: 5px 8px; }
.fchip { display: inline-flex; align-items: center; gap: 6px; font-family: var(--display); font-size: 12.5px; padding: 4px 9px; border-radius: 999px; }
.fchip[aria-pressed="false"] { opacity: .45; text-decoration: line-through; }
.sw { width: 11px; height: 11px; border-radius: 3px; display: inline-block; background: var(--dom); --dom: var(--fg-2); }
.sw.dom-engine { --dom: var(--dom-engine); } .sw.dom-data { --dom: var(--dom-data); } .sw.dom-surfaces { --dom: var(--dom-surfaces); } .sw.dom-fulfil { --dom: var(--dom-fulfil); } .sw.dom-users { --dom: var(--dom-users); }
.board.days { grid-auto-columns: minmax(230px, 1fr); }
.drawer h4:first-child { margin-top: 0; } .activity-list { list-style: none; padding: 0; margin: 0; font-family: var(--mono); font-size: 12px; } .activity-list li { margin-bottom: 4px; color: var(--fg-2); }
.adhoc-form { display: grid; gap: 8px; grid-template-columns: 1fr 1fr; margin-top: 8px; } .adhoc-form .full { grid-column: 1 / -1; } .adhoc-form input, .adhoc-form select { width: 100%; font: inherit; font-family: var(--display); color: var(--fg); background: var(--panel); border: 1px solid var(--line); border-radius: 6px; padding: 6px 10px; }
.chip-node { border: 1px solid var(--dom-engine); text-decoration: none; display: inline-block; font-family: var(--mono); font-size: 11px; padding: 2px 7px; border-radius: 4px; margin: 2px 4px 2px 0; background: var(--bg-2); }
.brief { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; margin: 6px 0; }
.drawer { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 18px 20px 14px; margin-top: 16px; }
.drawer .ph { display: flex; flex-wrap: wrap; gap: 10px 20px; justify-content: space-between; align-items: start; border-bottom: 1px solid var(--line); padding-bottom: 12px; }
.drawer h3 { font-family: var(--display); font-size: 20px; margin: 0; }
h4 { font-family: var(--mono); font-size: 11.5px; letter-spacing: .08em; text-transform: uppercase; color: var(--fg-2); margin: 16px 0 6px; }
p { margin: 0 0 12px; } ul, ol { margin: 0 0 10px; padding-left: 1.2em; } li { margin-bottom: 5px; }
code { font-family: var(--mono); font-size: .86em; background: var(--bg-2); padding: 1px 5px; border-radius: 3px; }
.pill { display: inline-block; font-family: var(--mono); font-size: 11px; letter-spacing: .04em; padding: 3px 8px; border-radius: 999px; border: 1px solid var(--line); white-space: nowrap; margin-right: 6px; }
.moves { display: flex; flex-wrap: wrap; gap: 6px; margin: 8px 0 4px; }
button, textarea, input[type=text] { font: inherit; font-family: var(--display); color: var(--fg); background: var(--panel); border: 1px solid var(--line); border-radius: 6px; padding: 6px 10px; }
button { cursor: pointer; } button:hover { border-color: var(--accent); } button[aria-pressed="true"] { background: var(--fg); color: var(--bg); }
textarea { width: 100%; min-height: 70px; font-family: var(--body); }
.note-row { display: flex; gap: 8px; flex-wrap: wrap; align-items: start; }
.note-row textarea { flex: 1 1 320px; }
.table-wrap { overflow-x: auto; margin: 14px 0 26px; border: 1px solid var(--line); border-radius: 4px; }
table { border-collapse: collapse; width: 100%; font-size: 13.5px; line-height: 1.45; font-family: var(--display); }
th, td { text-align: left; vertical-align: top; padding: 9px 11px; border-bottom: 1px solid var(--line); min-width: 10em; }
th { font-family: var(--mono); font-size: 11px; letter-spacing: .06em; text-transform: uppercase; color: var(--fg-2); background: var(--bg-2); position: sticky; top: 0; }
tbody tr:last-child td { border-bottom: 0; } tbody tr:nth-child(even) td { background: color-mix(in srgb, var(--bg-2) 55%, transparent); }
td ol, td ul { margin: 0; padding-left: 1.1em; } .dim { color: var(--fg-2); font-size: 12px; }
table.tests td:nth-child(2) { min-width: 26em; }
.qa { list-style: none; padding: 0; max-width: 90ch; } .qa li { padding: 8px 10px; border: 1px solid var(--line); border-radius: 6px; margin-bottom: 8px; background: var(--panel); }
.qa label { display: flex; gap: 10px; align-items: start; cursor: pointer; } .qa input { margin-top: 5px; } .qid { font-family: var(--mono); font-size: 11px; color: var(--fg-2); }
.qa li.checked { opacity: .65; text-decoration: line-through; } .qa.yc li { max-width: 100ch; } .qa .body { flex: 1; min-width: 0; } .qa .qid { flex: 0 0 auto; margin-top: 4px; } table.daily td:nth-child(3) { min-width: 30em; }
dl.research { max-width: 90ch; } dl.research dt { font-family: var(--display); font-weight: 700; margin-top: 12px; } dl.research dd { margin: 2px 0 0; }
.gate { border-left: 3px solid var(--accent-2); padding: 6px 0 6px 16px; font-family: var(--display); font-size: 15px; max-width: 90ch; }
.view h2 { font-family: var(--display); font-weight: 700; font-size: 24px; margin: 8px 0 8px; }
.notice { font-family: var(--mono); font-size: 12px; color: var(--fg-2); margin: 0 0 10px; }
@media (prefers-reduced-motion: no-preference) { html { scroll-behavior: smooth; } }
"""

JS = r"""
(function(){
  const MODEL = __MODEL__;
  const cards = Object.fromEntries(MODEL.cards.map(c => [c.id, Object.assign({}, c)]));
  const COLS = MODEL.sprint.columns.map(c => c[0]);
  const COLNAME = Object.fromEntries(MODEL.sprint.columns);
  const TOTAL_EST = MODEL.cards.reduce((a, c) => a + (c.est || 0), 0);
  const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[ch]));
  let db = null, uid = null, canWrite = false, selected = null, activity = [];
  const live = document.getElementById('live'), note = document.getElementById('toolbar-note');
  const filters = { lanes: new Set(Object.keys(MODEL.lanes)), sprints: new Set(MODEL.sprints), owner: '', day: '', p0: false };
  const DEADLINE = new Date('2026-11-03T04:00:00Z'); // Mon 2 Nov 2026, 8 pm PT

  // ---------- tabs
  const tabs = [...document.querySelectorAll('.tab')];
  function showTab(name) {
    tabs.forEach(t => t.setAttribute('aria-selected', t.dataset.tab === name ? 'true' : 'false'));
    document.querySelectorAll('.view').forEach(v => v.classList.toggle('active', v.id === 'view-' + name));
    if (name === 'days') renderDays();
  }
  tabs.forEach(t => t.addEventListener('click', () => { showTab(t.dataset.tab); history.replaceState(null, '', '#' + t.dataset.tab); }));

  // ---------- helpers
  const visible = c => filters.lanes.has(c.lane) && filters.sprints.has(c.sprint || 'S0') && (!filters.owner || c.owner === filters.owner) && (!filters.day || c.day === filters.day) && (!filters.p0 || c.prio === 'P0');
  const waitingOn = c => (c.deps || []).filter(d => cards[d] && cards[d].status !== 'done');
  function cardEl(c, compact) {
    const lane = MODEL.lanes[c.lane] || ['Ad hoc', '', 'dom-users'];
    const el = document.createElement('article');
    el.className = `card ${lane[2]} prio-${c.prio}` + (c.blocked ? ' is-blocked' : '') + (selected === c.id ? ' selected' : '') + (c.adhoc ? ' adhoc' : '') + (visible(c) ? '' : ' hide-f');
    el.draggable = canWrite && !compact; el.dataset.id = c.id; el.dataset.status = c.status; el.tabIndex = 0; el.setAttribute('role', 'button');
    el.setAttribute('aria-label', `${c.id} ${c.title}`);
    const wait = waitingOn(c);
    el.innerHTML = `<header><span class="cid">${esc(c.id)}</span><span class="prio">${esc(c.prio)}${compact ? ' · ' + esc(COLNAME[c.status] || c.status) : ''}</span></header><h4>${esc(c.title)}</h4>
      <p class="meta"><span>${esc(c.owner)}</span><span>${esc(c.est)} h</span><span>${esc(c.day)}</span></p>
      <p class="deps">${c.deps && c.deps.length ? 'after ' + c.deps.map(esc).join(', ') : 'no dependencies'}</p>
      ${wait.length && c.status !== 'done' ? `<p class="wait">waiting on ${wait.map(esc).join(', ')}</p>` : ''}
      <p class="blocked"${c.blocked ? '' : ' hidden'}>blocked: ${esc(c.blocked || '')}</p>`;
    el.addEventListener('click', () => select(c.id));
    el.addEventListener('keydown', ev => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); select(c.id); } });
    el.addEventListener('dragstart', ev => { if (!canWrite) { ev.preventDefault(); return; } ev.dataTransfer.setData('text/plain', c.id); el.classList.add('dragging'); });
    el.addEventListener('dragend', () => el.classList.remove('dragging'));
    return el;
  }
  function renderBoard() {
    for (const col of COLS) {
      const host = document.querySelector(`.cards[data-col="${col}"]`); host.innerHTML = '';
      const list = Object.values(cards).filter(c => c.status === col).sort((a, b) => (a.prio + a.id).localeCompare(b.prio + b.id));
      list.forEach(c => host.appendChild(cardEl(c, false)));
      document.querySelector(`[data-count="${col}"]`).textContent = list.filter(visible).length;
      const wip = MODEL.sprint.wip[col]; const colEl = document.querySelector(`.col[data-col="${col}"]`);
      if (wip) colEl.classList.toggle('over-wip', list.length > wip);
    }
    const all = Object.values(cards);
    const done = all.filter(c => c.status === 'done'), doing = all.filter(c => c.status === 'doing' || c.status === 'review');
    document.getElementById('stat-done').textContent = done.length; document.getElementById('stat-doing').textContent = doing.length;
    const hDone = done.reduce((a, c) => a + (c.est || 0), 0), hDoing = doing.reduce((a, c) => a + (c.est || 0), 0);
    document.getElementById('bar-done').style.width = (100 * hDone / TOTAL_EST) + '%'; document.getElementById('bar-doing').style.width = (100 * hDoing / TOTAL_EST) + '%';
    document.getElementById('progress-text').textContent = `${hDone} of ${TOTAL_EST} estimated hours done · ${hDoing} in progress or review · ${all.filter(c => c.blocked).length} blocked`;
    if (document.getElementById('view-days').classList.contains('active')) renderDays();
  }
  function renderDays() {
    const host = document.getElementById('days-board'); host.innerHTML = '';
    for (const day of MODEL.days.concat(['unscheduled'])) {
      const list = Object.values(cards).filter(c => (day === 'unscheduled' ? !MODEL.days.includes(c.day) : c.day === day)).sort((a, b) => (a.prio + a.id).localeCompare(b.prio + b.id));
      if (day === 'unscheduled' && !list.length) continue;
      const sec = document.createElement('section'); sec.className = 'col';
      sec.innerHTML = `<header><h3>${esc(day)}</h3><span class="count">${list.length} · ${list.reduce((a, c) => a + (c.est || 0), 0)} h</span></header><div class="cards"></div>`;
      const cs = sec.querySelector('.cards'); list.forEach(c => cs.appendChild(cardEl(c, true))); host.appendChild(sec);
    }
  }
  document.querySelectorAll('#view-board .col').forEach(colEl => {
    colEl.addEventListener('dragover', ev => { if (!canWrite) return; ev.preventDefault(); colEl.classList.add('drop'); });
    colEl.addEventListener('dragleave', () => colEl.classList.remove('drop'));
    colEl.addEventListener('drop', ev => { ev.preventDefault(); colEl.classList.remove('drop'); const id = ev.dataTransfer.getData('text/plain'); if (id) move(id, colEl.dataset.col); });
  });

  // ---------- filters
  document.querySelectorAll('.fchip[data-lane]').forEach(b => b.addEventListener('click', () => {
    const on = b.getAttribute('aria-pressed') !== 'true'; b.setAttribute('aria-pressed', on ? 'true' : 'false');
    if (on) filters.lanes.add(b.dataset.lane); else filters.lanes.delete(b.dataset.lane); renderBoard();
  }));
  document.querySelectorAll('.fchip[data-sprint]').forEach(b => b.addEventListener('click', () => {
    const on = b.getAttribute('aria-pressed') !== 'true'; b.setAttribute('aria-pressed', on ? 'true' : 'false');
    if (on) filters.sprints.add(b.dataset.sprint); else filters.sprints.delete(b.dataset.sprint); renderBoard();
  }));
  document.getElementById('f-owner').addEventListener('change', ev => { filters.owner = ev.target.value; renderBoard(); });
  document.getElementById('f-day').addEventListener('change', ev => { filters.day = ev.target.value; renderBoard(); });
  document.getElementById('f-p0').addEventListener('change', ev => { filters.p0 = ev.target.checked; renderBoard(); });

  // ---------- clipboard helpers
  async function copyText(text, okMsg) {
    try { await navigator.clipboard.writeText(text); note.textContent = okMsg; }
    catch (e) { const ta = document.createElement('textarea'); ta.value = text; document.body.appendChild(ta); ta.select(); note.textContent = 'Clipboard blocked — text selected below, press Ctrl/Cmd+C.'; ta.style.width = '100%'; ta.style.minHeight = '120px'; note.after(ta); setTimeout(() => ta.remove(), 15000); }
    setTimeout(() => note.textContent = '', 4000);
  }
  function briefFor(c) {
    const lane = MODEL.lanes[c.lane] || ['Ad hoc', 'Leo', ''];
    return `Lane: ${c.lane} · ${lane[0]}        Sprint: ${c.sprint || 'S0'}        Card: ${c.id}        Branch: wt/${c.id.toLowerCase()}
Goal: ${c.title}
Owner: ${c.owner} · estimate ${c.est} h · planned ${c.day} · priority ${c.prio}
Context: read docs/ARCHITECTURE.md (systems: ${(MODEL.cardNodes[c.id] || []).join(', ') || 'see register'}), docs/sprints/S0.md, docs/DECISIONS.md first.
Spec: ${c.spec}
Acceptance tests (write these BEFORE the implementation; all must pass):
${(c.tests || []).map((t, i) => `  ${i + 1}. ${t}`).join('\n')}
QA (the reviewer verifies): ${(c.qa || []).join(' · ')}
Definition of done: ${(c.dod || []).join(' · ')}
Research: ${(c.refs || []).join(' · ')}
Telemetry it must emit: ${(c.telemetry || []).join(' · ')}
Dependencies: ${(c.deps || []).join(', ') || 'none'}
Constraints: make lint test catalog-check and tests/test_composer_creativity.py stay green; no new dependencies without listing them; no changes outside this card's modules; never weaken an existing test; log every candidate and verdict; commit messages end with the project's trailers.
Done means: PR open, gate green, a 5-line summary of what changed and what you could not do, and a docs/DECISIONS.md entry for any choice you made.`;
  }
  function standup() {
    const all = Object.values(cards);
    const by = col => all.filter(c => c.status === col).map(c => `- ${c.id} ${c.title} (${c.owner})${c.blocked ? ' — BLOCKED: ' + c.blocked : ''}`).join('\n') || '- none';
    const hDone = all.filter(c => c.status === 'done').reduce((a, c) => a + (c.est || 0), 0);
    return `# Road to YC — standup ${new Date().toISOString().slice(0, 10)}\n\n${hDone} of ${TOTAL_EST} estimated hours done.\n\n## Done\n${by('done')}\n\n## In review\n${by('review')}\n\n## In progress\n${by('doing')}\n\n## Ready\n${by('ready')}\n\n## Blocked\n${all.filter(c => c.blocked).map(c => `- ${c.id}: ${c.blocked}`).join('\n') || '- none'}\n`;
  }
  document.getElementById('export').addEventListener('click', () => copyText(standup(), 'Standup summary copied.'));

  // ---------- ad-hoc cards
  document.getElementById('add-card').addEventListener('click', () => {
    if (!canWrite) { note.textContent = 'Read-only in this view.'; return; }
    const d = document.getElementById('drawer'); d.hidden = false; selected = null; renderBoard();
    d.innerHTML = `<h3>Add an ad-hoc card</h3><p class="notice">For work discovered during the sprint. Planned cards stay in docs/sprints/s0_model.py; ad-hoc cards live only on this board.</p>
      <form class="adhoc-form" id="adhoc"><input class="full" id="ah-title" placeholder="Title" required maxlength="120">
      <select id="ah-lane">${Object.entries(MODEL.lanes).map(([k, v]) => `<option value="${k}">${k} · ${esc(v[0])}</option>`).join('')}</select>
      <input id="ah-owner" placeholder="Owner" value="Leo" maxlength="40"><input id="ah-est" type="number" min="0" max="40" step="0.5" value="2" aria-label="Estimate hours"><select id="ah-day">${MODEL.days.map(x => `<option>${esc(x)}</option>`).join('')}</select>
      <input class="full" id="ah-test" placeholder="One acceptance test (what proves it is done)" maxlength="200">
      <div class="full"><button type="submit">Add to Ready</button></div></form>`;
    d.querySelector('#adhoc').addEventListener('submit', async ev => {
      ev.preventDefault();
      const n = Object.values(cards).filter(c => c.adhoc).length + 1; const id = 'X0-' + String(n).padStart(2, '0');
      const c = { id, lane: d.querySelector('#ah-lane').value, title: d.querySelector('#ah-title').value.trim(), owner: d.querySelector('#ah-owner').value.trim() || 'Leo', est: +d.querySelector('#ah-est').value || 0, day: d.querySelector('#ah-day').value, prio: 'P2', status: 'ready', deps: [], spec: 'Ad-hoc card added during the sprint.', tests: [d.querySelector('#ah-test').value.trim()].filter(Boolean), qa: [], dod: ['Merged or done; decision logged'], refs: [], telemetry: [], notes: '', blocked: '', adhoc: true, createdAt: new Date().toISOString(), createdBy: uid || 'unknown' };
      try { await db.doc('cards/' + id).set(c); cards[id] = c; select(id); logMove(id, 'created'); } catch (e) { note.textContent = 'Could not save (' + (e && e.code) + ').'; }
    });
  });

  // ---------- drawer
  function list(items) { return '<ul>' + (items || []).map(i => `<li>${esc(i)}</li>`).join('') + '</ul>'; }
  function olist(items) { return '<ol>' + (items || []).map(i => `<li>${esc(i)}</li>`).join('') + '</ol>'; }
  function renderDrawer() {
    const d = document.getElementById('drawer'); const c = cards[selected]; if (!c) { d.hidden = true; return; }
    const lane = MODEL.lanes[c.lane] || ['Ad hoc', 'added on the board', ''];
    const nodesTouched = MODEL.cardNodes[c.id] || [];
    const wait = waitingOn(c);
    d.hidden = false;
    d.innerHTML = `<div class="ph"><div><p class="eyebrow">${esc(c.id)} · ${esc(lane[0])} · ${esc(lane[1])}</p><h3>${esc(c.title)}</h3></div>
      <div><span class="pill">${esc(COLNAME[c.status] || c.status)}</span><span class="pill">${esc(c.prio)}</span><span class="pill">${esc(c.owner)}</span><span class="pill">${esc(c.est)} h · ${esc(c.day)}</span></div></div>
      <h4>Move</h4><div class="moves">${COLS.map(col => `<button type="button" data-move="${col}" aria-pressed="${c.status === col}"${canWrite ? '' : ' disabled'}>${esc(COLNAME[col])}</button>`).join('')}
        <button type="button" id="block-btn"${canWrite ? '' : ' disabled'}>${c.blocked ? 'Unblock' : 'Mark blocked'}</button></div>
      ${wait.length && c.status !== 'done' ? `<p class="notice">Waiting on ${wait.map(id => `<a href="#${id}">${id}</a>`).join(', ')} — not done yet.</p>` : ''}
      ${c.blocked ? `<p class="notice">Blocked: ${esc(c.blocked)}</p>` : ''}
      <div class="brief"><button type="button" id="copy-brief">Copy agent brief</button><span class="notice">Paste at the top of the agent session; it carries the spec, the tests and the gate.</span></div>
      <h4>Spec</h4><p>${esc(c.spec)}</p>
      <h4>Systems touched</h4><p>${nodesTouched.length ? nodesTouched.map(n => `<a class="chip-node" href="${MODEL.reference}#${n}" rel="noopener">${n}</a>`).join(' ') : 'see the system reference'}</p>
      <h4>Dependencies</h4><p>${c.deps && c.deps.length ? c.deps.map(id => `<a href="#${id}">${id}</a>${cards[id] ? ` (${esc(COLNAME[cards[id].status] || cards[id].status)})` : ''}`).join(', ') : 'none'}</p>
      <h4>Acceptance tests (written before the code)</h4>${olist(c.tests)}
      <h4>QA — what the reviewer verifies</h4>${list(c.qa)}
      <h4>Definition of done</h4>${list(c.dod)}
      <h4>Research references</h4>${list(c.refs)}
      <h4>Telemetry it must emit</h4>${list(c.telemetry)}
      <h4>Notes (shared)</h4><div class="note-row"><textarea id="note" ${canWrite ? '' : 'readonly'} placeholder="Decisions, blockers, links…">${esc(c.notes || '')}</textarea><button type="button" id="save-note"${canWrite ? '' : ' disabled'}>Save note</button></div>
      <p class="notice">Deep link: <code>#${esc(c.id)}</code>${c.movedAt ? ` · last moved ${esc(c.movedAt)}` : ''}</p>`;
    d.querySelectorAll('[data-move]').forEach(b => b.addEventListener('click', () => move(c.id, b.dataset.move)));
    d.querySelector('#block-btn').addEventListener('click', async () => {
      if (c.blocked) await write(c.id, { blocked: '' });
      else { const reason = (d.querySelector('#note').value || '').trim() || 'blocked'; await write(c.id, { blocked: reason }); }
    });
    d.querySelector('#save-note').addEventListener('click', async () => { await write(c.id, { notes: d.querySelector('#note').value }); });
    d.querySelector('#copy-brief').addEventListener('click', () => copyText(briefFor(c), 'Agent brief copied.'));
  }
  function select(id) { selected = id; renderBoard(); renderDrawer(); document.getElementById('drawer').scrollIntoView({ block: 'nearest' }); }

  // ---------- writes and activity
  function renderActivity() {
    const host = document.getElementById('activity');
    host.innerHTML = '<h4>Recent moves</h4>' + (activity.length ? '<ul class="activity-list">' + activity.slice(-12).reverse().map(a => `<li>${esc(a.at)} · <a href="#${esc(a.id)}">${esc(a.id)}</a> → ${esc(COLNAME[a.to] || a.to)}</li>`).join('') + '</ul>' : '<p class="notice">No moves yet.</p>');
  }
  async function logMove(id, to) {
    const entry = { at: new Date().toISOString().slice(0, 16).replace('T', ' '), id, to, by: uid || 'unknown' };
    activity = activity.concat([entry]).slice(-200); renderActivity();
    if (!db || !canWrite) return;
    try { await db.doc('meta/activity').set({ entries: activity }); } catch (e) { /* activity is a convenience; the card itself was saved */ }
  }
  async function write(id, patch) {
    const c = cards[id]; if (!c) return;
    Object.assign(c, patch); renderBoard(); if (selected === id) renderDrawer();
    if (!db || !canWrite) return;
    try { await db.doc('cards/' + id).update(Object.assign({}, patch, { updatedAt: new Date().toISOString(), updatedBy: uid || 'unknown' })); }
    catch (e) { live.innerHTML = `<b>Save failed</b> (${esc(e && e.code)}) — the board is read-only for this visit.`; canWrite = false; renderBoard(); if (selected === id) renderDrawer(); }
  }
  async function move(id, col) {
    const c = cards[id]; if (!c || c.status === col) return;
    const wip = MODEL.sprint.wip[col];
    if (wip && Object.values(cards).filter(x => x.status === col).length >= wip) { note.textContent = `WIP limit for ${COLNAME[col]} is ${wip}: finish or park something first.`; setTimeout(() => note.textContent = '', 4000); }
    await write(id, { status: col, movedAt: new Date().toISOString().slice(0, 16).replace('T', ' ') });
    logMove(id, col);
  }

  // ---------- QA checklist
  document.querySelectorAll('.qa:not(.yc) input').forEach(inp => inp.addEventListener('change', async () => {
    const qid = inp.dataset.qid; inp.closest('li').classList.toggle('checked', inp.checked);
    if (!db || !canWrite) return;
    try { await db.doc('qa/' + qid).update({ checked: inp.checked, checkedAt: new Date().toISOString(), checkedBy: uid || 'unknown' }); }
    catch (e) { live.innerHTML = `<b>Save failed</b> (${esc(e && e.code)}).`; }
  }));
  document.querySelectorAll('.qa.yc input').forEach(inp => inp.addEventListener('change', async () => {
    const yid = inp.dataset.yid; inp.closest('li').classList.toggle('checked', inp.checked);
    if (!db || !canWrite) return;
    try { await db.doc('yc/' + yid).update({ checked: inp.checked, checkedAt: new Date().toISOString(), checkedBy: uid || 'unknown' }); }
    catch (e) { live.innerHTML = `<b>Save failed</b> (${esc(e && e.code)}).`; }
  }));
  function applyYc(id, data) { const inp = document.getElementById('yc-' + id); if (!inp) return; inp.checked = !!data.checked; inp.closest('li').classList.toggle('checked', !!data.checked); }
  function applyQa(id, data) { const inp = document.getElementById('qa-' + id); if (!inp) return; inp.checked = !!data.checked; const li = inp.closest('li'); li.classList.toggle('checked', !!data.checked);
    let when = li.querySelector('.when'); if (!when) { when = document.createElement('span'); when.className = 'dim when'; li.querySelector('label').appendChild(when); }
    when.textContent = data.checked && data.checkedAt ? ` · ticked ${String(data.checkedAt).slice(0, 16).replace('T', ' ')}` : ''; }

  // ---------- hash routing
  function fromHash() {
    const h = (location.hash || '').slice(1);
    if (['board', 'days', 'yc', 'tests', 'qa', 'research'].includes(h)) { showTab(h); return; }
    if (cards[h]) { showTab('board'); select(h); }
  }
  window.addEventListener('hashchange', fromHash);

  // ---------- boot: render from the embedded model, then light up the store
  renderBoard(); renderActivity(); fromHash();
  document.getElementById('stat-days').textContent = Math.max(0, Math.floor((DEADLINE - Date.now()) / 86400000));
  (async () => {
    db = await claude.use('db'); const user = await claude.use('user');
    if (!db) { live.innerHTML = 'Live status unavailable in this view — showing the plan as written.'; return; }
    uid = user ? await user.id() : null;
    const w = user ? await user.can('data.write') : null; canWrite = w !== false;
    live.innerHTML = canWrite ? '<b>Live</b> — moves, notes, ad-hoc cards and the QA gate are shared with everyone who opens this board.' : 'Live, read-only in this view.';
    renderBoard(); if (selected) renderDrawer();
    db.collection('cards').onSnapshot(snap => {
      if (snap.empty) { live.innerHTML = 'Board not seeded yet — showing the plan as written.'; return; }
      live.innerHTML = canWrite ? '<b>Live</b> — moves, notes, ad-hoc cards and the QA gate are shared with everyone who opens this board.' : 'Live, read-only in this view.';
      snap.docs.forEach(d => { const data = d.data(); if (cards[d.id]) Object.assign(cards[d.id], data); else cards[d.id] = Object.assign({ adhoc: true }, data); });
      snap.docChanges().forEach(ch => { if (ch.type === 'removed' && cards[ch.doc.id] && cards[ch.doc.id].adhoc) delete cards[ch.doc.id]; });
      renderBoard(); if (selected) renderDrawer();
    }, e => { live.innerHTML = `Live status unavailable (${esc(e && e.code)}) — showing the plan as written.`; });
    db.collection('qa').onSnapshot(snap => { snap.docs.forEach(d => applyQa(d.id, d.data())); }, () => {});
    db.collection('yc').onSnapshot(snap => { snap.docs.forEach(d => applyYc(d.id, d.data())); }, () => {});
    db.doc('meta/activity').onSnapshot(snap => { if (snap.exists) { activity = (snap.data().entries || []).slice(-200); renderActivity(); } }, () => {});
  })();
})();
"""

days_left = 12  # Wed 21 Oct → Mon 2 Nov (recomputed live on the page)
sprint_filters = "".join(f'<button type="button" class="fchip" data-sprint="{sid}" aria-pressed="true">{sid}</button>' for sid in ("S0", "S1"))
lane_filters = "".join(f'<button type="button" class="fchip" data-lane="{k}" aria-pressed="true"><i class="sw {v[2]}"></i>{k} · {esc(v[0])}</button>' for k, v in M.LANES.items())
owner_options = "".join(f'<option value="{esc(o)}">{esc(o)}</option>' for o in sorted(set(c["owner"] for c in ALL_CARDS)))
day_options = "".join(f'<option value="{esc(d)}">{esc(d)}</option>' for d in ALL_DAYS)
PAGE = f"""<title>Road to YC Board</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,500;12..96,700;12..96,800&family=Literata:ital,opsz,wght@0,7..72,400;0,7..72,600;1,7..72,400&family=IBM+Plex+Mono:wght@400;500;700&display=swap">
<style>{CSS}</style>
<div class="wrap">
  <header class="masthead">
    <div>
      <p class="eyebrow">iParty · Road to YC · Wed 21 Oct – Mon 2 Nov 2026 · S0 instrument and spike → S1 road to YC</p>
      <h1>Road to YC Board: <em>deadline Mon 2 Nov, 8 pm PT</em></h1>
      <p class="goal">{esc(S1.SPRINT["goal"])}</p>
      <p class="live" id="live">Connecting to the shared board…</p>
    </div>
    <div class="stats"><span><b>{len(ALL_CARDS)}</b>cards</span><span><b id="stat-doing">0</b>in progress / review</span><span><b id="stat-done">0</b>done</span><span><b id="stat-days">{days_left}</b>days to deadline</span><span><b>{sum(c["est"] for c in ALL_CARDS)}</b>estimated hours</span></div>
  </header>

  <div class="tabs" role="tablist">
    <button class="tab" role="tab" data-tab="board" aria-selected="true">Board</button>
    <button class="tab" role="tab" data-tab="days" aria-selected="false">By day</button>
    <button class="tab" role="tab" data-tab="yc" aria-selected="false">YC application</button>
    <button class="tab" role="tab" data-tab="tests" aria-selected="false">Test plan</button>
    <button class="tab" role="tab" data-tab="qa" aria-selected="false">QA · exit gate</button>
    <button class="tab" role="tab" data-tab="research" aria-selected="false">Research · protocol</button>
  </div>

  <section id="view-board" class="view active">
    <p class="gate"><strong>Gate.</strong> {esc(S1.SPRINT["gate"])}</p>
    <div class="progress" aria-label="Progress"><div class="bar"><span id="bar-done"></span><span id="bar-doing"></span></div><p class="notice" id="progress-text">0 of {sum(c["est"] for c in ALL_CARDS)} estimated hours done</p></div>
    <div class="toolbar">
      <span class="k">Sprint</span>{sprint_filters}
      <span class="k">Lane</span>{lane_filters}
      <span class="k">Owner</span><select id="f-owner"><option value="">all</option>{owner_options}</select>
      <span class="k">Day</span><select id="f-day"><option value="">all</option>{day_options}</select>
      <label><input type="checkbox" id="f-p0"> P0 only</label>
      <button type="button" id="export">Copy standup summary</button>
      <button type="button" id="add-card">Add ad-hoc card</button>
      <span class="notice" id="toolbar-note"></span>
    </div>
    <div class="board">{columns_html()}</div>
    <div class="drawer" id="drawer" hidden></div>
    <div class="drawer" id="activity"><h4>Recent moves</h4><p class="notice">No moves yet.</p></div>
  </section>

  <section id="view-days" class="view">
    <h2>Plan by day</h2>
    <p class="notice">Cards by the day they are planned to start. A card waiting on an unfinished dependency shows it.</p>
    <div class="board days" id="days-board"></div>
  </section>

  <section id="view-tests" class="view">
    <h2>Test plan</h2>
    <p class="notice">Acceptance tests are written before the implementation; the agent writes them from the spec, Leo reviews the tests, the agent implements until they pass. QA is what a reviewer verifies beyond the tests.</p>
    {tests_html()}
  </section>

  <section id="view-yc" class="view">
    <h2>YC Winter 2027 application</h2>
    {yc_html()}
  </section>

  <section id="view-qa" class="view">
    <h2>QA · exit gates</h2>
    <p class="notice">Shared checklists. Nothing closes a sprint until every line is ticked, and a tick means the evidence exists (a report, a log, a quote, a recording).</p>
    {qa_html()}
  </section>

  <section id="view-research" class="view">
    <h2>Research behind the cards, and the protocol for S1–S8</h2>
    {research_html()}
  </section>
</div>
<script>{JS.replace("__MODEL__", MODEL_JSON)}</script>
"""
OUT_HTML.write_text(PAGE, encoding="utf-8")

# ---- db seed (ArtifactData batch): cards + qa
seed = {"cards": {c["id"]: dict(c, notes="", blocked="", movedAt="") for c in M.CARDS},
        "qa": {q["id"]: dict(text=q["text"], owner=q["owner"], checked=False) for q in M.QA_GATE}}
OUT_SEED.write_text(json.dumps(seed, ensure_ascii=False, indent=1), encoding="utf-8")
seed1 = {"cards": {c["id"]: dict(c, notes="", blocked="", movedAt="") for c in S1.CARDS},
         "qa": {q["id"]: dict(text=q["text"], owner=q["owner"], checked=False) for q in S1.QA_GATE},
         "yc": {y["id"]: dict(ask=y["ask"], evidence=y["evidence"], source=y["source"], owner=y["owner"], checked=False) for y in S1.YC_CHECKLIST}}
OUT_SEED1.write_text(json.dumps(seed1, ensure_ascii=False, indent=1), encoding="utf-8")

# ---- sprint markdown (repo docs/sprints/S0.md, S1.md, ROAD_TO_YC.md)
def sprint_md(SP, CARDS, QA):
    md = [f"# {SP['name']} ({SP['start']} → {SP['end']})", "", f"**Goal.** {SP['goal']}", "", f"**Gate.** {SP['gate']}", "",
          "Live board: the \"Road to YC Board\" artifact (moves, notes and the gates are shared). Generated from docs/sprints/*_model.py.", "", "## Cards", ""]
    for lane_key, (lane_name, owner_desc, _) in M.LANES.items():
        cs = [x for x in CARDS if x["lane"] == lane_key]
        if not cs: continue
        md += [f"### Lane {lane_key} · {lane_name} — {owner_desc}", ""]
        for c in cs:
            md += [f"#### {c['id']} · {c['title']}", "",
                   f"**Owner** {c['owner']} · **Estimate** {c['est']} h · **Day** {c['day']} · **Priority** {c['prio']} · **Depends on** {', '.join(c['deps']) or 'none'}", "",
                   f"**Spec.** {c['spec']}", "", "**Acceptance tests.**"] + [f"{i + 1}. {t}" for i, t in enumerate(c["tests"])] + ["",
                   "**QA.** " + " · ".join(c["qa"]), "", "**Definition of done.** " + " · ".join(c["dod"]), "",
                   "**Research.** " + " · ".join(c["refs"]), "", "**Telemetry.** " + " · ".join(c["telemetry"]), ""]
    md += ["## Exit gate (QA checklist)", ""] + [f"- [ ] {q['id']} {q['text']} — {q['owner']}" for q in QA] + [""]
    return md
OUT_MD1.write_text("\n".join(sprint_md(S1.SPRINT, S1.CARDS, S1.QA_GATE)), encoding="utf-8")
road = ["# Road to YC — Winter 2027 application", "", f"**{S1.DEADLINE['label']}: {S1.DEADLINE['when']}.** Submit {S1.DEADLINE['submit']}. Freeze: {S1.DEADLINE['freeze']}. Source: {S1.DEADLINE['source']}", "",
        "## Day by day", "", "| Day | Sprint | Critical path |", "|---|---|---|"] + [f"| {d} | {sp} | {t} |" for d, sp, t in S1.DAILY] + ["",
        "## Evidence checklist", "", "| ID | The form asks | Evidence we bring | Source | Owner |", "|---|---|---|---|---|"] + [f"| {y['id']} | {y['ask']} | {y['evidence']} | {y['source']} | {y['owner']} |" for y in S1.YC_CHECKLIST] + ["",
        "## Cut until after 2 November", ""] + [f"- {c}" for c in S1.CUTS] + ["", "Sprint documents: `docs/sprints/S0.md`, `docs/sprints/S1.md`.", ""]
OUT_ROAD.write_text("\n".join(road), encoding="utf-8")
md = [f"# {M.SPRINT['name']} ({M.SPRINT['start']} → {M.SPRINT['end']})", "",
      f"**Goal.** {M.SPRINT['goal']}", "", f"**Gate.** {M.SPRINT['gate']}", "",
      "Live board: the \"Sprint 0 Board\" artifact (moves, notes and the QA gate are shared). This file is generated from `docs/sprints/s0_model.py`.", "",
      "## Cards", ""]
for lane_key, (lane_name, owner_desc, _) in M.LANES.items():
    md += [f"### Lane {lane_key} · {lane_name} — {owner_desc}", ""]
    for c in [x for x in M.CARDS if x["lane"] == lane_key]:
        md += [f"#### {c['id']} · {c['title']}", "",
               f"**Owner** {c['owner']} · **Estimate** {c['est']} h · **Day** {c['day']} · **Priority** {c['prio']} · **Depends on** {', '.join(c['deps']) or 'none'}", "",
               f"**Spec.** {c['spec']}", "",
               "**Acceptance tests.**"] + [f"{i + 1}. {t}" for i, t in enumerate(c["tests"])] + ["",
               "**QA.** " + " · ".join(c["qa"]), "",
               "**Definition of done.** " + " · ".join(c["dod"]), "",
               "**Research.** " + " · ".join(c["refs"]), "",
               "**Telemetry.** " + " · ".join(c["telemetry"]), ""]
md += ["## Exit gate (QA checklist)", ""] + [f"- [ ] {q['id']} {q['text']} — {q['owner']}" for q in M.QA_GATE] + ["",
       "## Research digest", ""]
for title, items in RESEARCH:
    md += [f"### {title}", ""] + [f"- **{k}.** {v} ({u})" for k, v, u in items] + [""]
md += ["### Questions for counsel", ""] + [f"{i + 1}. {x}" for i, x in enumerate(LAWYER)] + ["",
       "## The planning protocol (S1–S8)", ""] + [f"- **{k}.** {v}" for k, v in M.PROTOCOL] + ["",
       "## S1 research brief (drafted now)", ""] + [f"- {x}" for x in M.S1_BRIEF] + [""]
OUT_MD.write_text("\n".join(md), encoding="utf-8")
print("html", len(PAGE) // 1024, "KB;", len(ALL_CARDS), "cards;", len(ALL_QA), "qa items;", len(S1.YC_CHECKLIST), "yc items")
