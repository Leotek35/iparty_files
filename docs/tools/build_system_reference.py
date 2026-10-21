"""Render arch_model.py into the interactive system-reference page, a markdown register and a JSON file."""
import html
import json
import sys
from pathlib import Path
from pathlib import Path as _P

sys.path.insert(0, str(_P(__file__).resolve().parents[1]))
sys.path.insert(0, str(_P(__file__).resolve().parents[1] / "sprints"))
import architecture_model as M  # docs/architecture_model.py

HERE = Path(__file__).resolve().parents[1]  # docs/
OUT_HTML = HERE / "tools" / "out" / "system-reference.html"
OUT_MD = HERE / "ARCHITECTURE.md"
OUT_JSON = HERE / "architecture.json"
OUT_HTML.parent.mkdir(parents=True, exist_ok=True)

NODES = {n["id"]: n for n in M.NODES}
LANE_INDEX = {lid: i for i, (lid, _, _) in enumerate(M.LANES)}

# ------------------------------------------------------------------ geometry
NODE_W, NODE_H = 150, 58
PITCH = 160
LEFT = 138
TOP = 8
LANE_PAD = 16
LANE_H = NODE_H + 2 * LANE_PAD
MAX_COLS = max(n["col"] for n in M.NODES) + 1
WIDTH = LEFT + MAX_COLS * PITCH + 12
HEIGHT = TOP + len(M.LANES) * LANE_H + 8

def pos(n):
    x = LEFT + n["col"] * PITCH
    y = TOP + LANE_INDEX[n["lane"]] * LANE_H + LANE_PAD
    return x, y

def wrap2(desc, n=22):
    words = desc.split(); a, b = [], []
    for w in words:
        if len(" ".join(a + [w])) <= n and not b: a.append(w)
        else: b.append(w)
    bs = " ".join(b)
    if len(bs) > n: bs = bs[:n - 1] + "…"
    return " ".join(a), bs

def esc(s):
    return html.escape(str(s), quote=True)

# ------------------------------------------------------------------ svg
def edge_path(a, b):
    ax, ay = pos(a); bx, by = pos(b)
    la, lb = LANE_INDEX[a["lane"]], LANE_INDEX[b["lane"]]
    if la < lb:  # downward
        sx, sy = ax + NODE_W / 2, ay + NODE_H
        tx, ty = bx + NODE_W / 2, by
        dy = max(24, (ty - sy) * 0.5)
        return f"M{sx:.0f},{sy:.0f} C{sx:.0f},{sy + dy:.0f} {tx:.0f},{ty - dy:.0f} {tx:.0f},{ty:.0f}"
    if la > lb:  # upward
        sx, sy = ax + NODE_W / 2, ay
        tx, ty = bx + NODE_W / 2, by + NODE_H
        dy = max(24, (sy - ty) * 0.5)
        return f"M{sx:.0f},{sy:.0f} C{sx:.0f},{sy - dy:.0f} {tx:.0f},{ty + dy:.0f} {tx:.0f},{ty:.0f}"
    # same lane: side to side
    if ax < bx:
        sx, sy = ax + NODE_W, ay + NODE_H / 2; tx, ty = bx, by + NODE_H / 2
    else:
        sx, sy = ax, ay + NODE_H / 2; tx, ty = bx + NODE_W, by + NODE_H / 2
    return f"M{sx:.0f},{sy:.0f} C{(sx + tx) / 2:.0f},{sy - 26:.0f} {(sx + tx) / 2:.0f},{ty - 26:.0f} {tx:.0f},{ty:.0f}"

svg = [f'<svg id="arch" viewBox="0 0 {WIDTH} {HEIGHT}" width="{WIDTH}" height="{HEIGHT}" role="img" aria-labelledby="arch-title" xmlns="http://www.w3.org/2000/svg">',
       '<title id="arch-title">iParty system reference: eleven lanes from end users to quality gates, every system color-coded by domain, status and customer-experience impact</title>',
       '<defs>']
for kind in ("flow", "data", "gate", "planned"):
    svg.append(f'<marker id="m-{kind}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" class="mh-{kind}"/></marker>')
svg.append('</defs>')
# lanes
for i, (lid, name, desc) in enumerate(M.LANES):
    y = TOP + i * LANE_H
    svg.append(f'<g class="lane dom-{lid}"><rect x="0" y="{y}" width="{WIDTH}" height="{LANE_H}" class="lane-bg"/>'
               f'<line x1="0" y1="{y}" x2="{WIDTH}" y2="{y}" class="lane-line"/>'
               f'<text x="12" y="{y + 30}" class="lane-name">{esc(name)}</text>'
               f'<text x="12" y="{y + 46}" class="lane-desc">{esc(wrap2(desc)[0])}</text><text x="12" y="{y + 59}" class="lane-desc">{esc(wrap2(desc)[1])}</text></g>')
# edges
for (a, b, kind, label) in M.EDGES:
    na, nb = NODES[a], NODES[b]
    d = edge_path(na, nb)
    svg.append(f'<path d="{d}" class="edge e-{kind}" data-a="{a}" data-b="{b}" marker-end="url(#m-{kind})"><title>{esc(a)} → {esc(b)}{(" · " + esc(label)) if label else ""}</title></path>')
# nodes
for n in M.NODES:
    x, y = pos(n)
    st = "built" if n["status"] == "built" else "planned"
    sprint = "" if n["status"] == "built" else n["status"]
    label = esc(n["label"]); sub = esc(n["sub"])
    svg.append(f'<g class="node dom-{n["lane"]} st-{st} cx-{n["cx"]}" data-id="{n["id"]}" tabindex="0" role="button" aria-label="{label}: {esc(n["purpose"][:80])}">'
               f'<rect x="{x}" y="{y}" width="{NODE_W}" height="{NODE_H}" rx="6" class="node-bg"/>'
               f'<rect x="{x}" y="{y}" width="{NODE_W}" height="6" rx="3" class="node-strip"/>'
               f'<text x="{x + 9}" y="{y + 25}" class="node-label">{label}</text>'
               f'<text x="{x + 9}" y="{y + 40}" class="node-sub">{sub}</text>'
               f'<text x="{x + 9}" y="{y + 52}" class="node-id">{n["id"]}{(" · " + sprint) if sprint else ""}</text>'
               f'<g class="cx-badge"><circle cx="{x + NODE_W - 13}" cy="{y + 17}" r="9"/><text x="{x + NODE_W - 13}" y="{y + 20.5}" text-anchor="middle">{n["cx"]}</text></g>'
               f'</g>')
svg.append('</svg>')
SVG = "\n".join(svg)

# ------------------------------------------------------------------ panel (server-rendered for the default node)
def method_badge(m):
    return f'<span class="mb mb-{m}" title="{esc(M.METHODS[m])}">{m}</span>'

def chips(items, cls="chip"):
    return "".join(f'<span class="{cls}">{esc(i)}</span>' for i in items)

def inspections_for(nid):
    return [x for x in M.INSPECTIONS if x["a"] == nid or x["b"] == nid]

