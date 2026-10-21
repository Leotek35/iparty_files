"""Road to YC — Sprint 1 (Mon 26 Oct – Mon 2 Nov 2026) and the application evidence checklist.

The YC Winter 2027 on-time deadline is Monday 2 November 2026, 8 pm PT. Submission is planned for Sunday 1 November
night; Monday is the buffer. Sprint 0 (s0_model.py) runs Wed 21 – Sun 25 Oct unchanged; this sprint turns its
instrumented engine into a deployed, end-to-end, evidenced product for the application.
"""

DEADLINE = dict(label="YC Winter 2027 on-time deadline", when="Mon 2 Nov 2026, 8:00 pm PT", submit="Sun 1 Nov 2026, evening",
                freeze="Thu 29 Oct 2026, 22:00 — demo build frozen; fixes only after", source="https://www.ycombinator.com/apply")

SPRINT = dict(
    id="S1", name="Sprint 1 · Road to YC", start="2026-10-26", end="2026-11-02",
    goal="A deployed product a YC partner can click through end to end (request → three verified concepts → Living Pass → RSVP repair → "
         "Book it with a test checkout → dasher console), benchmark numbers against raw frontier models with error bars, a real party run "
         "by the founders as dashers on Halloween with an outcome record, signed supply, and an application whose every number reproduces from the repo.",
    columns=[("backlog", "Backlog"), ("ready", "Ready"), ("doing", "In progress"), ("review", "In review · gate"), ("done", "Done")],
    wip={"doing": 5},
    gate="Everything in the Sprint 0 gate, plus: the deployed URL passes the UI matrix and validate_live before the freeze; no feature merges after Thu 29 Oct 22:00; "
         "every number in the application is produced by a script in the repo from the pinned demo environment",
)

DAYS = ["Mon 26", "Tue 27", "Wed 28", "Thu 29", "Fri 30", "Sat 31", "Sun 1", "Mon 2"]