def render_panel(n):
    cxname, cxdesc = M.CX[n["cx"]]
    lane_name = dict((l[0], l[1]) for l in M.LANES)[n["lane"]]
    parts = [f'<div class="ph"><div><p class="eyebrow">{esc(n["id"])} · {esc(lane_name)}</p><h3>{esc(n["label"])} <span class="sub">{esc(n["sub"])}</span></h3></div>'
             f'<div class="pills"><span class="pill st-{"built" if n["status"] == "built" else "planned"}">{esc(M.STATUS[n["status"]])}</span><span class="pill cx-{n["cx"]}" title="{esc(cxdesc)}">{n["cx"]} · {esc(cxname)}</span></div></div>',
             f'<section><h4>Purpose</h4><p>{esc(n["purpose"])}</p></section>',
             f'<section><h4>Customer-experience impact</h4><p><strong>{n["cx"]} — {esc(cxname)}.</strong> {esc(cxdesc)}</p></section>',
             '<section><h4>Interfaces</h4><ul>' + "".join(f'<li>{esc(i)}</li>' for i in n["interfaces"]) + '</ul></section>',
             '<section><h4>Validation methodology</h4><ul class="val">' + "".join(f'<li>{method_badge(m)} {esc(t)}</li>' for m, t in n["validation"]) + '</ul></section>',
             '<section><h4>Cross-performance inspections</h4><ul>' + "".join(f'<li>{esc(i)}</li>' for i in n["inspections"]) +
             "".join(f'<li><a href="#{x["id"]}"><strong>{x["id"]}</strong></a> {esc(x["a"])} ⟂ {esc(x["b"])}: {esc(x["what"])} <em>({esc(x["method"])}, {esc(x["freq"])}; pass: {esc(x["threshold"])})</em></li>' for x in inspections_for(n["id"])) + '</ul></section>',
             '<section><h4>Telemetry and logs to check</h4><ul>' + "".join(f'<li><code>{esc(t)}</code></li>' for t in n["telemetry"]) + '</ul></section>']
    fm = []
    for f in n["failures"]:
        fm.append(f'<div class="fm"><p class="fm-sym">{esc(f["symptom"])}</p>'
                  f'<p class="fm-row"><span class="k">Touch</span>{chips(f["touch"], "chip chip-touch")}</p>'
                  f'<p class="fm-row"><span class="k">Logs</span>{chips(f["logs"], "chip chip-log")}</p>'
                  f'<ol class="fm-checks">' + "".join(f'<li>{esc(c)}</li>' for c in f["checks"]) + '</ol></div>')
    parts.append('<section><h4>If it breaks</h4>' + "".join(fm) + '</section>')
    if n["touch"]:
        parts.append('<section><h4>Where to touch</h4><p>' + chips(n["touch"], "chip chip-touch") + '</p></section>')
    if n.get("cards"):
        parts.append('<section><h4>Sprint cards</h4><p>' + " ".join(f'<a class="chip chip-card" href="{M.BOARD_URL}#{c}" rel="noopener">{c}</a>' for c in n["cards"]) + '</p></section>')
    parts.append(f'<p class="deep">Deep link: <code>#{n["id"]}</code></p>')
    return "".join(parts)

DEFAULT = "ENG-PLANNER"

# ------------------------------------------------------------------ register tables
def register_table():
    rows = []
    for n in M.NODES:
        lane_name = dict((l[0], l[1]) for l in M.LANES)[n["lane"]]
        val = " ".join(f'{method_badge(m)}' for m, _ in n["validation"])
        rows.append(f'<tr id="{n["id"]}"><td><a href="#{n["id"]}">{n["id"]}</a><br><strong>{esc(n["label"])}</strong><br><span class="dim">{esc(n["sub"])}</span></td>'
                    f'<td>{esc(lane_name)}</td><td><span class="pill st-{"built" if n["status"] == "built" else "planned"}">{esc(n["status"] if n["status"] != "built" else "built")}</span></td>'
                    f'<td><span class="pill cx-{n["cx"]}">{n["cx"]}</span></td><td>{esc(n["purpose"])}</td><td>{val}<br>' + "<br>".join(esc(t) for _, t in n["validation"]) + '</td>'
                    '<td>' + "<br>".join(f'<code>{esc(t)}</code>' for t in n["telemetry"]) + '</td><td>' + chips(n["touch"], "chip chip-touch") + '</td></tr>')
    return ('<div class="table-wrap"><table class="register"><thead><tr><th>System</th><th>Lane</th><th>Status</th><th>CX</th><th>Purpose</th><th>Validation</th><th>Logs &amp; telemetry</th><th>Touch</th></tr></thead><tbody>'
            + "".join(rows) + '</tbody></table></div>')

def inspection_table():
    rows = []
    for x in M.INSPECTIONS:
        rows.append(f'<tr id="{x["id"]}"><td><strong>{x["id"]}</strong></td><td><a href="#{x["a"]}">{x["a"]}</a> ⟂ <a href="#{x["b"]}">{x["b"]}</a></td><td>{esc(x["what"])}</td>'
                    f'<td>{" ".join(method_badge(m) for m in x["method"].split("/"))}</td><td>{esc(x["freq"])}</td><td>{esc(x["threshold"])}</td><td><code>{esc(x["where"])}</code></td>'
                    f'<td><span class="pill st-{"built" if x["status"] == "built" else "planned"}">{esc(x["status"])}</span></td></tr>')
    return ('<div class="table-wrap"><table class="matrix"><thead><tr><th>ID</th><th>A ⟂ B</th><th>What is inspected</th><th>Method</th><th>Frequency</th><th>Pass threshold</th><th>Where results live</th><th>Status</th></tr></thead><tbody>'
            + "".join(rows) + '</tbody></table></div>')

def triage_table():
    rows = []
    for s in M.SYMPTOMS:
        rows.append(f'<tr id="{s["id"]}"><td><strong>{s["id"]}</strong></td><td><span class="pill cx-{s["cx"]}">{s["cx"]}</span></td><td><strong>{esc(s["title"])}</strong></td>'
                    f'<td>' + " → ".join(f'<a href="#{i}">{i}</a>' for i in s["nodes"]) + '</td><td><ol>' + "".join(f'<li>{esc(st)}</li>' for st in s["steps"]) + '</ol></td><td>' + chips(s["touch"], "chip chip-touch") + '</td></tr>')
    return ('<div class="table-wrap"><table class="triage"><thead><tr><th>ID</th><th>CX</th><th>Symptom</th><th>Path through the diagram</th><th>Checks, in order</th><th>Touch</th></tr></thead><tbody>'
            + "".join(rows) + '</tbody></table></div>')

# ------------------------------------------------------------------ page
MODEL_JSON = json.dumps(dict(board=M.BOARD_URL, lanes=M.LANES, status=M.STATUS, cx=M.CX, methods=M.METHODS, nodes=M.NODES, edges=M.EDGES,
                             inspections=M.INSPECTIONS, symptoms=M.SYMPTOMS), ensure_ascii=False)

symptom_options = "".join(f'<option value="{s["id"]}">{esc(s["id"])} · {esc(s["title"])}</option>' for s in M.SYMPTOMS)
node_options = "".join(f'<option value="{n["id"]}">{esc(n["label"])}</option>' for n in M.NODES)
dom_filters = "".join(f'<button type="button" class="fchip" data-dom="{lid}" aria-pressed="true"><i class="sw dom-{lid}"></i>{esc(name)}</button>' for lid, name, _ in M.LANES)
cx_filters = "".join(f'<button type="button" class="fchip" data-cx="{k}" aria-pressed="true"><span class="pill cx-{k}">{k}</span></button>' for k in M.CX)
edge_filters = "".join(f'<button type="button" class="fchip" data-edge="{k}" aria-pressed="true">{k}</button>' for k in ("flow", "data", "gate", "planned"))
dom_legend = "".join(f'<span class="lg"><i class="sw dom-{lid}"></i>{esc(name)}</span>' for lid, name, _ in M.LANES)
cx_legend = "".join(f'<span class="lg"><span class="pill cx-{k}">{k}</span>{esc(v[0])}</span>' for k, v in M.CX.items())
method_legend = "".join(f'<span class="lg">{method_badge(k)}{esc(v.split(" — ")[1])}</span>' for k, v in M.METHODS.items())

built = sum(1 for n in M.NODES if n["status"] == "built")
planned = len(M.NODES) - built