CARDS = [
    # ------------------------------------------------------------------ C · Product (go-live and the end-to-end path)
    dict(id="C1-01", lane="C", sprint="S1", title="Go live on the Anthropic backend", owner="Agent C + Leo", est=6, day="Mon 26", prio="P0", status="ready", deps=["C0-04"],
         spec="Deploy the current build to the hosting blueprint (Render or equivalent) with LLM_BACKEND=anthropic, ANTHROPIC_MODEL=claude-haiku-5-5, prompt caching on, METRICS_TOKEN set, PUBLIC_BASE_URL set to the public domain, EVENTS_PATH/PLANS_DB_PATH on a persistent disk, CANDIDATE_LOG_PATH on the same disk; an automatic fallback to LLM_BACKEND=mock when the provider errors (breaker open → composer path) so the demo never shows a 503.",
         tests=["/health and one smoke plan succeed on the public URL after deploy (script scripts/smoke_live.sh)", "validate_live on 20 briefs against the public URL: ≥ 95% verified, p95 latency < 20 s, cost per plan logged",
                "Breaker-open simulation (bad key) returns a verified composer plan, not a 503", "Data survives a redeploy (create a Living Pass, redeploy, read it back)"],
         qa=["Full UI matrix (100 profiles) against the public URL on Tue 27", "A stranger (advisor) completes the host journey on a phone without help"],
         dod=["Public URL in the decision log and in the application's product link", "Runbook: how to roll back, how to flip to mock, where the logs are (docs/ARCHITECTURE.md EXT-HOST)"],
         refs=["Sprint plan P0 go-live; S0 digest §7 (Haiku 5.5 pricing and caching)"], telemetry=["host logs", "/metrics", "candidate log on disk"]),
    dict(id="C1-02", lane="C", sprint="S1", title="Book it: bundle price + Stripe Checkout (test mode)", owner="Agent C", est=8, day="Tue 27", prio="P0", status="ready", deps=["C1-01", "D0-02"],
         spec="A 'Book this party' action on the pass: bundle price = verified plan total + dasher labour envelope (hours × rate from config) + replacement allowance (5%) + margin (config, default 20%); a bookings record (extends the bookings ledger) linked to the plan id; Stripe Checkout session in test mode with the bundle as one line item and iParty as the seller; webhook handler marks the booking paid; alcohol items excluded from bookable plans. Live keys never set before Sprint 6.",
         tests=["Price function: parts sum to total; margin ≥ floor; a plan with alcohol is not bookable (422 with copy)", "Checkout session created with the right amount (Stripe test fixtures); webhook with a bad signature rejected",
                "Booking appears in /bookings/summary and on the pass as 'booked (test)'", "Playwright: host clicks Book it → Stripe test page → returns to the pass marked booked"],
         qa=["Test-mode card 4242 flow walked through by Leo on the public URL", "Copy review: the price breakdown is readable by a parent"],
         dod=["Merged behind the gate", "Price parts logged to the bookings ledger", "Refund/cancellation policy page linked from the checkout"],
         refs=["Stripe Checkout + Connect separate charges and transfers (S0 ops digest §2)", "Take-rate benchmarks: Instacart 7.2% of GTV, DoorDash 13.5% net revenue margin; curated bundle 20–30% blended"], telemetry=["bookings.jsonl with price parts", "Stripe test dashboard"]),
    dict(id="C1-03", lane="C", sprint="S1", title="Dasher console v0", owner="Agent C", est=6, day="Wed 28", prio="P0", status="ready", deps=["C1-02"],
         spec="/dasher?b=<booking>&t=<token>: a mobile web page for the person running the party: the job (date, window, address placeholder), the shopping list grouped by vendor/store with quantities, the run of show with timings, a replacement note per slot, check-off per item, an incident button (writes an incident to the outcome log), and the post-party report form (on time, items replaced, incidents, host rating). Token-gated; no host PII beyond first name.",
         tests=["Console renders from a booking fixture; items check off and persist", "Incident and report write to the outcome log (new JSONL ledger) with the booking id",
                "axe 0 serious on phone width", "Token missing or wrong → 403"],
         qa=["Founders run the Halloween party from this console (D1-03)", "Report form takes < 2 minutes to fill on a phone"],
         dod=["Merged", "Console link shown to the host after booking (test)", "Outcome ledger documented in docs/ARCHITECTURE.md DAT-OUTCOME"],
         refs=["Sprint plan S4 dasher console; Stitch Fix label flywheel (dasher reports as training data)"], telemetry=["outcome ledger"]),
    dict(id="C1-04", lane="C", sprint="S1", title="Landing page + waitlist", owner="Agent C + Leo", est=4, day="Mon 26", prio="P1", status="ready", deps=[],
         spec="Public landing page on the same host: the one-sentence promise, the three-concept demo as a GIF, the six things incumbents cannot do, a waitlist form (email + metro + 'what are you planning') writing to a waitlist ledger with the same hardening as events; a counter for the application. Leo posts it in three parent/community groups on Tue 27.",
         tests=["Form validates and rate-limits like /events; summary endpoint exposes counts only", "UI matrix smoke on the landing page; axe 0 serious"],
         qa=["Copy review; the demo GIF shows real product output"],
         dod=["Live by Tue 27 morning", "Count visible in the daily standup"],
         refs=["YC application asks how far along you are and whether people want this — a waitlist number is cheap evidence"], telemetry=["waitlist.jsonl"]),

    # ------------------------------------------------------------------ A · Engine (hardening only — no new features after Thu)
    dict(id="A1-01", lane="A", sprint="S1", title="Three concepts in the API and the live path", owner="Agent A", est=5, day="Mon 26", prio="P0", status="ready", deps=["A0-03", "C0-01"],
         spec="POST /plan?variants=3 returns `alternatives` from the DPP pick on both backends: mock (composer variants) and live (Verbalized Sampling pool + composer seeds), always ≥ 1 and at most 3, each verified; the picker falls back gracefully to one card when the pool is thin. Difficulty-adaptive N: simple briefs (≤ 20 guests, no dietary) use N=2; complex use N=4.",
         tests=["130 profiles: alternatives count ≥ 2 in ≥ 95% on the mock path; all verified", "Live fixture: pool of 5 → 3 distinct cells", "N policy covered by unit tests; telemetry shows candidates_generated"],
         qa=["PartyBench diversity page shows the DPP determinant distribution before and after"],
         dod=["Merged", "README API section updated"],
         refs=["Snell et al. compute-optimal scaling: difficulty-adaptive allocation"], telemetry=["candidate log selected_by.dpp", "pattern_log"]),
    dict(id="A1-02", lane="A", sprint="S1", title="Hardening pass on the demo requests", owner="Agent A", est=4, day="Thu 29", prio="P0", status="ready", deps=["A1-01"],
         spec="Run the demo script's five requests and the Halloween party request 20 times each on the live path; fix any flake (parse failures, slow candidates, cliché concepts) in the composer or prompts; pin the demo environment (commit, catalog_sha256, model) in docs/sprints/DEMO_ENV.md. No feature work.",
         tests=["100/100 runs of the six requests verified; p95 < 15 s; no identical concept titles across the three shown", "Replay of the runs reproduces verdicts"],
         qa=["Leo reads all 18 concepts for the three demo requests and signs off"],
         dod=["Demo environment pinned", "Freeze declared at 22:00"],
         refs=["Sprint plan S5 freeze"], telemetry=["candidate log for the demo requests"]),

    # ------------------------------------------------------------------ B · Data & learning (the numbers)
    dict(id="B1-01", lane="B", sprint="S1", title="PartyBench v1 with frontier baselines", owner="Agent B", est=8, day="Mon 26", prio="P0", status="ready", deps=["B0-03", "B0-04"],
         spec="100 cases (stratified from the 230) run three ways: iParty live path, iParty mock path, and raw frontier models with the catalog slice in context (OpenAI, Gemini, Claude — three runs each, ≈ $15 total); metrics: delivery, hard micro/macro, final pass, first-try pass, cost per plan, p50/p95 latency; Miller paired-difference SEs with 95% CIs; report with the environment hash. Numbers go into the application only from this report.",
         tests=["Baseline runner handles refusals, malformed JSON and timeouts as failed deliveries (never crashes)", "Report shows CIs; paired SE between the two iParty paths computed on the same cases",
                "Total external spend ≤ $20 (usage logged per call)"],
         qa=["Leo sanity-reads 10 baseline plans: are failures real (hallucinated SKUs, budget) and not harness bugs?"],
         dod=["bench/reports/2026-10-28.html archived and linked from the decision log", "One sentence of findings for the application"],
         refs=["TravelPlanner metrics; Miller error bars; S0 digest §9 (a 100-case bench detects ~15-point gaps — report CIs, do not overclaim)"], telemetry=["bench rows with model_id and cost"]),
    dict(id="B1-02", lane="B", sprint="S1", title="PartyBench public page", owner="Agent B", est=4, day="Wed 28", prio="P1", status="ready", deps=["B1-01"],
         spec="A static page on the public host (/bench) rendering the latest report: headline numbers with CIs, the method (what is verified, how baselines were run), the environment hash, a link to the repo. No live queries.",
         tests=["Page builds from the report JSON; numbers match the report; axe 0 serious"],
         qa=["An outsider can explain the headline number after reading the page for one minute"],
         dod=["Linked from the landing page and the application"],
         refs=["Sprint plan M2"], telemetry=["—"]),
    dict(id="B1-03", lane="B", sprint="S1", title="Outcome ledger + Halloween case in the bench", owner="Agent B", est=3, day="Thu 29", prio="P1", status="ready", deps=["C1-03"],
         spec="The dasher console's reports land in data/outcomes.jsonl; the Halloween party request is a PartyBench case with its expected outcome; after the party, the outcome row (on time, replacements, incidents, host rating, guest count) is attached to the report as the first entry of the outcome track.",
         tests=["Outcome schema validated; summary endpoint exposes counts only", "The Halloween case runs in the bench with the pinned environment"],
         qa=["Outcome row filled within 2 hours of the party"],
         dod=["Outcome track visible on /bench with n=1, honestly labelled"],
         refs=["Sprint plan S4 outcome logging"], telemetry=["outcomes.jsonl"]),

    # ------------------------------------------------------------------ D · Marketplace ops (supply and the proof party)
    dict(id="D1-01", lane="D", sprint="S1", title="Halloween proof party: host, request, plan", owner="Leo", est=3, day="Mon 26", prio="P0", status="ready", deps=["D0-06"],
         spec="A real party on Sat 31 Oct (friends, family or cohort; 8–20 guests; at least one dietary need), the request entered on the public URL, the three concepts shown to the host, the pick recorded, the Living Pass sent to guests for RSVPs, Book it in test mode. Founders are the dashers.",
         tests=["Plan exists on the public URL with a Living Pass and ≥ 5 RSVPs by Thu 29", "Booking (test) recorded; dasher console link in hand"],
         qa=["The plan's shopping list is buyable at retail in the metro (checked Tue 27)"],
         dod=["Party confirmed in the decision log with host, address, window"],
         refs=["Sprint plan S4 pilots, pulled forward for the application"], telemetry=["bookings ledger; Living Pass events"]),
    dict(id="D1-02", lane="D", sprint="S1", title="Ten confirmed vendor rows", owner="Leo", est=6, day="Tue 27", prio="P0", status="ready", deps=["D0-04"],
         spec="Ten vendors across venue, caterer (permitted facility), cake, supplies/rentals, entertainer with phone-confirmed price, minimum, lead time, pickup window and a big-9 allergen declaration; rows in data/vendor_catalog.jsonl with status approved; two of them say yes to being named in the application.",
         tests=["load_vendor_items loads all ten; make catalog-check unaffected", "Each row has a call note with date and contact"],
         qa=["A plan composed on the public URL includes at least one vendor row item"],
         dod=["Vendor count and two names in the application"],
         refs=["S0 ops digest §4 (fields, caterer terms)"], telemetry=["vendor call notes"]),
    dict(id="D1-03", lane="D", sprint="S1", title="Run the Halloween party as dashers", owner="Leo + co-founder", est=8, day="Sat 31", prio="P0", status="ready", deps=["D1-01", "C1-03"],
         spec="Shop from the console's list (receipts kept), set up by the window, run the run of show, strike; log replacements and incidents as they happen; fill the report within 2 hours; collect host rating and 3–5 guest NPS answers; 20+ photos and 3 short clips with permission from the host (faces of children only with written consent, otherwise none).",
         tests=["Outcome row complete; receipts total vs plan total recorded; photos in the application folder"],
         qa=["Honesty check: what went wrong is written down before what went right"],
         dod=["Outcome in the bench; two photos and one number (on time, replacements) in the application"],
         refs=["Generative-design lesson: fulfilment is the bottleneck; show it works"], telemetry=["outcomes.jsonl"]),
    dict(id="D1-04", lane="D", sprint="S1", title="Dasher pipeline: two candidates screened", owner="Leo", est=3, day="Wed 28", prio="P1", status="ready", deps=["D0-05", "D0-03"],
         spec="Two dasher candidates interviewed, agreed to the 14 Nov dry run, consented to a Checkr check (not necessarily run before 2 Nov); the job description and pay in writing.",
         tests=["Two signed interest forms; FCRA disclosure delivered"],
         qa=["Pay beats Taskrabbit party-setup rates in writing"],
         dod=["Two names (first names) and the pay structure in the application"],
         refs=["S0 ops digest §3"], telemetry=["pipeline sheet"]),
    dict(id="D1-05", lane="D", sprint="S1", title="Insurance quotes and Stripe activation closed out", owner="Leo", est=2, day="Thu 29", prio="P1", status="ready", deps=["D0-01", "D0-02"],
         spec="Three quotes compared in the decision log with a bind date in Sprint 6; Stripe activation complete or pending with no open questions; Checkr account open.",
         tests=["Decision log entries exist with numbers"],
         qa=["No open underwriting questions"],
         dod=["One line in the application's 'how far along' answer"],
         refs=["S0 ops digest §1–2"], telemetry=["decision log"]),

    # ------------------------------------------------------------------ E · Story (the application itself)
    dict(id="E1-01", lane="E", sprint="S1", title="Application answers v1 → v3", owner="Leo + agent E", est=8, day="Mon 26", prio="P0", status="ready", deps=["E0-01"],
         spec="v1 Mon 26 from the memo and the sprint plan (every question drafted; numbers marked TBD); v2 Wed 28 with PartyBench, waitlist, vendor and dasher numbers; v3 Fri 30 final text reviewed by two outside readers; every number traces to a report or a ledger (list the source next to each in the working doc).",
         tests=["Working doc has a source for every number", "Two outside readers' notes addressed"],
         qa=["Read aloud once; cut anything a partner would not understand in one pass"],
         dod=["Pasted into the YC form by Sat 31 with only the party outcome and video pending"],
         refs=["ycombinator.com/apply; the application's 'how far along', 'why this idea', 'how do you make money', competitors (S0 ops digest §5)"], telemetry=["—"]),
    dict(id="E1-02", lane="E", sprint="S1", title="Founder video (1 minute)", owner="Founders", est=3, day="Thu 29", prio="P0", status="ready", deps=[],
         spec="Per YC's instructions: one minute, all founders on screen, founders talking only, no demo, no slides, no script read aloud; three takes on Sat 24 (practice), final take Thu 29 after the freeze; good light, phone at eye level, quiet room; file named and uploaded Sun 1.",
         tests=["Final file ≤ 60 s; all founders visible; audio clear on a phone speaker"],
         qa=["One outsider says what the company does after watching once"],
         dod=["Uploaded"],
         refs=["ycombinator.com/video"], telemetry=["—"]),
    dict(id="E1-03", lane="E", sprint="S1", title="Product demo video (2–3 minutes) and product link", owner="Leo + agent E", est=5, day="Sat 31", prio="P0", status="ready", deps=["A1-02", "C1-02", "C1-03", "D1-03"],
         spec="Screen recording on the pinned demo environment: request → three concepts → infeasibility explanation → Living Pass RSVP repair → Book it (test) → dasher console; then 20 seconds of the Halloween party footage and the outcome numbers; then the /bench page. Recorded Sat 31 night or Sun 1 morning; edited Sun 1; the product link field gets the public URL plus the video link.",
         tests=["≤ 3 minutes; every number on screen matches the pinned report; the public URL in the video is the live one"],
         qa=["An outsider follows it without narration"],
         dod=["Uploaded; link in the form"],
         refs=["Sprint plan §5 demo script"], telemetry=["—"]),
    dict(id="E1-04", lane="E", sprint="S1", title="Submit (Sun 1 Nov evening) and the Monday buffer", owner="Leo", est=2, day="Sun 1", prio="P0", status="ready", deps=["E1-01", "E1-02", "E1-03"],
         spec="Final read-through against the evidence checklist; submit Sunday evening; screenshot the confirmation; Monday 2 Nov is reserved for fixing anything the form rejects — nothing else is scheduled before 8 pm PT.",
         tests=["Confirmation screenshot in the decision log before Mon 2 Nov 8 pm PT"],
         qa=["Checklist all green"],
         dod=["Submitted"],
         refs=["Deadline: Mon 2 Nov 2026, 8 pm PT (ycombinator.com/apply)"], telemetry=["—"]),
    dict(id="E1-05", lane="E", sprint="S1", title="Outside readers and the YC alumni check", owner="Leo", est=2, day="Wed 28", prio="P1", status="ready", deps=[],
         spec="Two outside readers (one YC alum if reachable) read answers v2 on Wed 28 and the demo video on Sun 1; their notes go into v3 and the final cut.",
         tests=["Notes received and logged"],
         qa=["—"],
         dod=["Addressed or consciously declined in the decision log"],
         refs=["—"], telemetry=["—"]),
]