CSS = r"""
/* Layout: an engineering reference — a wide, scrollable system diagram (11 lanes), a detail panel for the
   selected system, then the printed registers (systems, cross-inspections, triage). */
:root {
  --bg: #f7f8f6; --bg-2: #eef1ec; --fg: #16211d; --fg-2: #4b5751; --line: #d3d9d3; --accent: #0e6f63; --accent-2: #b8442f;
  --node-bg: #ffffff; --panel: #ffffff;
  --dom-users: #6b5bd2; --dom-surfaces: #2f7bd7; --dom-api: #1c8c7a; --dom-engine: #c2521f; --dom-verify: #b3261e;
  --dom-catalog: #8a6d0b; --dom-living: #2d8a4e; --dom-data: #5f6b7a; --dom-fulfil: #a3417f; --dom-external: #6e6e6e; --dom-gates: #0f5f8c;
  --c1: #b3261e; --c2: #c2521f; --c3: #2f7bd7; --c4: #6e6e6e;
  --display: "Bricolage Grotesque", "Avenir Next", "Helvetica Neue", Arial, sans-serif;
  --body: "Literata", Georgia, "Times New Roman", serif;
  --mono: "IBM Plex Mono", "SFMono-Regular", Menlo, Consolas, monospace;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg: #121816; --bg-2: #1b2320; --fg: #e8ece8; --fg-2: #a9b3ad; --line: #2e3934; --accent: #5fc2b3; --accent-2: #f08a74;
  --node-bg: #1f2724; --panel: #171e1b;
  --dom-users: #a99af5; --dom-surfaces: #7fb3f0; --dom-api: #62c6b4; --dom-engine: #f0996f; --dom-verify: #f08a84;
  --dom-catalog: #d9b949; --dom-living: #7fcf98; --dom-data: #a8b4c2; --dom-fulfil: #e08bc6; --dom-external: #b4b4b4; --dom-gates: #78b5dc;
  --c1: #f08a84; --c2: #f0996f; --c3: #7fb3f0; --c4: #b4b4b4; color-scheme: dark; } }
:root[data-theme="dark"] {
  --bg: #121816; --bg-2: #1b2320; --fg: #e8ece8; --fg-2: #a9b3ad; --line: #2e3934; --accent: #5fc2b3; --accent-2: #f08a74;
  --node-bg: #1f2724; --panel: #171e1b;
  --dom-users: #a99af5; --dom-surfaces: #7fb3f0; --dom-api: #62c6b4; --dom-engine: #f0996f; --dom-verify: #f08a84;
  --dom-catalog: #d9b949; --dom-living: #7fcf98; --dom-data: #a8b4c2; --dom-fulfil: #e08bc6; --dom-external: #b4b4b4; --dom-gates: #78b5dc;
  --c1: #f08a84; --c2: #f0996f; --c3: #7fb3f0; --c4: #b4b4b4; color-scheme: dark; }
* { box-sizing: border-box; }
body { background: var(--bg); color: var(--fg); font-family: var(--body); font-size: 16px; line-height: 1.55;
  padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)); padding-block: 0 64px; }
a { color: var(--accent); text-decoration-thickness: 1px; text-underline-offset: 2px; }
a:focus-visible, button:focus-visible, select:focus-visible, .node:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.wrap { max-width: 1640px; margin: 0 auto; }
header.masthead { padding-block: 36px 20px; border-bottom: 1px solid var(--line); display: flex; flex-wrap: wrap; gap: 16px 40px; align-items: end; justify-content: space-between; }
.eyebrow { font-family: var(--mono); font-size: 12px; letter-spacing: .08em; text-transform: uppercase; color: var(--fg-2); margin: 0 0 10px; }
h1 { font-family: var(--display); font-weight: 800; font-size: clamp(30px, 4vw, 46px); line-height: 1.02; letter-spacing: -.02em; margin: 0 0 10px; text-wrap: balance; }
h1 em { font-style: normal; color: var(--accent-2); }
.sub { color: var(--fg-2); max-width: 70ch; margin: 0; }
.stats { display: flex; gap: 18px; flex-wrap: wrap; font-family: var(--mono); font-size: 12px; color: var(--fg-2); }
.stats b { color: var(--fg); font-size: 20px; font-family: var(--display); display: block; }
h2 { font-family: var(--display); font-weight: 700; font-size: 26px; margin: 44px 0 10px; padding-top: 16px; border-top: 1px solid var(--line); text-wrap: balance; }
h3 { font-family: var(--display); font-weight: 700; font-size: 20px; margin: 0; }
h3 .sub { font-family: var(--mono); font-size: 12px; margin-left: 8px; }
h4 { font-family: var(--mono); font-size: 11.5px; letter-spacing: .08em; text-transform: uppercase; color: var(--fg-2); margin: 16px 0 6px; }
p { margin: 0 0 12px; }
ul, ol { margin: 0 0 10px; padding-left: 1.2em; } li { margin-bottom: 5px; }
code { font-family: var(--mono); font-size: .86em; background: var(--bg-2); padding: 1px 5px; border-radius: 3px; }
.how { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 14px 28px; margin: 18px 0 8px; max-width: 1200px; }
.how p { margin: 0; font-size: 15px; }
.legend { display: flex; flex-wrap: wrap; gap: 8px 18px; margin: 12px 0 8px; font-family: var(--display); font-size: 13px; align-items: center; }
.legend .k { font-family: var(--mono); font-size: 11px; letter-spacing: .06em; text-transform: uppercase; color: var(--fg-2); margin-right: 4px; }
.lg { display: inline-flex; align-items: center; gap: 6px; }
.sw { width: 12px; height: 12px; border-radius: 3px; display: inline-block; background: var(--dom); }
.sw.dom-users{--dom:var(--dom-users)} .sw.dom-surfaces{--dom:var(--dom-surfaces)} .sw.dom-api{--dom:var(--dom-api)} .sw.dom-engine{--dom:var(--dom-engine)} .sw.dom-verify{--dom:var(--dom-verify)} .sw.dom-catalog{--dom:var(--dom-catalog)} .sw.dom-living{--dom:var(--dom-living)} .sw.dom-data{--dom:var(--dom-data)} .sw.dom-fulfil{--dom:var(--dom-fulfil)} .sw.dom-external{--dom:var(--dom-external)} .sw.dom-gates{--dom:var(--dom-gates)}
.lg-line { width: 28px; height: 0; border-top: 2px solid var(--fg-2); display: inline-block; }
.lg-line.dashed { border-top-style: dashed; } .lg-line.dotted { border-top-style: dotted; } .lg-line.gate { border-color: var(--dom-verify); } .lg-line.data { border-color: var(--accent); border-top-style: dashed; }
.lg-box { width: 22px; height: 14px; border: 2px solid var(--fg-2); border-radius: 3px; display: inline-block; } .lg-box.planned { border-style: dashed; }
.toolbar { display: flex; flex-wrap: wrap; gap: 10px 18px; align-items: center; margin: 14px 0; font-family: var(--display); font-size: 14px; }
.toolbar label { display: inline-flex; gap: 6px; align-items: center; }
.toolbar.filters { gap: 6px 10px; } .toolbar .k { font-family: var(--mono); font-size: 11px; letter-spacing: .06em; text-transform: uppercase; color: var(--fg-2); margin: 0 4px 0 8px; }
.fchip { display: inline-flex; align-items: center; gap: 6px; font-family: var(--display); font-size: 12.5px; padding: 4px 9px; border-radius: 999px; }
.fchip[aria-pressed="false"] { opacity: .45; text-decoration: line-through; }
input[type=search], input[type=text], textarea { font: inherit; font-family: var(--display); color: var(--fg); background: var(--panel); border: 1px solid var(--line); border-radius: 6px; padding: 6px 10px; min-width: 0; }
.chip-card { border: 1px solid var(--dom-users); text-decoration: none; }
.step circle { fill: var(--accent-2); } .step text { fill: var(--bg); font-size: 10px; font-weight: 800; font-family: var(--mono); }
svg.fit { width: 100%; height: auto; }
svg .node.dim-f, svg .edge.dim-f { display: none; }
.inc-form { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 14px 16px; max-width: 900px; display: grid; gap: 10px; }
.inc-form .row { display: grid; grid-template-columns: 170px minmax(0, 1fr); gap: 10px; align-items: start; }
@media (max-width: 640px) { .inc-form .row { grid-template-columns: 1fr; } }
.inc-form label { font-family: var(--mono); font-size: 11.5px; letter-spacing: .06em; text-transform: uppercase; color: var(--fg-2); padding-top: 8px; }
.inc-form textarea { min-height: 70px; width: 100%; } .inc-form .actions { grid-template-columns: auto 1fr; align-items: center; }
.inc-list { display: grid; gap: 10px; margin-top: 14px; max-width: 900px; }
.inc { background: var(--panel); border: 1px solid var(--line); border-left: 4px solid var(--accent-2); border-radius: 6px; padding: 10px 14px; }
.inc.resolved { border-left-color: var(--dom-living); opacity: .8; }
.inc h5 { font-family: var(--display); font-size: 15px; margin: 0 0 4px; } .inc .m { font-family: var(--mono); font-size: 11px; color: var(--fg-2); margin: 0 0 6px; }
.inc p { margin: 0 0 6px; font-size: 14.5px; } .inc .acts { display: flex; gap: 8px; }
.notice { font-family: var(--mono); font-size: 12px; color: var(--fg-2); }
select, button { font: inherit; font-family: var(--display); color: var(--fg); background: var(--panel); border: 1px solid var(--line); border-radius: 6px; padding: 6px 10px; }
select { max-width: 100%; min-width: 0; }
button { cursor: pointer; } button:hover { border-color: var(--accent); }
.diagram { overflow-x: auto; border: 1px solid var(--line); border-radius: 6px; background: var(--panel); }
svg#arch { display: block; font-family: var(--display); }
.lane-bg { fill: var(--dom); fill-opacity: .06; } .lane-line { stroke: var(--line); stroke-width: 1; }
.lane-name { fill: var(--fg); font-size: 13px; font-weight: 700; } .lane-desc { fill: var(--fg-2); font-size: 10.5px; }
.lane.dom-users{--dom:var(--dom-users)} .lane.dom-surfaces{--dom:var(--dom-surfaces)} .lane.dom-api{--dom:var(--dom-api)} .lane.dom-engine{--dom:var(--dom-engine)} .lane.dom-verify{--dom:var(--dom-verify)} .lane.dom-catalog{--dom:var(--dom-catalog)} .lane.dom-living{--dom:var(--dom-living)} .lane.dom-data{--dom:var(--dom-data)} .lane.dom-fulfil{--dom:var(--dom-fulfil)} .lane.dom-external{--dom:var(--dom-external)} .lane.dom-gates{--dom:var(--dom-gates)}
.node { cursor: pointer; --dom: var(--fg-2); }
.node.dom-users{--dom:var(--dom-users)} .node.dom-surfaces{--dom:var(--dom-surfaces)} .node.dom-api{--dom:var(--dom-api)} .node.dom-engine{--dom:var(--dom-engine)} .node.dom-verify{--dom:var(--dom-verify)} .node.dom-catalog{--dom:var(--dom-catalog)} .node.dom-living{--dom:var(--dom-living)} .node.dom-data{--dom:var(--dom-data)} .node.dom-fulfil{--dom:var(--dom-fulfil)} .node.dom-external{--dom:var(--dom-external)} .node.dom-gates{--dom:var(--dom-gates)}
.node-bg { fill: var(--node-bg); stroke: var(--dom); stroke-width: 1.4; } .node.st-planned .node-bg { stroke-dasharray: 5 3; }
.node-strip { fill: var(--dom); } .node.st-planned .node-strip { fill-opacity: .45; }
.node-label { fill: var(--fg); font-size: 12px; font-weight: 700; } .node-sub { fill: var(--fg-2); font-size: 9.5px; } .node-id { fill: var(--dom); font-size: 9.5px; font-family: var(--mono); letter-spacing: .04em; }
.cx-badge circle { fill: var(--bg); stroke: var(--cxc); stroke-width: 1.6; } .cx-badge text { fill: var(--cxc); font-size: 9.5px; font-weight: 800; font-family: var(--mono); }
.node.cx-C1{--cxc:var(--c1)} .node.cx-C2{--cxc:var(--c2)} .node.cx-C3{--cxc:var(--c3)} .node.cx-C4{--cxc:var(--c4)}
.node:hover .node-bg, .node.selected .node-bg { stroke-width: 3; } .node.selected .node-bg { filter: drop-shadow(0 0 6px var(--dom)); }
.edge { fill: none; stroke-width: 1.4; opacity: .5; } .e-flow { stroke: var(--fg-2); } .e-data { stroke: var(--accent); stroke-dasharray: 5 4; } .e-gate { stroke: var(--dom-verify); } .e-planned { stroke: var(--fg-2); stroke-dasharray: 2 4; opacity: .4; }
.mh-flow { fill: var(--fg-2); } .mh-data { fill: var(--accent); } .mh-gate { fill: var(--dom-verify); } .mh-planned { fill: var(--fg-2); }
svg.focus .node { opacity: .28; } svg.focus .node.selected, svg.focus .node.nb, svg.focus .node.path { opacity: 1; }
svg.focus .edge { opacity: .12; } svg.focus .edge.hot { opacity: 1; stroke-width: 2.4; }
svg.hide-planned .st-planned, svg.hide-planned .e-planned { display: none; }
.after { display: grid; grid-template-columns: 1fr; gap: 20px; margin-top: 18px; }
@media (min-width: 1100px) { .after { grid-template-columns: minmax(0, 1.4fr) minmax(0, 1fr); } }
.panel, .triage-card { background: var(--panel); border: 1px solid var(--line); border-radius: 6px; padding: 18px 20px 14px; min-width: 0; }
.ph { display: flex; flex-wrap: wrap; gap: 10px 20px; justify-content: space-between; align-items: start; border-bottom: 1px solid var(--line); padding-bottom: 12px; }
.pills { display: flex; flex-wrap: wrap; gap: 6px; }
.pill { display: inline-block; font-family: var(--mono); font-size: 11px; letter-spacing: .04em; padding: 3px 8px; border-radius: 999px; border: 1px solid var(--line); white-space: nowrap; }
.pill.st-built { background: color-mix(in srgb, var(--dom-living) 18%, transparent); border-color: var(--dom-living); } .pill.st-planned { border-style: dashed; }
.pill.cx-C1 { color: var(--c1); border-color: var(--c1); } .pill.cx-C2 { color: var(--c2); border-color: var(--c2); } .pill.cx-C3 { color: var(--c3); border-color: var(--c3); } .pill.cx-C4 { color: var(--c4); border-color: var(--c4); }
.mb { display: inline-block; font-family: var(--mono); font-size: 10.5px; font-weight: 700; width: 20px; text-align: center; border-radius: 4px; padding: 1px 0; margin-right: 6px; color: var(--bg); background: var(--fg-2); }
.mb-T { background: var(--dom-living); } .mb-A { background: var(--dom-surfaces); } .mb-I { background: var(--dom-catalog); } .mb-D { background: var(--dom-fulfil); } .mb-M { background: var(--dom-gates); }
.chip { display: inline-block; font-family: var(--mono); font-size: 11px; padding: 2px 7px; border-radius: 4px; margin: 2px 4px 2px 0; background: var(--bg-2); word-break: break-word; }
.chip-touch { border: 1px solid var(--dom-engine); } .chip-log { border: 1px solid var(--accent); }
.fm { border-left: 3px solid var(--accent-2); padding: 4px 0 4px 14px; margin: 10px 0 14px; }
.fm-sym { font-family: var(--display); font-weight: 700; margin-bottom: 6px; } .fm-row { margin: 0 0 4px; } .fm-row .k { font-family: var(--mono); font-size: 10.5px; letter-spacing: .06em; text-transform: uppercase; color: var(--fg-2); margin-right: 8px; }
.fm-checks { margin: 6px 0 0; font-size: 15px; }
.deep { font-family: var(--mono); font-size: 12px; color: var(--fg-2); margin-top: 14px; }
.val li { list-style: none; margin-left: -1.2em; }
.table-wrap { overflow-x: auto; margin: 14px 0 26px; border: 1px solid var(--line); border-radius: 4px; }
table { border-collapse: collapse; width: 100%; font-size: 13.5px; line-height: 1.45; font-family: var(--display); }
th, td { text-align: left; vertical-align: top; padding: 9px 11px; border-bottom: 1px solid var(--line); min-width: 8em; }
th { font-family: var(--mono); font-size: 11px; letter-spacing: .06em; text-transform: uppercase; color: var(--fg-2); background: var(--bg-2); position: sticky; top: 0; }
tbody tr:last-child td { border-bottom: 0; } tbody tr:nth-child(even) td { background: color-mix(in srgb, var(--bg-2) 55%, transparent); }
tr:target td { background: color-mix(in srgb, var(--accent) 14%, transparent) !important; }
td ol { padding-left: 1.1em; margin: 0; } td .dim { color: var(--fg-2); font-size: 12px; }
table.register td:nth-child(5) { min-width: 22em; } table.triage td:nth-child(5) { min-width: 26em; }
.triage-card h3 { font-size: 18px; } .triage-card ol { font-size: 15px; }
@media (prefers-reduced-motion: no-preference) { html { scroll-behavior: smooth; } }
"""