# Sprint 1 exit gate (shared QA checklist, collection 'qa', ids Q1-xx)
QA_GATE = [
    dict(id="Q1-01", text="Public URL up on the Anthropic backend with mock fallback; UI matrix and validate_live green against it before the freeze", owner="Agent C"),
    dict(id="Q1-02", text="Three verified concepts on both backends in ≥ 95% of the 130 profiles; hardening runs 100/100 on the demo requests", owner="Agent A"),
    dict(id="Q1-03", text="PartyBench v1 report with frontier baselines and CIs archived; /bench page live; spend ≤ $20", owner="Agent B"),
    dict(id="Q1-04", text="Book it (test) and the dasher console work end to end on the public URL; alcohol excluded", owner="Agent C"),
    dict(id="Q1-05", text="Halloween party run from the console; outcome row, receipts and photos in hand within 2 hours", owner="Leo"),
    dict(id="Q1-06", text="Ten confirmed vendor rows loaded; two dasher candidates screened; insurance quotes and Stripe activation closed out", owner="Leo"),
    dict(id="Q1-07", text="Waitlist live since Tue 27 with the count in the standup", owner="Leo"),
    dict(id="Q1-08", text="Application v3 with a source for every number; two outside readers' notes addressed", owner="Leo"),
    dict(id="Q1-09", text="Founder video final take uploaded; product demo video ≤ 3 minutes uploaded; product link set", owner="Founders"),
    dict(id="Q1-10", text="Freeze respected: no feature merges after Thu 29 Oct 22:00; demo environment pinned in docs/sprints/DEMO_ENV.md", owner="Leo"),
    dict(id="Q1-11", text="Submitted Sun 1 Nov evening; confirmation screenshot logged; Monday reserved for the buffer", owner="Leo"),
]