JS = r"""
(function(){
  const MODEL = __MODEL__;
  const nodes = Object.fromEntries(MODEL.nodes.map(n => [n.id, n]));
  const laneName = Object.fromEntries(MODEL.lanes.map(l => [l[0], l[1]]));
  const svg = document.getElementById('arch');
  const panel = document.getElementById('panel');
  const triageSel = document.getElementById('symptom');
  const triageCard = document.getElementById('triage');
  const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  const chips = (items, cls) => items.map(i => `<span class="${cls}">${esc(i)}</span>`).join('');
  const mb = m => `<span class="mb mb-${m}" title="${esc(MODEL.methods[m])}">${m}</span>`;
  const neighbors = id => { const s = new Set(); MODEL.edges.forEach(e => { if (e[0] === id) s.add(e[1]); if (e[1] === id) s.add(e[0]); }); return s; };
  const nodeEls = [...svg.querySelectorAll('.node')]; const edgeEls = [...svg.querySelectorAll('.edge')];
  let incidents = []; let db = null, uid = null, canWrite = false;

  function renderPanel(n) {
    const [cxname, cxdesc] = MODEL.cx[n.cx];
    const st = n.status === 'built' ? 'built' : 'planned';
    const insp = MODEL.inspections.filter(x => x.a === n.id || x.b === n.id);
    let h = `<div class="ph"><div><p class="eyebrow">${esc(n.id)} · ${esc(laneName[n.lane])}</p><h3>${esc(n.label)} <span class="sub">${esc(n.sub)}</span></h3></div>
      <div class="pills"><span class="pill st-${st}">${esc(MODEL.status[n.status])}</span><span class="pill cx-${n.cx}" title="${esc(cxdesc)}">${n.cx} · ${esc(cxname)}</span></div></div>`;
    h += `<section><h4>Purpose</h4><p>${esc(n.purpose)}</p></section>`;
    h += `<section><h4>Customer-experience impact</h4><p><strong>${n.cx} — ${esc(cxname)}.</strong> ${esc(cxdesc)}</p></section>`;
    h += `<section><h4>Interfaces</h4><ul>${n.interfaces.map(i => `<li>${esc(i)}</li>`).join('')}</ul></section>`;
    h += `<section><h4>Validation methodology</h4><ul class="val">${n.validation.map(v => `<li>${mb(v[0])} ${esc(v[1])}</li>`).join('')}</ul></section>`;
    h += `<section><h4>Cross-performance inspections</h4><ul>${n.inspections.map(i => `<li>${esc(i)}</li>`).join('')}${insp.map(x => `<li><a href="#${x.id}"><strong>${x.id}</strong></a> ${esc(x.a)} ⟂ ${esc(x.b)}: ${esc(x.what)} <em>(${esc(x.method)}, ${esc(x.freq)}; pass: ${esc(x.threshold)})</em></li>`).join('')}</ul></section>`;
    h += `<section><h4>Telemetry and logs to check</h4><ul>${n.telemetry.map(t => `<li><code>${esc(t)}</code></li>`).join('')}</ul></section>`;
    h += `<section><h4>If it breaks</h4>${n.failures.map(f => `<div class="fm"><p class="fm-sym">${esc(f.symptom)}</p><p class="fm-row"><span class="k">Touch</span>${chips(f.touch, 'chip chip-touch')}</p><p class="fm-row"><span class="k">Logs</span>${chips(f.logs, 'chip chip-log')}</p><ol class="fm-checks">${f.checks.map(c => `<li>${esc(c)}</li>`).join('')}</ol></div>`).join('')}</section>`;
    if (n.touch.length) h += `<section><h4>Where to touch</h4><p>${chips(n.touch, 'chip chip-touch')}</p></section>`;
    if (n.cards && n.cards.length) h += `<section><h4>Sprint cards</h4><p>${n.cards.map(c => `<a class="chip chip-card" href="${MODEL.board}#${c}" rel="noopener">${c}</a>`).join(' ')}</p></section>`;
    const incs = incidents.filter(i => (i.nodes || []).includes(n.id));
    if (incs.length) h += `<section><h4>Incidents on this system</h4><ul>${incs.map(i => `<li>${esc(i.date)} · ${esc(i.title)} <em>(${i.status === 'resolved' ? 'resolved' : 'open'})</em></li>`).join('')}</ul></section>`;
    h += `<p class="deep">Deep link: <code>#${n.id}</code></p>`;
    panel.innerHTML = h;
  }

  function clearMarks() {
    nodeEls.forEach(g => { g.classList.remove('selected', 'nb', 'path'); g.querySelectorAll('.step').forEach(x => x.remove()); });
    edgeEls.forEach(e => e.classList.remove('hot'));
  }
  function select(id, scroll) {
    const n = nodes[id]; if (!n) return;
    clearMarks(); svg.classList.add('focus');
    const nb = neighbors(id);
    nodeEls.forEach(g => { const gid = g.dataset.id; if (gid === id) g.classList.add('selected'); else if (nb.has(gid)) g.classList.add('nb'); });
    edgeEls.forEach(e => { if (e.dataset.a === id || e.dataset.b === id) e.classList.add('hot'); });
    renderPanel(n);
    if (scroll) panel.scrollIntoView({ block: 'nearest' });
  }
  function stepBadge(g, k) {
    const r = g.querySelector('.node-bg'); const x = +r.getAttribute('x') + +r.getAttribute('width') - 13, y = +r.getAttribute('y') + +r.getAttribute('height') - 11;
    const ns = 'http://www.w3.org/2000/svg'; const grp = document.createElementNS(ns, 'g'); grp.setAttribute('class', 'step');
    const c = document.createElementNS(ns, 'circle'); c.setAttribute('cx', x); c.setAttribute('cy', y); c.setAttribute('r', 8);
    const t = document.createElementNS(ns, 'text'); t.setAttribute('x', x); t.setAttribute('y', y + 3.5); t.setAttribute('text-anchor', 'middle'); t.textContent = k;
    grp.appendChild(c); grp.appendChild(t); g.appendChild(grp);
  }
  function triage(sid) {
    const s = MODEL.symptoms.find(x => x.id === sid);
    clearMarks();
    if (!s) { svg.classList.remove('focus'); triageCard.hidden = true; return; }
    svg.classList.add('focus');
    const order = new Map(s.nodes.map((id, i) => [id, i + 1]));
    nodeEls.forEach(g => { const k = order.get(g.dataset.id); if (k) { g.classList.add('path'); stepBadge(g, k); } });
    edgeEls.forEach(e => { if (order.has(e.dataset.a) && order.has(e.dataset.b)) e.classList.add('hot'); });
    triageCard.hidden = false;
    triageCard.innerHTML = `<p class="eyebrow">${esc(s.id)} · <span class="pill cx-${s.cx}">${s.cx}</span></p><h3>${esc(s.title)}</h3>
      <h4>Path through the diagram (numbered on the nodes)</h4><p>${s.nodes.map((i, k) => `<a href="#${i}">${k + 1}. ${i}</a>`).join(' → ')}</p>
      <h4>Checks, in order</h4><ol>${s.steps.map(st => `<li>${esc(st)}</li>`).join('')}</ol>
      <h4>Where to touch</h4><p>${chips(s.touch, 'chip chip-touch')}</p>
      <p class="notice">Log what you found in the <a href="#incidents">incident log</a> so the next person starts further along.</p>`;
  }

  nodeEls.forEach(g => {
    g.addEventListener('click', () => { triageSel.value = ''; triageCard.hidden = true; select(g.dataset.id, true); });
    g.addEventListener('keydown', ev => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); triageSel.value = ''; triageCard.hidden = true; select(g.dataset.id, true); } });
  });
  triageSel.addEventListener('change', () => triage(triageSel.value));
  document.getElementById('clear').addEventListener('click', () => { triageSel.value = ''; triage(''); svg.classList.remove('focus'); document.getElementById('find').value = ''; });
  document.getElementById('planned').addEventListener('change', ev => svg.classList.toggle('hide-planned', !ev.target.checked));
  document.getElementById('fit').addEventListener('change', ev => svg.classList.toggle('fit', ev.target.checked));

  // find
  const find = document.getElementById('find');
  function doFind() {
    const q = find.value.trim().toLowerCase(); if (!q) return;
    const L = n => n.label.toLowerCase(), I = n => n.id.toLowerCase();
    const hit = MODEL.nodes.find(n => I(n) === q) || MODEL.nodes.find(n => L(n) === q) || MODEL.nodes.find(n => I(n).includes(q)) || MODEL.nodes.find(n => L(n).includes(q)) || MODEL.nodes.find(n => n.sub.toLowerCase().includes(q));
    if (hit) { triageSel.value = ''; triageCard.hidden = true; select(hit.id, true); }
  }
  find.addEventListener('change', doFind); find.addEventListener('keydown', ev => { if (ev.key === 'Enter') { ev.preventDefault(); doFind(); } });

  // filters
  const filters = { dom: new Set(MODEL.lanes.map(l => l[0])), cx: new Set(Object.keys(MODEL.cx)), edge: new Set(['flow', 'data', 'gate', 'planned']) };
  function applyFilters() {
    nodeEls.forEach(g => { const n = nodes[g.dataset.id]; g.classList.toggle('dim-f', !(filters.dom.has(n.lane) && filters.cx.has(n.cx))); });
    edgeEls.forEach(e => { const kind = [...e.classList].find(c => c.startsWith('e-')).slice(2); const a = nodes[e.dataset.a], b = nodes[e.dataset.b];
      const vis = filters.edge.has(kind) && filters.dom.has(a.lane) && filters.dom.has(b.lane) && filters.cx.has(a.cx) && filters.cx.has(b.cx); e.classList.toggle('dim-f', !vis); });
  }
  document.querySelectorAll('.fchip').forEach(b => b.addEventListener('click', () => {
    const on = b.getAttribute('aria-pressed') !== 'true'; b.setAttribute('aria-pressed', on ? 'true' : 'false');
    const key = b.dataset.dom ? 'dom' : b.dataset.cx ? 'cx' : 'edge'; const val = b.dataset.dom || b.dataset.cx || b.dataset.edge;
    if (on) filters[key].add(val); else filters[key].delete(val); applyFilters();
  }));

  // hash routing
  function fromHash() {
    const h = (location.hash || '').slice(1);
    if (nodes[h]) { select(h, false); return true; }
    const sym = MODEL.symptoms.find(x => x.id === h); if (sym) { triageSel.value = h; triage(h); return true; }
    return false;
  }
  window.addEventListener('hashchange', fromHash);
  if (!fromHash()) select('__DEFAULT__', false);

  // ---------- incident log (shared store)
  const incLive = document.getElementById('inc-live'), incList = document.getElementById('inc-list'), form = document.getElementById('inc-form'), note = document.getElementById('inc-note');
  function renderIncidents() {
    if (!incidents.length) { incList.innerHTML = '<p class="notice">No incidents logged yet.</p>'; return; }
    const sorted = [...incidents].sort((a, b) => (a.status === b.status ? (b.date || '').localeCompare(a.date || '') : (a.status === 'open' ? -1 : 1)));
    incList.innerHTML = sorted.map(i => `<div class="inc ${i.status === 'resolved' ? 'resolved' : ''}" data-id="${esc(i.id)}"><h5>${esc(i.title)}</h5>
      <p class="m">${esc(i.date)} · ${i.symptom ? `<a href="#${esc(i.symptom)}">${esc(i.symptom)}</a> · ` : ''}${(i.nodes || []).map(n => `<a href="#${esc(n)}">${esc(n)}</a>`).join(', ') || 'no systems named'} · ${i.status === 'resolved' ? 'resolved' : 'open'}</p>
      ${i.logs ? `<p><span class="k">Logs:</span> <code>${esc(i.logs)}</code></p>` : ''}${i.cause ? `<p>${esc(i.cause)}</p>` : ''}
      <div class="acts">${canWrite ? `<button type="button" data-toggle="${esc(i.id)}">${i.status === 'resolved' ? 'Reopen' : 'Mark resolved'}</button>` : ''}</div></div>`).join('');
    incList.querySelectorAll('[data-toggle]').forEach(b => b.addEventListener('click', async () => {
      const inc = incidents.find(x => x.id === b.dataset.toggle); if (!inc || !db) return;
      const status = inc.status === 'resolved' ? 'open' : 'resolved';
      try { await db.doc('incidents/' + inc.id).update({ status, updatedAt: new Date().toISOString(), updatedBy: uid || 'unknown' }); }
      catch (e) { note.textContent = 'Could not save (' + (e && e.code) + ').'; }
    }));
  }
  form.addEventListener('submit', async ev => {
    ev.preventDefault();
    if (!db || !canWrite) { note.textContent = 'Logging is read-only in this view.'; return; }
    const title = document.getElementById('inc-title').value.trim(); if (!title) return;
    const ids = document.getElementById('inc-nodes').value.split(/[,\s]+/).map(x => x.trim().toUpperCase()).filter(x => nodes[x]);
    const body = { title, symptom: document.getElementById('inc-symptom').value || '', nodes: ids, logs: document.getElementById('inc-logs').value.trim(), cause: document.getElementById('inc-cause').value.trim(),
      status: 'open', date: new Date().toISOString().slice(0, 16).replace('T', ' '), by: uid || 'unknown', createdAt: new Date().toISOString() };
    const id = 'inc-' + Date.now().toString(36);
    try { await db.doc('incidents/' + id).set(body); form.reset(); note.textContent = 'Logged.'; setTimeout(() => note.textContent = '', 2500); }
    catch (e) { note.textContent = 'Could not save (' + (e && e.code) + ').'; }
  });
  (async () => {
    db = await claude.use('db'); const user = await claude.use('user');
    if (!db) { incLive.textContent = 'The shared log is unavailable in this view; the model and triage index above are complete without it.'; return; }
    uid = user ? await user.id() : null; const w = user ? await user.can('data.write') : null; canWrite = w !== false;
    incLive.innerHTML = canWrite ? '<b>Live.</b> Incidents you log here are shared with everyone who opens this page.' : 'Live, read-only in this view.';
    db.collection('incidents').onSnapshot(snap => { incidents = snap.docs.map(d => Object.assign({ id: d.id }, d.data())); renderIncidents(); const sel = svg.querySelector('.node.selected'); if (sel) renderPanel(nodes[sel.dataset.id]); },
      e => { incLive.textContent = 'Shared log unavailable (' + (e && e.code) + ').'; });
  })();
})();
"""