# The application evidence checklist (shared, collection 'yc'): what the form asks → the evidence we bring → where it comes from
YC_CHECKLIST = [
    dict(id="Y-01", ask="Company one-liner and what it does (short)", evidence="The verified, fulfilled party bundle: one sentence from the memo's six-things thesis", source="strategy memo §3; E1-01", owner="Leo"),
    dict(id="Y-02", ask="Founders, roles, how long you have worked together", evidence="Bios; who built what in the repo (commit history)", source="git log; E1-01", owner="Founders"),
    dict(id="Y-03", ask="Founder video (1 minute, founders only)", evidence="Final take after the freeze", source="E1-02", owner="Founders"),
    dict(id="Y-04", ask="Product link / demo", evidence="Public URL (live backend) + 2–3 minute demo video", source="C1-01; E1-03", owner="Leo"),
    dict(id="Y-05", ask="How far along are you?", evidence="Deployed product; 601-item catalog; verifier; Living Pass; PartyBench numbers; one real party; ten vendors; two dashers; insurance quotes; Stripe activation", source="B1-01; D1-02; D1-03; D1-04; D1-05", owner="Leo"),
    dict(id="Y-06", ask="Are people using it? Revenue?", evidence="Pre-revenue; the Halloween party booked in test mode; waitlist count; host rating and guest NPS", source="C1-04; D1-03; B1-03", owner="Leo"),
    dict(id="Y-07", ask="Tech stack, including AI tools used to build", evidence="FastAPI/pydantic, deterministic composer + verifier, Claude (Haiku 5.5) with caching, CP-SAT spike, Playwright/axe matrix, PartyBench; built with Claude Code agents under a test gate", source="README; docs/ARCHITECTURE.md", owner="Leo"),
    dict(id="Y-08", ask="Why this idea; how do you know people need it", evidence="The PB&J moment; the 100-profile matrix; the party outcome; the waitlist; incumbents' gaps (OpenAI checkout retreat, Google MoR stance, Instacart Fizz scope)", source="memo §3; D1-03; C1-04", owner="Leo"),
    dict(id="Y-09", ask="Competitors and what you understand that they do not", evidence="Nobody sells a verified, fulfilled bundle; TravelPlanner ladder (solver beats sampling); verifier as reward", source="memo §2–3", owner="Leo"),
    dict(id="Y-10", ask="How will you make money", evidence="Merchant of record for the bundle, 20–30% blended take with ≥ 10% contribution; dasher labour inside the price; one real order P&L from the Halloween party", source="C1-02 price parts; D1-03 receipts", owner="Leo"),
    dict(id="Y-11", ask="Metrics a partner would check", evidence="First-try verified rate vs raw GPT/Gemini/Claude with CIs; cost per plan; p95 latency; on-time and replacement rate (n=1)", source="B1-01; B1-03", owner="Agent B"),
    dict(id="Y-12", ask="Legal entity, equity, prior funding", evidence="As applicable; nothing invented", source="Leo", owner="Leo"),
    dict(id="Y-13", ask="What is next (the plan)", evidence="Nine sprints to Christmas; one metro launch 17 Dec; PartyBench public", source="strategy/sprint-plan-to-launch.md", owner="Leo"),
    dict(id="Y-14", ask="Submission", evidence="Submitted Sun 1 Nov evening; confirmation screenshot", source="E1-04", owner="Leo"),
]