PAGE = f"""<title>iParty System Reference</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,500;12..96,700;12..96,800&family=Literata:ital,opsz,wght@0,7..72,400;0,7..72,600;1,7..72,400&family=IBM+Plex+Mono:wght@400;500;700&display=swap">
<style>{CSS}</style>
<div class="wrap">
  <header class="masthead">
    <div>
      <p class="eyebrow">iParty · system reference · living-pass @ 21355aa · 21 October 2026</p>
      <h1>iParty System Reference: <em>where to touch, what to check</em></h1>
      <p class="sub">Every system that stands between a host's sentence and a party that happened, color-coded by domain, marked built or planned by sprint, badged by customer-experience impact, with its validation methods, the inspections that cross-check it, and — when it breaks — the files to touch and the logs to read. Select a system in the diagram, or pick a symptom to light up the path.</p>
    </div>
    <div class="stats"><span><b>{len(M.NODES)}</b>systems</span><span><b>{built}</b>built</span><span><b>{planned}</b>planned S0–S6</span><span><b>{len(M.INSPECTIONS)}</b>cross-inspections</span><span><b>{len(M.SYMPTOMS)}</b>triage paths</span></div>
  </header>

  <section class="how">
    <p><strong>Lanes</strong> run from the end user at the top to the quality gates at the bottom; a request flows downward through the surfaces, the gateway, the engine and the verifier to the catalog, and the ledgers and gates sit beneath everything.</p>
    <p><strong>Color</strong> is the domain (lane). <strong>Solid</strong> borders are built and on GitHub; <strong>dashed</strong> borders are planned, labelled with their sprint. The <strong>badge</strong> is the customer-experience impact class: C1 can harm a guest or charge the wrong amount; C2 breaks a promise; C3 makes the party bland or slow; C4 the host never sees.</p>
    <p><strong>Validation</strong> uses the five NASA methods — Test, Analysis, Inspection, Demonstration, Monitoring — each tied to the real test file, script or endpoint. <strong>Cross-performance inspections</strong> are pairs of systems that check each other (X-01…X-16), with a method, a cadence and a pass threshold.</p>
    <p><strong>If it breaks</strong>: pick the symptom in the toolbar. The path lights up, the checks come in order, and every check names a file to touch or a log to read. Deep links work: <code>#ENG-TTL</code>, <code>#T-02</code>, <code>#X-07</code>.</p>
  </section>

  <div class="legend"><span class="k">Domain</span>{dom_legend}</div>
  <div class="legend"><span class="k">Status</span><span class="lg"><i class="lg-box"></i>built</span><span class="lg"><i class="lg-box planned"></i>planned (sprint on the node)</span>
    <span class="k">Edges</span><span class="lg"><i class="lg-line"></i>request flow</span><span class="lg"><i class="lg-line data"></i>data read/write</span><span class="lg"><i class="lg-line gate"></i>verification</span><span class="lg"><i class="lg-line dotted"></i>planned</span></div>
  <div class="legend"><span class="k">CX impact</span>{cx_legend}</div>
  <div class="legend"><span class="k">Methods</span>{method_legend}</div>

  <div class="toolbar">
    <label for="symptom">If it breaks:</label>
    <select id="symptom"><option value="">Pick a symptom…</option>{symptom_options}</select>
    <label for="find">Find:</label>
    <input type="search" id="find" list="node-list" placeholder="ENG-TTL, verifier, Stripe…" autocomplete="off">
    <datalist id="node-list">{node_options}</datalist>
    <button id="clear" type="button">Clear</button>
    <label><input type="checkbox" id="planned" checked> planned systems</label>
    <label><input type="checkbox" id="fit"> fit to width</label>
  </div>
  <div class="toolbar filters" aria-label="Filters">
    <span class="k">Lanes</span>{dom_filters}
    <span class="k">CX</span>{cx_filters}
    <span class="k">Edges</span>{edge_filters}
  </div>

  <div class="diagram">{SVG}</div>

  <div class="after">
    <div class="panel" id="panel">{render_panel(NODES[DEFAULT])}</div>
    <div class="triage-card" id="triage" hidden></div>
  </div>

  <h2 id="register">System register</h2>
  <p class="sub">Every system, with its validation methods, the telemetry to read and the files to touch. Click an ID to select it in the diagram.</p>
  {register_table()}

  <h2 id="inspections">Cross-performance inspection matrix</h2>
  <p class="sub">Pairs of systems that check each other. A built inspection runs today; a planned one lands with the sprint shown.</p>
  {inspection_table()}

  <h2 id="triage-index">Triage index</h2>
  <p class="sub">From symptom to path to ordered checks. When an incident is not here, add it: the register is only as good as the last incident it absorbed.</p>
  {triage_table()}

  <h2 id="incidents">Incident log</h2>
  <p class="sub">Shared with everyone who opens this page. Log what broke, which systems you touched and which logs explained it; open incidents stay at the top. Claude reads this log to update the model and the triage index.</p>
  <p class="notice" id="inc-live">Connecting to the shared log…</p>
  <form id="inc-form" class="inc-form" autocomplete="off">
    <div class="row"><label for="inc-title">What happened</label><input type="text" id="inc-title" required maxlength="140" placeholder="503 on /plan for 10 minutes after deploy"></div>
    <div class="row"><label for="inc-symptom">Closest symptom</label><select id="inc-symptom"><option value="">none of the listed</option>{symptom_options}</select></div>
    <div class="row"><label for="inc-nodes">Systems touched</label><input type="text" id="inc-nodes" list="node-list" placeholder="ENG-TTL, EXT-ANTHROPIC (comma-separated ids)"></div>
    <div class="row"><label for="inc-logs">Logs that explained it</label><input type="text" id="inc-logs" maxlength="300" placeholder="iparty.ttl 'circuit OPEN'; /metrics failures=5"></div>
    <div class="row"><label for="inc-cause">Root cause and fix</label><textarea id="inc-cause" maxlength="1000" placeholder="Expired API key after rotation; added a startup check."></textarea></div>
    <div class="row actions"><button type="submit" id="inc-save">Log incident</button><span class="notice" id="inc-note"></span></div>
  </form>
  <div id="inc-list" class="inc-list"><p class="notice">No incidents logged yet.</p></div>
</div>
<script>{JS.replace("__MODEL__", MODEL_JSON).replace("__DEFAULT__", DEFAULT)}</script>
"""
OUT_HTML.write_text(PAGE, encoding="utf-8")
OUT_JSON.write_text(MODEL_JSON, encoding="utf-8")