# Day-by-day critical path (Wed 21 Oct → Mon 2 Nov)
DAILY = [
    ("Wed 21 Oct", "S0", "Graded verifier (A0-01), candidate log (B0-01), Verbalized Sampling (C0-01) start; insurance quotes requested, Stripe activation submitted; YC go decided; application answers v0 drafted from the memo; decision log opened."),
    ("Thu 22 Oct", "S0", "Descriptor vector (A0-04), CP-SAT spike (A0-02), replay (B0-02), PartyBench v0 (B0-03), backprompting (C0-02); Checkr account, vendor long-list and form; Halloween host shortlisted; demo storyline."),
    ("Fri 23 Oct", "S0", "DPP pick of three (A0-03), picker (C0-03), Places terms (C0-05), baseline stub (B0-04); Friday demo recorded; dasher job description posted."),
    ("Sat 24 Oct", "S0", "Prompt caching + Haiku 5.5 (C0-04), judge v0 (B0-05); founder video practice takes; application answers v1 outline."),
    ("Sun 25 Oct", "S0", "S0 exit gate; PartyBench v0 report archived; S1 briefs issued; Halloween host confirmed; deploy prep (secrets, disk)."),
    ("Mon 26 Oct", "S1", "Go live (C1-01), three concepts in the API (A1-01), PartyBench v1 baselines start (B1-01), landing + waitlist (C1-04); Halloween request entered and Living Pass sent (D1-01); application v1 complete."),
    ("Tue 27 Oct", "S1", "Book it with test checkout (C1-02); UI matrix against the public URL; waitlist posted in three groups; ten vendor calls (D1-02); shopping list checked against retail."),
    ("Wed 28 Oct", "S1", "Dasher console v0 (C1-03); /bench page (B1-02); application v2 with numbers; outside readers; two dasher candidates screened (D1-04)."),
    ("Thu 29 Oct", "S1", "Hardening runs and the demo environment pinned (A1-02); outcome ledger (B1-03); insurance and Stripe closed out (D1-05); founder video final take; FREEZE at 22:00."),
    ("Fri 30 Oct", "S1", "Fixes only; full gate + UI matrix + validate_live on the frozen build; application v3 final text pasted into the form; party shopping from the console."),
    ("Sat 31 Oct", "S1", "Halloween proof party run by the founders as dashers (D1-03); outcome row within 2 hours; demo video recorded at night (E1-03)."),
    ("Sun 1 Nov", "S1", "Edit the demo video; outside readers on the cut; product link set; final checklist; SUBMIT in the evening (E1-04)."),
    ("Mon 2 Nov", "S1", "Buffer only. Deadline 8:00 pm PT. Nothing else scheduled."),
]

CUTS = [
    "CP-SAT core, concept archive, judge calibration and taste weights wait until after 2 Nov (the spike, DPP and Verbalized Sampling carry the demo).",
    "Vendor onboarding stops at ten confirmed rows; no vendor API work; Places compliance fix only.",
    "Insurance is quoted, not bound; Checkr is opened, not run; Stripe stays in test mode.",
    "No new product surfaces beyond Book it, the dasher console and the landing page.",
    "The S0 cards keep their dates; anything in S0 not done by Sun 25 Oct moves to S1 only if the demo needs it, otherwise to Backlog.",
]