# ------------------------------------------------------------------ markdown register (repo + project)
md = ["# iParty system reference", "",
      "*Generated from `docs/architecture.json` (source: the system model). Interactive version: the \"iParty System Reference\" artifact. Branch `living-pass` @ 21355aa, 21 October 2026.*", "",
      "How to read it: lanes run from the end user to the quality gates; status is built or planned by sprint; CX impact classes are "
      + "; ".join(f"**{k}** {v[0]} ({v[1]})" for k, v in M.CX.items()) + ". Validation methods: " + "; ".join(f"**{k}** {v}" for k, v in M.METHODS.items()) + ".", ""]
for lid, lname, ldesc in M.LANES:
    md += [f"## {lname}", "", f"*{ldesc}*", ""]
    for n in [x for x in M.NODES if x["lane"] == lid]:
        md += [f"### {n['id']} · {n['label']} — `{n['sub']}`", "",
               f"**Status:** {M.STATUS[n['status']]} · **CX impact:** {n['cx']} {M.CX[n['cx']][0]}", "",
               f"**Purpose.** {n['purpose']}", "",
               "**Interfaces.** " + " · ".join(n["interfaces"]), "",
               "**Validation.** " + " · ".join(f"[{m}] {t}" for m, t in n["validation"]), "",
               "**Cross-inspections.** " + " · ".join(n["inspections"] + [f"{x['id']} ({x['a']} ⟂ {x['b']})" for x in inspections_for(n["id"])]), "",
               "**Telemetry and logs.** " + " · ".join(f"`{t}`" for t in n["telemetry"]), ""]
        for f in n["failures"]:
            md += [f"**If it breaks — {f['symptom']}.** Touch: " + ", ".join(f"`{t}`" for t in f["touch"]) + ". Logs: " + ", ".join(f"`{l}`" for l in f["logs"]) + ". Checks: " + " ".join(f"({i + 1}) {c}" for i, c in enumerate(f["checks"])), ""]
md += ["## Cross-performance inspection matrix", "", "| ID | A ⟂ B | What | Method | Frequency | Pass threshold | Where | Status |", "|---|---|---|---|---|---|---|---|"]
for x in M.INSPECTIONS:
    md.append(f"| {x['id']} | {x['a']} ⟂ {x['b']} | {x['what']} | {x['method']} | {x['freq']} | {x['threshold']} | `{x['where']}` | {x['status']} |")
md += ["", "## Triage index", ""]
for s in M.SYMPTOMS:
    md += [f"### {s['id']} · {s['title']} ({s['cx']})", "", "Path: " + " → ".join(s["nodes"]), ""] + [f"{i + 1}. {st}" for i, st in enumerate(s["steps"])] + ["", "Touch: " + ", ".join(f"`{t}`" for t in s["touch"]), ""]
OUT_MD.write_text("\n".join(md), encoding="utf-8")
print("html", len(PAGE) // 1024, "KB;", len(M.NODES), "nodes;", len(M.EDGES), "edges;", WIDTH, "x", HEIGHT)
