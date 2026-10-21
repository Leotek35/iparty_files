# iParty system reference

*Generated from `docs/architecture.json` (source: the system model). Interactive version: the "iParty System Reference" artifact. Branch `living-pass` @ 21355aa, 21 October 2026.*

How to read it: lanes run from the end user to the quality gates; status is built or planned by sprint; CX impact classes are **C1** Safety & money (A failure can harm a guest or charge the wrong amount: allergens, certifications, age, prices, payment.); **C2** Trust (A failure makes a verified claim false or the product look dishonest: infeasibility answers, Living Pass correctness, telemetry.); **C3** Delight & speed (A failure makes the party bland, repetitive, off-theme or slow.); **C4** Internal (A failure costs the team time or money but the host does not see it directly.). Validation methods: **T** Test — automated tests that must pass; **A** Analysis — property-based, statistical or replay checks; **I** Inspection — schema, staleness and review checks; **D** Demonstration — driving the real product end to end; **M** Monitoring — logs, metrics and ledgers in production.

## End users

*Who the system serves*

### U-HOST · Host — `parent · organizer · buyer`

**Status:** Built (living-pass @ 21355aa) · **CX impact:** C1 Safety & money

**Purpose.** The customer. Types one request and expects a verified, delightful, buyable party in under 20 seconds; later sends the invite and accepts repairs.

**Interfaces.** → UX-HOST (web/index.html) · → UX-RSVP as the invite sender

**Validation.** [D] 100-profile UI matrix drives the host journey the way a person would (scripts/ui_matrix.py) · [D] Pilot parties from Sprint 4: three before 25 Nov, five more by 13 Dec

**Cross-inspections.** Host-visible numbers equal API numbers (UI matrix compares the rendered receipt with /api/v1/plan) · X-11 (DAT-JUDGE ⟂ U-HOST)

**Telemetry and logs.** `data/events.jsonl funnel events (plan_requested, verified, infeasible, feedback answer)` · `bookings.jsonl intents`

**If it breaks — Host abandons at the form or after a 422.** Touch: `web/index.html copy and defaults`, `planning/feasibility.py minimum budget message`. Logs: `events.jsonl: status and budget_band on plan events`, `GET /api/v1/events/summary`. Checks: (1) Is the 422 explaining the minimum feasible budget? (2) Did the UI matrix flag copy or dead ends?

### U-GUEST · Guest — `RSVPs · declares allergies`

**Status:** Built (living-pass @ 21355aa) · **CX impact:** C1 Safety & money

**Purpose.** Confirms attendance and declares dietary needs through the invitation page; every RSVP re-verifies the host's plan.

**Interfaces.** → UX-RSVP (web/rsvp.html)

**Validation.** [T] tests/test_living_pass_api.py RSVP contract · [D] UI matrix living-pass flows (verified / attention / unverifiable states)

**Cross-inspections.** Guest-declared allergens re-enter the verifier through living.build_status — never trusted as free text

**Telemetry and logs.** `events.jsonl rsvp events` · `data/iparty.db guests table`

**If it breaks — Guest RSVP accepted but the host's status does not change.** Touch: `planning/living.py build_status`, `api/living.py submit_rsvp`. Logs: `GET /api/v1/plans/{id}/status`, `data/iparty.db guests rows`. Checks: (1) 429 from LIVING_RSVP_RATE_PER_MIN? (2) guest_key collision (same name twice)?

### U-DASHER · Party dasher — `shops · assembles · runs`

**Status:** Planned · Sprint 4 (16–22 Nov) · **CX impact:** C1 Safety & money

**Purpose.** The gig worker who makes the plan real: shops by vendor, assembles, runs the party, reports outcomes and labels plans (the Stitch Fix flywheel).

**Interfaces.** → UX-DASHER console · → DAT-OUTCOME

**Validation.** [D] Dry run on 14 Nov with the console before any real party · [M] On-time, replacement and incident rates per party

**Cross-inspections.** Dasher QA labels on sampled plans calibrate the judge (Sprint 4+)

**Telemetry and logs.** `outcome log (planned)` · `incident reports (planned)`

**If it breaks — Dasher late or missing items.** Touch: `FUL-AVAIL replacement per slot`, `FUL-JOBS time-window check`. Logs: `outcome log`, `incident log`. Checks: (1) Was availability re-confirmed 48 h before? (2) Was the window feasible in the job model?

### U-VENDOR · Vendor — `caterer · venue · act`

**Status:** Built (living-pass @ 21355aa) · **CX impact:** C2 Trust

**Purpose.** Supplies the items. Leaves a lead through the app (POST /vendors) or is onboarded as an approved row with a quoted price.

**Interfaces.** → API-VEND lead · → CAT-ROWS approved rows

**Validation.** [I] Only rows with status approved and valid allergen keys load (pricing/vendors.py load_vendor_items) · [D] Phone-confirmed price and lead time before a row is approved (Sprint 1+)

**Cross-inspections.** Vendor rows are re-validated against the catalog schema on every load; bad allergen keys are skipped loudly

**Telemetry and logs.** `data/vendor_leads.jsonl` · `GET /api/v1/vendors/summary`

**If it breaks — Vendor item priced or tagged wrong.** Touch: `data/vendor_catalog.jsonl row`, `pricing/vendors.py load_vendor_items`. Logs: `iparty.vendors logger (stdout)`. Checks: (1) price_basis is quote and status approved? (2) allergen keys in the FDA big-9 set?

### U-OPS · Founder · investors — `metrics · PartyBench`

**Status:** Built (living-pass @ 21355aa) · **CX impact:** C4 Internal

**Purpose.** Reads the nightly numbers and the reliability ledger; every number shown outside is generated by a script in the repo.

**Interfaces.** → GET /api/v1/metrics · → UX-BENCH (planned) · → scripts/validate_live.py

**Validation.** [A] Miller (2024) paired-difference error bars on every comparison

**Cross-inspections.** Investor numbers reproduce from a pinned demo environment (`make partybench`, Sprint 0+)

**Telemetry and logs.** `/metrics (METRICS_TOKEN)` · `events/bookings/vendors summaries`

**If it breaks — A slide number cannot be reproduced.** Touch: `scripts/validate_live.py`, `PartyBench harness (planned)`. Logs: `the pinned run's report`. Checks: (1) Which commit, catalog and model produced it?

## Surfaces

*What people touch*

### UX-HOST · Host app — `web/index.html`

**Status:** Built (living-pass @ 21355aa) · **CX impact:** C2 Trust

**Purpose.** Single-page host journey: the request form → the concept-first pass (title, story, moments, menu by course, grouped receipt, reliability ledger) → Make it a Living Pass → booking intent → vendor lead.

**Interfaces.** POST /api/v1/plan · POST /api/v1/plans · GET /api/v1/plans/{id}/status (polling) · POST /api/v1/events · POST /api/v1/bookings · POST /api/v1/vendors · GET /static/themes.json, /static/inspo.json · GET /health

**Validation.** [T] tests/test_frontend_static.py, test_theme_and_booking_ui.py, test_ux_guards.py · [D] tests/ui/test_ui_matrix.py (IPARTY_UI=1) and scripts/ui_matrix.py: 100 profiles, desktop + phone, axe-core 0 serious · [I] CSP forbids unsafe-eval; no inline event handlers

**Cross-inspections.** Rendered receipt total equals plan.total_cost from the API · Every verifier code shown has host-readable copy (test_ux_guards) · X-06 (UX-HOST ⟂ API-PLAN)

**Telemetry and logs.** `browser console` · `events.jsonl (session_id, event, meta: status, has_diet, guests_band, budget_band, answer)`

**If it breaks — Blank page, broken layout or a dead button.** Touch: `web/index.html`. Logs: `browser console`, `uvicorn access log: /static/* 404?`, `GET /health`. Checks: (1) Do /static/themes.json and /static/inspo.json load? (2) Any CSP violation in the console? (3) Run `make ui-test`

**If it breaks — Pass shows a concept that does not match the receipt.** Touch: `web/index.html render of concept_name/story/moments`, `api/living.py _public_pass`. Logs: `response JSON of /api/v1/plan`. Checks: (1) Compare plan.line_items with the rendered groups

### UX-RSVP · Invitation & RSVP — `web/rsvp.html`

**Status:** Built (living-pass @ 21355aa) · **CX impact:** C1 Safety & money

**Purpose.** Public invitation: concept, story, moments; the guest confirms attendance and allergies; never exposes host-only data.

**Interfaces.** GET /api/v1/plans/{id}/rsvp · POST /api/v1/plans/{id}/rsvp · POST /api/v1/events

**Validation.** [T] tests/test_living_pass_api.py invitation and RSVP contracts; privacy of host fields · [D] UI matrix guest flows

**Cross-inspections.** Invitation JSON contains no host token, no cost, no guest list (test_living_pass_api)

**Telemetry and logs.** `events.jsonl rsvp events`

**If it breaks — Invitation 404 or shows the wrong party.** Touch: `api/living.py get_invitation`, `core/store.py get_plan`. Logs: `uvicorn access log`, `data/iparty.db plans`. Checks: (1) plan_id format and existence (2) PUBLIC_BASE_URL set so links are absolute?

### UX-DATA · Theme & inspo data — `themes.json · inspo.json`

**Status:** Built (living-pass @ 21355aa) · **CX impact:** C3 Delight & speed

**Purpose.** Palettes, chips, games by band and inspiration entries that shape the form and the pass; themes.json is also projected into the engine's palettes.json.

**Interfaces.** read by UX-HOST · projected into CAT-JSON palettes.json by scripts/build_catalog.py

**Validation.** [T] tests/test_theme_dataset.py, test_inspo_dataset.py (schema, bands, ids) · [I] make catalog-check fails if palettes.json is stale

**Cross-inspections.** palettes.json ⟂ themes.json: regenerated and diffed by the catalog check

**Telemetry and logs.** `none at runtime`

**If it breaks — Theme chip missing or a palette never matches an item.** Touch: `web/themes.json`, `scripts/catalog_src/supplies.py theme:<id> tags`. Logs: `make catalog-check output`. Checks: (1) Does the palette id exist in both files? (2) python scripts/concept_debug.py explain for the theme

### UX-DASHER · Dasher console — `mobile web`

**Status:** Planned · Sprint 3 (9–15 Nov) · **CX impact:** C1 Safety & money

**Purpose.** Job accept, shopping list grouped by vendor, timings and route, replacement prompts, incident button, post-party report.

**Interfaces.** reads FUL-JOBS · writes DAT-OUTCOME

**Validation.** [D] Dry run 14 Nov; Playwright smoke on the console (Sprint 3)

**Cross-inspections.** Console timings ⟂ FUL-JOBS window feasibility

**Telemetry and logs.** `outcome log (planned)`

**If it breaks — Dasher cannot see the job or the list is wrong.** Touch: `FUL-JOBS`, `console page`. Logs: `outcome log`, `server log`. Checks: (1) Is the booking paid and assigned?

### UX-BENCH · PartyBench page — `public benchmark`

**Status:** Planned · Sprint 2 (2–8 Nov) · **CX impact:** C2 Trust

**Purpose.** The public page of nightly numbers: first-try pass, cost, latency, diversity, baselines with error bars, outcome track.

**Interfaces.** reads DAT-BENCH reports

**Validation.** [A] Every number on the page is produced by `make partybench` from a pinned environment

**Cross-inspections.** PartyBench ⟂ production telemetry: nightly first-try pass vs live (drift alarm, Sprint 2+)

**Telemetry and logs.** `nightly report`

**If it breaks — Numbers differ from the deck.** Touch: `PartyBench harness`, `pinned demo environment`. Logs: `the nightly report for that date`. Checks: (1) Same commit, catalog hash and model version?

## API gateway

*FastAPI under /api/v1 — validation, rate limits, tokens*

### API-APP · FastAPI app — `api/app.py · /health · /static`

**Status:** Built (living-pass @ 21355aa) · **CX impact:** C2 Trust

**Purpose.** Composes the routers under /api/v1, serves / and /rsvp and the static assets, exposes /health; ENV dev|prod|test.

**Interfaces.** routers: plan, living, events, bookings, vendors · GET /health · /static → web/

**Validation.** [T] tests/test_planner_api.py, test_input_validation.py, test_pentest.py, test_adversarial_security_fuzzing.py · [T] scripts/loop_harness.py 100 adversarial loops with penetration probes

**Cross-inspections.** Pydantic rejects extra keys on every body (extra=forbid) — fuzzing confirms

**Telemetry and logs.** `uvicorn access log` · `GET /health`

**If it breaks — App will not start or /health fails.** Touch: `api/app.py create_app`, `core/config.py settings`. Logs: `process stdout at startup`. Checks: (1) Missing env (ANTHROPIC_API_KEY when LLM_BACKEND=anthropic)? (2) data/ writable (events, bookings, iparty.db)?

### API-PLAN · Plan & metrics routes — `api/routes.py · POST /plan`

**Status:** Built (living-pass @ 21355aa) · **CX impact:** C2 Trust

**Purpose.** The planning endpoint: validates PartyRequest, rate-limits (PLAN_RATE_PER_MIN 20), calls TTLPartyPlanner; 422 with violations + minimum_feasible_budget when no valid plan; 503 planning_unavailable when the breaker is open or retries are exhausted. /metrics exposes breaker, watchdog, backend and catalog size behind METRICS_TOKEN.

**Interfaces.** → ENG-PLANNER · ← PlanResult {status, plan, verification, telemetry, backend} · GET /api/v1/metrics

**Validation.** [T] tests/test_planner_api.py (422/503 contracts, hallucinated price and unknown SKU rejection) · [T] test_input_validation.py boundary values · [M] /metrics circuit_breaker state in production

**Cross-inspections.** 422 bodies always carry minimum_feasible_budget when one exists (test_planner_api) · /metrics breaker state ⟂ iparty.ttl log events · X-06 (UX-HOST ⟂ API-PLAN)

**Telemetry and logs.** `response.telemetry.pattern_log` · `iparty.planner and iparty.ttl loggers` · `/metrics`

**If it breaks — 503 planning_unavailable.** Touch: `core/config.py CB_FAILURE_THRESHOLD/CB_COOLDOWN_SECONDS`, `llm/client.py backend`. Logs: `GET /metrics → circuit_breaker.state, failures`, `iparty.ttl: 'circuit OPEN'`, `iparty.llm errors`. Checks: (1) Is the Anthropic key/model valid? (2) Wait CB_COOLDOWN_SECONDS (30 s) for HALF_OPEN probe (3) MOCK_FLAW_RATE left non-zero in prod?

**If it breaks — 429 on normal use.** Touch: `core/ratelimit.py`, `PLAN_RATE_PER_MIN`. Logs: `uvicorn access log 429s`. Checks: (1) Shared NAT / UI matrix hammering one client key?

### API-LIVING · Living Pass routes — `api/living.py`

**Status:** Built (living-pass @ 21355aa) · **CX impact:** C1 Safety & money

**Purpose.** POST /plans creates a pass (plans the party, stores it, mints a host token and share links); GET /plans/{id} (host), /rsvp (public invitation), POST /rsvp, GET /status (live verification), POST /apply (accept a proposal), GET /guests.

**Interfaces.** → ENG-PLANNER on create · → LIV-ENGINE build_status/apply · → LIV-STORE · host token via header or ?host_token

**Validation.** [T] tests/test_living_pass_api.py (contracts, privacy, tokens, 404/429) · [T] tests/test_living_pass_mece.py waves of RSVP drift across 100 profiles

**Cross-inspections.** Every proposal offered has passed verify_plan before it is shown (living tests assert accepted codes only)

**Telemetry and logs.** `uvicorn access log` · `data/iparty.db` · `events.jsonl`

**If it breaks — Host cannot apply a proposal (403/409).** Touch: `api/living.py apply_proposal`, `planning/living.py propose_fix`. Logs: `response detail`, `iparty.db plans.verification`. Checks: (1) Host token present? (2) Proposal id still current after a newer RSVP?

### API-EVENTS · Ledger routes — `events · bookings · vendor leads`

**Status:** Built (living-pass @ 21355aa) · **CX impact:** C4 Internal

**Purpose.** Append-only JSONL ledgers: POST /events (204; whitelisted meta keys; EVENTS_MAX_BYTES 25 MB ceiling), POST /bookings (201; BOOKINGS_MAX_PER_SESSION 3; COMMISSION_RATE 0.15), POST /vendors (lead); summaries expose counts only.

**Interfaces.** writes data/events.jsonl (EVENTS_PATH), data/bookings.jsonl, data/vendor_leads.jsonl · GET …/summary

**Validation.** [T] tests/test_events.py, test_bookings.py, test_vendors_and_commercial.py · [I] meta whitelist (_ALLOWED_META) and length caps

**Cross-inspections.** events.jsonl funnel counts ⟂ UI matrix run counts (sanity after each matrix run)

**Telemetry and logs.** `the JSONL files themselves` · `summary endpoints`

**If it breaks — Events stop being recorded.** Touch: `api/events.py _events_path`, `EVENTS_MAX_BYTES`. Logs: `file size of data/events.jsonl`, `429s in the access log`. Checks: (1) Ceiling reached? (2) EVENTS_PATH points to a writable path on the host?

### API-VEND · Vendor lookup — `GET /vendors/lookup`

**Status:** Built (living-pass @ 21355aa) · **CX impact:** C2 Trust

**Purpose.** Real businesses near the host for any SKU: ?sku&near&limit → Google Places / Yelp / Foursquare (optional keys, cached, outage-tolerant), opt-in OSM fallback, keyless marketplace links; 422 on a bad `near`, 404 on an unknown SKU; VENDOR_LOOKUP_RATE_PER_MIN 30.

**Interfaces.** → EXT-PLACES · ← {query, source, listings, links, sources_configured, note}

**Validation.** [T] tests/test_vendor_sources.py with recorded fixtures incl. outages · [M] sources_configured in every response

**Cross-inspections.** Listings are never used for prices (price_basis stays research/quote) — test asserts

**Telemetry and logs.** `iparty.vendors logger` · `response.note`

**If it breaks — Lookup returns no listings.** Touch: `core/config.py GOOGLE_PLACES_API_KEY / YELP_API_KEY / FOURSQUARE_API_KEY`, `pricing/vendors.py sources`. Logs: `iparty.vendors`, `response.sources_configured and note`. Checks: (1) Keys set? Quota? Cache TTL (300 s / 24 h) serving a stale empty? (2) Links still present (they need no keys)?

## Planning engine

*Precheck → verifier-gated best-of-N → concept*

### ENG-PLANNER · TTLPartyPlanner — `planning/planner.py`

**Status:** Built (living-pass @ 21355aa) · **CX impact:** C2 Trust

**Purpose.** The request pipeline: (0) dietary precheck refuses unverifiable needs with 0 LLM calls; (1) feasibility precheck refuses impossible budgets with the minimum feasible budget, 0 calls; (2) verifier-gated best-of-N with the verifier's violations fed back as repair instructions.

**Interfaces.** ← API-PLAN / API-LIVING · → VER-DIET unverifiable_dietary · → VER-FEAS minimum_feasible_budget · → ENG-TTL run_verified(produce, verify) · → ENG-LLM generate_draft(feedback) · → VER-GROUND ground_draft · → VER-VERIFIER verify_plan

**Validation.** [T] tests/test_planner_api.py, test_properties.py (invariants over 200+ random inputs), test_safety_adversarial.py · [A] tests/test_100_user_profiles_mece.py: the MECE profile set end to end · [D] scripts/validate_live.py: the same requests through the full pipeline, mock and live

**Cross-inspections.** Precheck ⟂ verifier: a request refused by the precheck must also fail the verifier for every candidate (property test) · Mock ⟂ Anthropic: validate_live compares pass rates and costs between backends · X-10 (DAT-CANDLOG ⟂ ENG-PLANNER)

**Telemetry and logs.** `response.telemetry {llm_calls, candidates_generated, candidates_verified_pass, circuit_state, elapsed_seconds, pattern_log}` · `iparty.planner logger`

**If it breaks — 422 'No plan could satisfy' on a reasonable request.** Touch: `planning/feasibility.py (precheck, cheapest_compliant_draft)`, `planning/verifier.py thresholds (BUDGET_TOLERANCE, BUDGET_FLOOR_FRACTION)`, `planning/composer.py ENVELOPES / affinity`. Logs: `response.telemetry.pattern_log (which candidates failed and why)`, `response.violations codes`, `iparty.ttl candidate events`. Checks: (1) Does `make concept ARGS=…` compose a passing concept for the same request? (2) Is minimum_feasible_budget below the budget? (3) Which verifier code repeats across all N candidates?

**If it breaks — Plan returned but telemetry shows 0 verified candidates.** Touch: `orchestration/ttl_engine.py run_verified fallback (best unpassed candidate)`, `planning/planner.py raises on !passed`. Logs: `pattern_log`. Checks: (1) This must never reach the host: planner raises NoValidPlanError — check the API mapping

### ENG-TTL · TTL orchestrator — `orchestration/ttl_engine.py`

**Status:** Built (living-pass @ 21355aa) · **CX impact:** C2 Trust

**Purpose.** Reliability patterns from hardware applied to LLM calls: verifier-gated best-of-N (PLAN_CANDIDATES_N 4), consecutive-failure breaker (CB_CONSECUTIVE_FAILS 3), process-wide CircuitBreaker (5 failures → OPEN, 30 s cooldown, 2 successes to close), WatchdogTimer (soft 20 s / hard 40 s, 1 retry), REQUEST_DEADLINE_SECONDS 90; emits the telemetry ledger.

**Interfaces.** ← ENG-PLANNER produce/verify callables · → ENG-LLM via breaker.call(watchdog.execute(...)) · → /metrics breaker + watchdog metrics

**Validation.** [T] tests/test_ttl_engine.py (breaker states, watchdog retries, best-of-N stop rules, deadline) · [A] MOCK_FLAW_RATE injects broken candidates to exercise the breaker in tests · [M] /metrics in production

**Cross-inspections.** /metrics.circuit_breaker ⟂ iparty.ttl events: an OPEN state must have a logged trip · Telemetry counts ⟂ billing: llm_calls equals the provider's request count per plan (spot check monthly)

**Telemetry and logs.** `iparty.ttl logger (candidate i: verified PASS/FAIL, circuit OPEN, breaker tripped, deadline)` · `Telemetry.as_dict() in every response` · `/metrics`

**If it breaks — Every request takes ~40–90 s.** Touch: `core/config.py SOFT/HARD_TIMEOUT_SECONDS, WATCHDOG_MAX_RETRIES, REQUEST_DEADLINE_SECONDS`, `llm/client.py (slow provider, ANTHROPIC_MAX_TOKENS 3000)`. Logs: `telemetry.elapsed_seconds and watchdog_retries`, `iparty.ttl 'watchdog timeout'`. Checks: (1) Provider latency? Prompt too large (catalog_slice size)? (2) Lower N for simple requests (difficulty-adaptive N, Sprint 1)

**If it breaks — Breaker trips constantly.** Touch: `llm/client.py error handling`, `CB_* settings`. Logs: `iparty.ttl trips`, `iparty.llm errors (malformed JSON, auth)`. Checks: (1) Malformed output → MalformedPlanError → counted as a failure: check the prompt/model version

### ENG-LLM · LLM client — `llm/client.py · prompts.py`

**Status:** Built (living-pass @ 21355aa) · **CX impact:** C3 Delight & speed

**Purpose.** MockClient (deterministic, serves composer concepts; MOCK_FLAW_RATE default 0) or AnthropicClient (ANTHROPIC_MODEL, ANTHROPIC_MAX_TOKENS 3000) with SYSTEM_PROMPT + build_user_prompt: a ranked catalog slice and the composer's concept as a verified starting point; variant_for(temperature) picks the composer variant; baseline_draft falls back to the cheapest compliant plan.

**Interfaces.** ← ENG-TTL · → ENG-COMPOSER compose/catalog_slice · → EXT-ANTHROPIC · → VER-GROUND (returns a PlanDraft of SKUs, never prices)

**Validation.** [T] tests/test_planner_api.py with the mock backend; tests/test_loop_regressions.py · [D] scripts/validate_live.py LLM_BACKEND=anthropic rehearsal with published stats

**Cross-inspections.** Model output is grounded before anything is trusted: unknown SKU → UNREALIZABLE_SKU, model price ignored → PRICE_MISMATCH impossible by construction · Verbalized Sampling and backprompted verifier reasons (Sprint 0) are measured in PartyBench, not assumed · X-05 (ENG-LLM ⟂ ENG-COMPOSER)

**Telemetry and logs.** `iparty.llm logger (backend name, errors)` · `telemetry.llm_calls` · `provider dashboard spend`

**If it breaks — Concepts from the live backend are worse than the mock.** Touch: `planning/prompts.py (slice size, starting-point framing)`, `ANTHROPIC_MODEL`. Logs: `validate_live.py comparison report`, `pattern_log: how many candidates fail and on what`. Checks: (1) Is the verified starting point included in the prompt? (2) Did the model drop SKUs for prose?

**If it breaks — Auth or quota errors.** Touch: `ANTHROPIC_API_KEY`, `LLM_BACKEND`. Logs: `iparty.llm`, `provider status page`. Checks: (1) Switch LLM_BACKEND=mock to keep the product up (composer path has no external dependency)

### ENG-COMPOSER · Concept composer — `planning/composer.py`

**Status:** Built (living-pass @ 21355aa) · **CX impact:** C3 Delight & speed

**Purpose.** Deterministic, offline concept engine: profile_for(request) → affinity scoring over the catalog (theme/occasion/band/mood/cuisine/palette rules) → slot filling with per-tier ENVELOPES, an essentials reserve, quality floors, seeded variants (FNV-1a + mulberry32) and an upgrade pass → to_draft (concept_name, story, moments, schedule). compose() returns only verifier-passing drafts; catalog_slice ranks items for the LLM; suggest_theme fills blank themes.

**Interfaces.** ← ENG-LLM (variants, slices) · ← LIV-ENGINE (recomposed strategy, tier_override=essential) · → VER-VERIFIER (every draft) · reads CAT-JSON + palettes.json

**Validation.** [T] tests/test_composer_creativity.py: 179 tests incl. the 130-profile coherence gate (_audit: leakage, palette, characters, adult acts, occasion items, age/segment, meal, activity, cake, dietary, budget, PB&J) · [A] determinism and variant-diversity tests · [D] scripts/concept_debug.py --all prints every MECE profile's concept for eyeballing

**Cross-inspections.** Composer ⟂ verifier: compose() output must pass verify_plan (test) and the coherence gate audits what the verifier does not own · Composer ⟂ solver (Sprint 1): solver cost ≤ composer cost on all 130 profiles, both verifier-clean · X-02 (ENG-COMPOSER ⟂ VER-VERIFIER) · X-03 (ENG-SOLVER ⟂ ENG-COMPOSER) · X-05 (ENG-LLM ⟂ ENG-COMPOSER)

**Telemetry and logs.** `none at runtime beyond the plan itself; `make concept` and concept_debug.explain offline`

**If it breaks — Bland, repetitive or off-theme concepts (cornbread everywhere, a mariachi at a Nordic brunch).** Touch: `planning/composer.py affinity(), SYNONYMS, PHRASES, cuisine penalties, ENVELOPES`, `scripts/catalog_src/* tags (seg:, cuisine:, theme:, niche, needs:)`. Logs: `python scripts/concept_debug.py explain(req, slot, course)`. Checks: (1) Which rule gave the bad item its score? (2) Does the 130-profile gate still pass after the change? (3) Is it the mock path (composer) or the live path (model)?

**If it breaks — No concept for a request (falls to cheapest compliant).** Touch: `reserve_needed(), min_score floors`, `catalog coverage for that segment`. Logs: `compose() returns [] — check the three passes (as asked, essential, loose)`. Checks: (1) Is any item eligible for the band/location? eligible() in feasibility.py

### ENG-DPP · Pick of three (DPP) — `over the verified pool`

**Status:** Planned · Sprint 0 (20–25 Oct) · **CX impact:** C3 Delight & speed

**Purpose.** Chooses the three variants a host sees from the verified pool with a determinantal point process (kernel = quality × concept similarity), so the three are different by construction.

**Interfaces.** ← ENG-COMPOSER / ENG-ARCHIVE candidates · → UX-HOST picker

**Validation.** [T] unit tests: determinant of the shown set ≥ random triple on 130 profiles · [A] PartyBench diversity page

**Cross-inspections.** Shown-set diversity ⟂ judge quality: diversity must not cost more than 0.1 rubric points on average

**Telemetry and logs.** `candidate log: shown ids and determinant`

**If it breaks — The three look the same.** Touch: `DPP kernel features (descriptor vector)`. Logs: `candidate log determinant`. Checks: (1) Are the candidates distinct in descriptors or only in prose?

### ENG-SOLVER · CP-SAT solver — `planning/solver.py`

**Status:** Planned · Sprint 1 (26 Oct–1 Nov) · **CX impact:** C2 Trust

**Purpose.** One hand-written OR-Tools CP-SAT model: pick counts per eligible item per slot; rows for budget, servings per course, settings, allergen/certification exclusions, age, capacity, location, lead time, cake-at-birthdays and at-least-one-activity; objective = affinity (+ archive targets). Optimal bundle in <200 ms or an infeasibility certificate naming the binding rows. Composer stays the seed generator and fallback.

**Interfaces.** ← ENG-PLANNER / LIV-ENGINE (repair, minimum budget) · → VER-VERIFIER (every solution re-verified) · reads CAT-JSON

**Validation.** [T] solver cost ≤ composer cost and verifier-clean on all 130 profiles; infeasible profiles name the right binding rows; determinism · [A] optimality gap tracked nightly in PartyBench

**Cross-inspections.** Solver ⟂ composer (cost, validity) · Solver infeasibility ⟂ feasibility.py minimum budget: must agree on feasibility for every profile · X-03 (ENG-SOLVER ⟂ ENG-COMPOSER)

**Telemetry and logs.** `solver status, wall time and binding rows in the candidate log`

**If it breaks — Solver says infeasible but the composer finds a plan.** Touch: `planning/solver.py rows (a row stricter than the verifier)`, `eligible() filters`. Logs: `candidate log: binding rows`, `verifier report of the composer plan`. Checks: (1) Diff the rows against verifier.py codes one by one

**If it breaks — Optimal bundle is cheap and bland.** Touch: `objective weights`, `ENG-ARCHIVE targets`. Logs: `judge score vs composer plan`. Checks: (1) The solver owns feasible; the archive owns good — route the objective through the archive

### ENG-ARCHIVE · Concept archive — `MAP-Elites · surprise · arc`

**Status:** Planned · Sprint 2 (2–8 Nov) · **CX impact:** C3 Delight & speed

**Purpose.** Per-request MAP-Elites archive over party descriptors (energy, formality, food adventurousness, activity type, theme family, price position); composer seeds cells, Claude crossover of verified parents fills weak cells (≤8 calls/request), the verifier is the minimal criterion, the judge scores quality; score = quality × (1 + λ·surprise) × arc; a template classifier penalises clichés.

**Interfaces.** ← ENG-COMPOSER seeds · → ENG-LLM crossover prompts · → VER-VERIFIER gate · → ENG-DPP

**Validation.** [T] archive coverage ≥ k cells on 130 profiles; every cell content verifier-clean · [A] judge prefers archive triples to composer triples in ≥60% of 100 paired cases (kill criterion)

**Cross-inspections.** Archive ⟂ judge ⟂ humans: judge calibrated on 50 human-rated plans before it scores cells

**Telemetry and logs.** `candidate log: cell ids, scores, surprise, arc, crossover calls`

**If it breaks — Cells filled with nonsense or cultural leakage.** Touch: `crossover prompt`, `affinity penalties`, `template classifier`. Logs: `candidate log per cell`, `judge rubric items that failed`. Checks: (1) Did the verifier pass something the coherence gate would reject? Add the rule to the gate

### ENG-TASTE · Taste weights — `LinUCB · preference pairs`

**Status:** Planned · Sprint 3 (9–15 Nov) · **CX impact:** C3 Delight & speed

**Purpose.** 'Which of these three' picks and edits become preference pairs; LinUCB weights over plan features (cell, price position, signature type, cuisine) update globally and per host; replay evaluation before a policy ships.

**Interfaces.** ← DAT-PREF · → ENG-ARCHIVE scoring / ENG-DPP kernel

**Validation.** [A] offline replay lift of the pick rate before shipping (Yahoo!/Netflix pattern)

**Cross-inspections.** Policy ⟂ replay: a policy that does not lift replay pick rate never ships

**Telemetry and logs.** `preference log` · `pick rate of the top-ranked concept`

**If it breaks — Pick rate falls after a policy change.** Touch: `feature set`, `exploration rate`. Logs: `preference log before/after`. Checks: (1) Roll back; compare replay lift to live lift

## Verification

*The objective last word on every line item*

### VER-VERIFIER · Verifier — `planning/verifier.py`

**Status:** Built (living-pass @ 21355aa) · **CX impact:** C1 Safety & money

**Purpose.** Deterministic hard-constraint check of every candidate: BUDGET_EXCEEDED, BUDGET_SUSPICIOUSLY_LOW, ALLERGEN_VIOLATION, INSUFFICIENT_SAFE_FOOD, INSUFFICIENT_VEGETARIAN, CERTIFICATION_MISSING, KOSHER_SUPERVISION_MISSING, INGREDIENT_VIOLATION, AGE_INAPPROPRIATE, GUEST_RANGE, VENDOR_MINIMUM, VENUE_LOCATION, FOOD/MAIN/SUPPLIES_UNDERSCALED, NO_ACTIVITIES, NO_CAKE_MOMENT, SCHEDULE_NOT_MONOTONIC/TOO_SHORT, UNREALIZABLE_SKU, PRICE_MISMATCH, DIETARY_UNVERIFIABLE. Returns VerificationReport(passed, score, violations). Graded partial credit per rule arrives in Sprint 0.

**Interfaces.** ← ENG-PLANNER, ENG-COMPOSER, LIV-ENGINE, ENG-SOLVER · → VER-DIET dietary_context · reads CAT-JSON facts

**Validation.** [T] tests/test_verifier.py, test_pentest.py (certified diets ship only certified courses), test_safety_adversarial.py · [A] tests/test_properties.py invariants: a passing plan is allergen-safe and within budget over 200+ random plans

**Cross-inspections.** Verifier ⟂ grounding: prices in a passing plan equal catalog prices · Verifier ⟂ coherence gate: the gate audits semantics the verifier does not own (cultural leakage, palette, clichés) · Verifier ⟂ Living Pass: build_status re-runs the same verify_plan on the live request · X-01 (VER-VERIFIER ⟂ VER-GROUND) · X-02 (ENG-COMPOSER ⟂ VER-VERIFIER) · X-07 (LIV-ENGINE ⟂ VER-VERIFIER)

**Telemetry and logs.** `report.violations in every response (host-readable copy in the UI)` · `candidate log (Sprint 0) with per-rule scores`

**If it breaks — An allergen or certification slipped through (C1).** Touch: `planning/verifier.py the specific rule`, `pricing/catalog.py DietContext (_word_in, _EMPTY_PHRASES, certifications)`, `the item's allergens/tags in scripts/catalog_src/*`. Logs: `the plan's verification report`, `the catalog item record`, `make catalog-check (ingredient inference)`. Checks: (1) Pull the item (set status pending in vendor rows or fix the table) and rebuild the catalog (2) Add the case to test_verifier.py and the property tests before any other change

**If it breaks — Verifier rejects everything after a change.** Touch: `new rule thresholds`. Logs: `pattern_log codes across all candidates`. Checks: (1) Run the 130-profile gate; a new rule must keep ≥ the previous pass rate

### VER-GROUND · Grounding — `planning/grounding.py`

**Status:** Built (living-pass @ 21355aa) · **CX impact:** C1 Safety & money

**Purpose.** Turns a model draft (SKUs and quantities) into a PartyPlan priced from the catalog: resolves LEGACY_SKUS, rejects unknown SKUs, computes servings and settings, never accepts a model-supplied price.

**Interfaces.** ← ENG-LLM draft · → VER-VERIFIER · reads CAT-JSON

**Validation.** [T] tests/test_planner_api.py test_hallucinated_price_is_rejected, test_unknown_sku_is_rejected · [A] property tests on quantities and totals

**Cross-inspections.** Grounding ⟂ catalog: total_cost recomputed from unit_price × quantity for every line (verifier REALIZABLE check) · X-01 (VER-VERIFIER ⟂ VER-GROUND)

**Telemetry and logs.** `UNREALIZABLE_SKU / PRICE_MISMATCH codes in reports`

**If it breaks — Wrong price or a total that does not add up.** Touch: `planning/grounding.py`, `pricing/catalog.py billable_guests / settings_for`, `the catalog item (unit, serves, min_guests)`. Logs: `plan.line_items vs catalog records`, `make catalog-check`. Checks: (1) per_person items bill max(guests, min_guests) — is min_guests set right? (2) Vendor row with price_basis quote overriding a research price?

### VER-FEAS · Feasibility — `planning/feasibility.py`

**Status:** Built (living-pass @ 21355aa) · **CX impact:** C2 Trust

**Purpose.** eligible(request, catalog, diet) buckets items (venues, mains, foods, tableware, supplies, activities, services); cheapest_compliant_draft and minimum_feasible_budget drive the 0-call precheck and the Living Pass fallbacks; KOSHER_SUPERVISION_SKU; no over-capacity fallback.

**Interfaces.** ← ENG-PLANNER precheck · ← LIV-ENGINE propose_fix · → VER-VERIFIER

**Validation.** [T] tests/test_planner_api.py 422 bodies, test_mece_gap_partitions.py, test_living_pass_mece.py · [A] property: precheck-refused requests fail the verifier for every candidate

**Cross-inspections.** Feasibility ⟂ solver (Sprint 1): both must agree on feasibility for every profile · minimum_feasible_budget ⟂ cheapest verified plan cost (≤)

**Telemetry and logs.** `minimum_feasible_budget in 422 bodies and Living Pass status`

**If it breaks — Minimum budget looks too high or too low.** Touch: `cheapest_compliant_draft slot choices`, `units_to_cover / cost_per_cover`. Logs: `the 422 body`, `concept_debug for the same request`. Checks: (1) Is a cheaper eligible main/venue excluded by location or capacity?

### VER-DIET · Dietary context — `catalog.py · DietContext`

**Status:** Built (living-pass @ 21355aa) · **CX impact:** C1 Safety & money

**Purpose.** dietary_context(request) merges the dietary field with needs the theme states: FDA big-9 allergens (peanut ⇒ nuts), vegetarian/vegan, halal (certified non-veg, no pork/alcohol), kosher (every food certified + supervision), 'no pork/beef', alcohol-free via contains:* tags; keto/paleo/pescatarian are unverifiable → refused by name. Whole-word matching; empty phrases ignored.

**Interfaces.** ← VER-VERIFIER, VER-FEAS, ENG-COMPOSER · ← ENG-PLANNER unverifiable_dietary precheck

**Validation.** [T] tests/test_pentest.py (unverifiable diets), test_verifier.py, test_catalog_csv.py · [T] test_e2e_user_journeys.py keto/halal journeys

**Cross-inspections.** DietContext ⟂ catalog tags: contains:* inferred by build_catalog from names/descriptions so a forgotten tag cannot make 'no pork' look verified

**Telemetry and logs.** `DIETARY_UNVERIFIABLE code and copy`

**If it breaks — A need is misread ('no nuts' ignored, 'n/a' treated as a restriction).** Touch: `pricing/catalog.py _word_in, _EMPTY_PHRASES, allergen synonyms`. Logs: `the request's dietary string and the DietContext it produced (log it in Sprint 0)`. Checks: (1) Add the phrase to tests/test_verifier.py; never widen matching without a test

## Catalog & facts

*Priced inventory and the facts the verifier trusts*

### CAT-JSON · Catalog v2 — `catalog_v2.json · palettes.json`

**Status:** Built (living-pass @ 21355aa) · **CX impact:** C1 Safety & money

**Purpose.** 601 priced items (68 venues, 212 food by course, 118 supplies, 203 activities) with allergens, certifications, age and guest ranges, location types, tiers, tags and lead days; StaticCatalog loads it (with_vendors merges approved vendor rows); LEGACY_SKUS keep old passes resolving.

**Interfaces.** read by ENG-COMPOSER, VER-*, LIV-ENGINE, API-VEND · written only by CAT-BUILD

**Validation.** [I] make catalog-check: the committed JSON must equal the generated one (CI guard) · [T] tests/test_catalog_csv.py, test_theme_dataset.py · [I] pyproject package-data ships the JSON; .gitignore anchors /data/ so the catalog is tracked

**Cross-inspections.** JSON ⟂ tables (staleness) · palettes.json ⟂ web/themes.json (projection) · Vendor rows ⟂ schema on load · X-04 (CAT-JSON ⟂ CAT-BUILD) · X-13 (CAT-ROWS ⟂ CAT-JSON)

**Telemetry and logs.** `/metrics.catalog_items` · `build log`

**If it breaks — Catalog missing on a fresh install (0 items).** Touch: `.gitignore (/data/ not data/)`, `pyproject [tool.setuptools.package-data]`. Logs: `/metrics.catalog_items`, `startup error`. Checks: (1) Was the JSON committed? Run `make catalog-check`

**If it breaks — An item is priced or tagged wrong.** Touch: `scripts/catalog_src/<category>.py row`. Logs: `make catalog output (validation errors)`. Checks: (1) Edit the table, `make catalog`, re-run the coherence gate

### CAT-BUILD · Catalog builder — `scripts/build_catalog.py`

**Status:** Built (living-pass @ 21355aa) · **CX impact:** C1 Safety & money

**Purpose.** Assembles the tables, validates every item (allergen keys, courses, segments, theme ids, ranges), infers contains:pork/beef/alcohol from names and descriptions (NO_INFER exceptions), projects web/themes.json into palettes.json, writes the JSON, and `--check` fails CI when stale.

**Interfaces.** reads scripts/catalog_src/*.py and web/themes.json · writes CAT-JSON

**Validation.** [I] `make catalog-check` in CI · [T] the coherence gate after every catalog change

**Cross-inspections.** Inference ⟂ hand tags: an item tagged halal but inferred contains:pork fails validation · X-04 (CAT-JSON ⟂ CAT-BUILD)

**Telemetry and logs.** `build output`

**If it breaks — CI red on catalog-check.** Touch: `scripts/catalog_src/*.py`, `web/themes.json`. Logs: ``python scripts/build_catalog.py --check` diff`. Checks: (1) Run `make catalog` and commit the regenerated JSON

### CAT-ROWS · Vendor rows — `vendor_catalog.jsonl · vendors.py`

**Status:** Built (living-pass @ 21355aa) · **CX impact:** C1 Safety & money

**Purpose.** Onboarded vendor items (status approved, price_basis quote, tagged vendor) merged into the catalog; VendorDirectory with Google Places (Pro field mask, 300 s cache), Yelp and Foursquare (24 h), opt-in OSM; marketplace links for Yelp, Thumbtack, GigSalad, The Bash, Peerspace.

**Interfaces.** → CAT-JSON merge (StaticCatalog.with_vendors) · → API-VEND lookups · ← U-VENDOR

**Validation.** [T] tests/test_vendor_sources.py (fixtures, outages, merge rules) · [D] phone-confirmed rows only, from Sprint 1

**Cross-inspections.** Rows ⟂ schema: bad allergen keys skipped loudly; pending rows never load · X-13 (CAT-ROWS ⟂ CAT-JSON)

**Telemetry and logs.** `iparty.vendors logger` · `VENDOR_CATALOG_PATH`

**If it breaks — Vendor item appears in plans but is unavailable.** Touch: `row status`, `FUL-AVAIL (Sprint 4) availability flag`. Logs: `outcome log`, `vendor call notes`. Checks: (1) Set status pending; choose the replacement for the slot

## Living Pass

*The plan that re-verifies itself as guests RSVP*

### LIV-ENGINE · Living Pass engine — `planning/living.py`

**Status:** Built (living-pass @ 21355aa) · **CX impact:** C1 Safety & money

**Purpose.** build_status re-verifies the saved plan against the live request (confirmed headcount, guest allergies); repair keeps selections, drops unsafe food for the live dietary picture, adds safe main-course servings/settings (and kosher supervision), sheds the least important things first; propose_fix orders repair → recomposed (essential) → cheapest_compliant → minimum budget; requantify/right_size offer the same party portioned smaller, never a different party; apply verifies before saving.

**Interfaces.** ← API-LIVING · → VER-VERIFIER, VER-FEAS, ENG-COMPOSER · → LIV-STORE

**Validation.** [T] tests/test_living_pass_mece.py (RSVP waves incl. 4a halal / 4b keto across 100 profiles), test_living_right_size.py, test_living_apply.py · [A] accepted-code sets per wave; proposals must pass verify_plan

**Cross-inspections.** Living ⟂ verifier (same verify_plan) · Right-size ⟂ family: a right-sized plan keeps every line's family (_same_family) — test · X-07 (LIV-ENGINE ⟂ VER-VERIFIER)

**Telemetry and logs.** `GET /plans/{id}/status {state: verified|attention|unverifiable, violations, proposals, savings}` · `iparty.db plans.verification`

**If it breaks — Status stays 'attention' with no proposal.** Touch: `planning/living.py propose_fix strategies`, `feasibility for the live request`. Logs: `status body: violations and minimum_feasible_budget`. Checks: (1) Is the live request infeasible at the budget? Then only 'minimum' is offered — by design

**If it breaks — A proposal changes the party's character.** Touch: `_SHED_COURSES order`, `recomposed strategy tier`. Logs: `status.proposals[].strategy`. Checks: (1) repair should precede recomposed; check strategy order

### LIV-STORE · Plan store — `core/store.py · SQLite`

**Status:** Built (living-pass @ 21355aa) · **CX impact:** C2 Trust

**Purpose.** PlanStore: tables plans (plan_id, host_token, backend, request, plan, verification, timestamps) and guests (guest_key, plan_id, name, attending, dietary); PLANS_DB_PATH; LIVING_MAX_GUESTS_PER_PLAN 200; one small class so Postgres can replace it (Sprint 6).

**Interfaces.** ← API-LIVING / LIV-ENGINE · → data/iparty.db

**Validation.** [T] tests/test_living_pass_api.py persistence and reset; tests/test_living_apply.py · [I] schema in CREATE TABLE IF NOT EXISTS

**Cross-inspections.** Stored plan ⟂ catalog: repairs re-price from the catalog, never from stored prices

**Telemetry and logs.** `sqlite3 data/iparty.db` · `file size and write errors in the server log`

**If it breaks — Passes vanish after a deploy.** Touch: `PLANS_DB_PATH (ephemeral disk on the host)`, `Postgres migration (Sprint 6)`. Logs: `server log at startup`, `disk mount`. Checks: (1) Is data/ on a persistent volume?

**If it breaks — database is locked.** Touch: `core/store.py _tx`. Logs: `server log`. Checks: (1) Concurrent writers under load — move to Postgres

### LIV-LINKS · Links & token — `_links · emailcheck.py`

**Status:** Built (living-pass @ 21355aa) · **CX impact:** C2 Trust

**Purpose.** Share links built from PUBLIC_BASE_URL; the host token (header or ?host_token) gates host views, apply and the guest list; emailcheck validates contact fields; the public invitation exposes concept, course and certifications only.

**Interfaces.** ← API-LIVING · → UX-HOST host link, UX-RSVP invite link

**Validation.** [T] tests/test_living_pass_api.py token and privacy tests; tests/test_pentest.py · [T] scripts/loop_harness.py penetration probes

**Cross-inspections.** Invitation body ⟂ host body: no host-only fields leak (test)

**Telemetry and logs.** `403/404 in the access log`

**If it breaks — Links point to localhost in production.** Touch: `PUBLIC_BASE_URL`. Logs: `create response links`. Checks: (1) Set PUBLIC_BASE_URL on the host

## Data & learning

*Logs, ledgers, benchmarks and the training loop*

### DAT-LOGS · Application logs — `core/logging.py · stdout`

**Status:** Built (living-pass @ 21355aa) · **CX impact:** C4 Internal

**Purpose.** Loggers iparty.planner, iparty.ttl, iparty.llm, iparty.vendors to stdout as `time LEVEL name :: message`; uvicorn access log alongside. On the host: the service's log stream; locally: the terminal or `docker logs`.

**Interfaces.** written by ENG-*, API-VEND · read by humans and the triage index

**Validation.** [M] every incident ends with the log line that explained it added to this register

**Cross-inspections.** Logs ⟂ telemetry: a breaker OPEN in /metrics has a matching log line · X-08 (DAT-TELEMETRY ⟂ DAT-LOGS)

**Telemetry and logs.** `stdout`

**If it breaks — No logs in production.** Touch: `core/logging.py (INFO level, stdout handler)`, `host log retention`. Logs: `host dashboard`. Checks: (1) Is stdout captured? Is the level INFO?

### DAT-TELEMETRY · Reliability ledger — `telemetry · /metrics`

**Status:** Built (living-pass @ 21355aa) · **CX impact:** C2 Trust

**Purpose.** Every plan response carries telemetry (pattern_log, llm_calls, candidates_generated, candidates_verified_pass, watchdog_retries, circuit_state, elapsed_seconds) which the UI renders as the reliability ledger; /metrics exposes the process-wide breaker and watchdog.

**Interfaces.** ← ENG-TTL · → UX-HOST ledger · → U-OPS

**Validation.** [T] tests/test_ttl_engine.py telemetry counts; tests/test_planner_api.py telemetry presence in 422 bodies

**Cross-inspections.** Telemetry ⟂ provider billing (monthly spot check) · X-08 (DAT-TELEMETRY ⟂ DAT-LOGS) · X-12 (DAT-BENCH ⟂ DAT-TELEMETRY)

**Telemetry and logs.** `it is the telemetry`

**If it breaks — Ledger shows 0 calls on a live-backend plan.** Touch: `llm/client.py counting`, `ttl_engine tel.llm_calls`. Logs: `pattern_log`. Checks: (1) Did the precheck answer (0 calls by design) or did counting break?

### DAT-LEDGERS · JSONL ledgers — `events · bookings · leads`

**Status:** Built (living-pass @ 21355aa) · **CX impact:** C4 Internal

**Purpose.** Append-only product ledgers under data/: funnel events with whitelisted meta, booking intents (counts and commission only in summaries), vendor leads. Privacy-safe summaries; never names or free text.

**Interfaces.** ← API-EVENTS · → summaries, PartyBench outcome track (planned)

**Validation.** [T] tests/test_events.py, test_bookings.py, test_vendors_and_commercial.py

**Cross-inspections.** Ledger counts ⟂ UI matrix runs · X-09 (DAT-LEDGERS ⟂ QA-UI)

**Telemetry and logs.** `the files` · `summary endpoints`

**If it breaks — Summary counts stop growing.** Touch: `EVENTS_MAX_BYTES ceiling`, `paths`. Logs: `file sizes`. Checks: (1) Rotate the file; raise the ceiling

### DAT-CANDLOG · Candidate log — `JSONL per request · replay`

**Status:** Planned · Sprint 0 (20–25 Oct) · **CX impact:** C2 Trust

**Purpose.** Every candidate with request, variant, draft, verdict, per-rule graded scores, latency and tokens; a replay script re-verifies a log and must reproduce every verdict (determinism). The raw material for the judge, the bandit, PartyBench and the party model.

**Interfaces.** ← ENG-TTL / ENG-PLANNER · → DAT-BENCH, DAT-TRAIN, DAT-PREF

**Validation.** [A] replay reproduces verdicts bit for bit · [I] no PII in the log (request fields only)

**Cross-inspections.** Replay ⟂ live: nightly replay of yesterday's log · X-10 (DAT-CANDLOG ⟂ ENG-PLANNER)

**Telemetry and logs.** `the log`

**If it breaks — Replay disagrees with live verdicts.** Touch: `verifier change without a version bump`, `catalog changed`. Logs: `replay diff`. Checks: (1) Stamp catalog hash and verifier version on every record

### DAT-BENCH · PartyBench — `nightly harness`

**Status:** Planned · Sprint 0 (20–25 Oct) · **CX impact:** C2 Trust

**Purpose.** 300 executable cases (the 130 gate profiles, the 100 UI-matrix requests, 70 holiday/adult), verifiers, an RSVP-drift track, baselines for ChatGPT/Gemini/Claude raw (three runs each), Miller error bars, a creativity page (coverage, DPP diversity, surprise, arc, Ritchie ratios) and later an outcome track.

**Interfaces.** ← DAT-CANDLOG, ENG-* · → UX-BENCH, U-OPS

**Validation.** [A] paired-difference statistics with error bars · [I] pinned environment hash on every report

**Cross-inspections.** PartyBench ⟂ production first-try pass (drift alarm) · PartyBench ⟂ human panel (n≥50, Sprint 3) · X-12 (DAT-BENCH ⟂ DAT-TELEMETRY)

**Telemetry and logs.** `nightly report`

**If it breaks — Nightly regression.** Touch: `the merged PR of the day`. Logs: `report diff vs yesterday`, `candidate log for the failing cases`. Checks: (1) Bisect by lane; the gate should have caught it — add the case to the gate

### DAT-JUDGE · Coherence judge — `LLM rubric · human-calibrated`

**Status:** Planned · Sprint 1 (26 Oct–1 Nov) · **CX impact:** C3 Delight & speed

**Purpose.** Ten-item rubric (one signature, one peak, courses match the vibe, no cultural leakage, age fit, a real activity, a cake moment at birthdays, dietary safety, budget used well, nothing generic) scored by a cheap model, calibrated on 50 human-rated plans (≥0.7 Spearman) and re-checked against the Sprint 3 panel.

**Interfaces.** ← ENG-ARCHIVE, DAT-BENCH · → scores in the candidate log

**Validation.** [A] Spearman ≥0.7 with humans before use; re-check each sprint

**Cross-inspections.** Judge ⟂ humans · Judge ⟂ dasher QA labels (Sprint 4+) · X-11 (DAT-JUDGE ⟂ U-HOST)

**Telemetry and logs.** `judge scores and model version in the candidate log`

**If it breaks — Judge likes what humans do not.** Touch: `rubric wording`, `judge model`. Logs: `calibration set disagreements`. Checks: (1) Freeze the archive scoring until re-calibrated

### DAT-PREF · Preference log — `picks · edits`

**Status:** Planned · Sprint 1 (26 Oct–1 Nov) · **CX impact:** C3 Delight & speed

**Purpose.** Each 'which of these three' pick and each edit stored as a preference pair with the shown set, descriptors and host context; replay-evaluable.

**Interfaces.** ← UX-HOST picker · → ENG-TASTE, DAT-TRAIN

**Validation.** [A] replay evaluation of any policy before it ships

**Cross-inspections.** Pairs ⟂ candidate log ids (every pair references logged candidates)

**Telemetry and logs.** `the log`

**If it breaks — No pairs recorded.** Touch: `UI picker event`, `API logging`. Logs: `events.jsonl pick events`. Checks: (1) Is the picker shown (three concepts) or a single plan?

### DAT-TRAIN · Party model — `SFT S3 · GRPO S6`

**Status:** Planned · Sprint 3 (9–15 Nov) · **CX impact:** C3 Delight & speed

**Purpose.** LoRA SFT of an 8B open model on verifier-accepted plans (~5k examples, ~1 GPU-hour), then GRPO with the graded verifier as a dense shaped reward (two attempts, ~$120); promoted behind the LLMClient interface only if it beats the cheap Claude tier on PartyBench first-try pass at ≤¼ the cost.

**Interfaces.** ← DAT-CANDLOG, DAT-PREF · → ENG-LLM (a new client)

**Validation.** [A] PartyBench first-try pass and cost per plan vs baselines; sparse pass/fail reward is forbidden (collapse risk)

**Cross-inspections.** Model ⟂ verifier: every model output is still grounded and verified like any candidate

**Telemetry and logs.** `training run logs` · `PartyBench report for the model version`

**If it breaks — Model regresses on a category (e.g., kosher).** Touch: `training data balance`, `reward shaping`. Logs: `PartyBench per-category pass`. Checks: (1) Kill criterion: keep buying inference if it cannot beat the baseline at ≤¼ cost

### DAT-OUTCOME · Outcome log — `dasher & host reports`

**Status:** Planned · Sprint 4 (16–22 Nov) · **CX impact:** C1 Safety & money

**Purpose.** On-time, items replaced, incidents, host rating, guest NPS per party, written by the dasher console and a post-party form; the real reward and PartyBench's outcome track.

**Interfaces.** ← UX-DASHER, U-HOST · → DAT-BENCH, FUL-AVAIL (availability actuals)

**Validation.** [M] every pilot party has a complete outcome record before the next is booked

**Cross-inspections.** Outcome ⟂ plan: replacements triggered must match pre-chosen replacements · X-14 (FUL-AVAIL ⟂ DAT-OUTCOME) · X-15 (FUL-JOBS ⟂ DAT-OUTCOME)

**Telemetry and logs.** `the log`

**If it breaks — Missing outcome record.** Touch: `console submit`, `form reminder`. Logs: `bookings ledger vs outcome log`. Checks: (1) No party closes without the record

## Fulfilment

*Price, pay, dash, deliver, report (planned)*

### FUL-PRICE · Bundle price — `items + labour + margin`

**Status:** Planned · Sprint 3 (9–15 Nov) · **CX impact:** C1 Safety & money

**Purpose.** One price for the party: solver bundle cost + dasher labour envelope + replacement allowance + variance margin; iParty is merchant of record for the bundle (alcohol excluded at launch).

**Interfaces.** ← ENG-SOLVER · → FUL-PAY

**Validation.** [T] price = sum of parts; margin ≥ floor; alcohol excluded · [A] margin per party in the outcome log

**Cross-inspections.** Price ⟂ plan total: the bundle price never undercuts the verified total · X-16 (FUL-PAY ⟂ FUL-PRICE)

**Telemetry and logs.** `bookings ledger: price parts`

**If it breaks — Negative margin on a party.** Touch: `labour envelope`, `variance margin`. Logs: `outcome log actuals vs price parts`. Checks: (1) Which part was under-estimated: labour minutes, replacements, travel?

### FUL-PAY · Checkout — `Stripe test (S3) → live (S6)`

**Status:** Planned · Sprint 3 (9–15 Nov) · **CX impact:** C1 Safety & money

**Purpose.** Stripe Checkout for the bundle; booking record linked to the Living Pass; refund and cancellation policy in the product.

**Interfaces.** ← FUL-PRICE · → EXT-STRIPE · → bookings ledger, LIV-STORE link

**Validation.** [T] Stripe test-mode e2e in the UI matrix · [I] webhook signature verification

**Cross-inspections.** Paid amount ⟂ bundle price (webhook vs record) · X-16 (FUL-PAY ⟂ FUL-PRICE)

**Telemetry and logs.** `Stripe dashboard` · `bookings ledger`

**If it breaks — Paid but no booking.** Touch: `webhook handler`, `idempotency key`. Logs: `Stripe events`, `server log`. Checks: (1) Replay the webhook

### FUL-JOBS · Dasher jobs — `one lead · window check`

**Status:** Planned · Sprint 4 (16–22 Nov) · **CX impact:** C1 Safety & money

**Purpose.** A job per party: skills (shop, assemble, host), labour budget, deadline = party start; vendor pickup windows → party start checked as a CP-SAT feasibility test over the lead dasher's route (optimisation waits for January).

**Interfaces.** ← FUL-PAY booking · → UX-DASHER · ← CAT-ROWS pickup windows

**Validation.** [T] window feasibility on every pilot party before confirmation · [D] dry run 14 Nov

**Cross-inspections.** Window ⟂ outcome: late parties must trace to a window the model called feasible (then fix the durations) · X-15 (FUL-JOBS ⟂ DAT-OUTCOME)

**Telemetry and logs.** `job record` · `outcome log`

**If it breaks — Window infeasible at confirmation.** Touch: `pickup windows in vendor rows`, `dasher start time`. Logs: `job record binding constraints`. Checks: (1) Earlier start, fewer vendors, or a second dasher

### FUL-AVAIL · Availability — `confirmed ≤7 d · replacement`

**Status:** Planned · Sprint 4 (16–22 Nov) · **CX impact:** C1 Safety & money

**Purpose.** A minimum availability flag per vendor (confirmed within 7 days) is a hard row in the solver; every slot carries a pre-chosen replacement; re-confirm 48 hours before the party; Living Pass re-verifies when a replacement triggers.

**Interfaces.** → ENG-SOLVER rows · ← CAT-ROWS · → LIV-ENGINE

**Validation.** [I] no slot without a replacement before booking · [M] replacement rate per party

**Cross-inspections.** Availability flags ⟂ outcome actuals (Instacart's lesson: predicted vs real availability) · X-14 (FUL-AVAIL ⟂ DAT-OUTCOME)

**Telemetry and logs.** `vendor confirmation log` · `outcome log`

**If it breaks — Sold-out item on the day.** Touch: `replacement for the slot`, `re-confirm cadence`. Logs: `outcome log`, `vendor call notes`. Checks: (1) Was the 48 h re-confirmation done? Trigger the replacement and re-verify the pass

### FUL-INCIDENT · Incidents — `console button · on-call`

**Status:** Planned · Sprint 4 (16–22 Nov) · **CX impact:** C1 Safety & money

**Purpose.** Incident button in the dasher console; founder on-call rota during pilots and launch; every incident gets a root cause and a register entry.

**Interfaces.** ← UX-DASHER · → DAT-OUTCOME

**Validation.** [M] time to acknowledge < 5 min during parties

**Cross-inspections.** Incidents ⟂ this register: each one must map to a node and a fix

**Telemetry and logs.** `incident log`

**If it breaks — Incident without a mapped node.** Touch: `this register`. Logs: `incident log`. Checks: (1) Add the node or failure mode

## External

*Everything we do not control*

### EXT-ANTHROPIC · Anthropic API — `ANTHROPIC_MODEL · 3000 tok`

**Status:** Built (living-pass @ 21355aa) · **CX impact:** C3 Delight & speed

**Purpose.** The live concept backend (LLM_BACKEND=anthropic). Prompt caching on the catalog slice (Sprint 0) keeps cost inside the budget; the composer path keeps the product up without it.

**Interfaces.** ← ENG-LLM

**Validation.** [D] scripts/validate_live.py rehearsal before every model or prompt change · [M] provider dashboard spend vs telemetry.llm_calls

**Cross-inspections.** Spend ⟂ telemetry

**Telemetry and logs.** `iparty.llm` · `provider dashboard`

**If it breaks — Outage or rate limits.** Touch: `LLM_BACKEND=mock fallback`, `CB_* settings`. Logs: `iparty.llm`, `/metrics breaker`. Checks: (1) Flip to mock; the composer path serves verified concepts offline

### EXT-PLACES · Places APIs — `Places · Yelp · 4sq · OSM`

**Status:** Built (living-pass @ 21355aa) · **CX impact:** C2 Trust

**Purpose.** Real listings near the host; keys optional; cached; outage-tolerant; never a price source.

**Interfaces.** ← API-VEND / CAT-ROWS

**Validation.** [T] tests/test_vendor_sources.py outage paths

**Cross-inspections.** Listings ⟂ prices: never

**Telemetry and logs.** `iparty.vendors` · `sources_configured`

**If it breaks — Quota exceeded.** Touch: `keys`, `cache TTLs`. Logs: `iparty.vendors`. Checks: (1) Links still render; fall through to the next source

### EXT-STRIPE · Stripe — `Checkout · webhooks`

**Status:** Planned · Sprint 3 (9–15 Nov) · **CX impact:** C1 Safety & money

**Purpose.** Payments for the bundle; iParty as merchant of record; test mode until Sprint 6.

**Interfaces.** ← FUL-PAY

**Validation.** [T] test-mode e2e · [I] webhook signatures

**Cross-inspections.** Paid ⟂ booked

**Telemetry and logs.** `Stripe dashboard`

**If it breaks — Webhook failures.** Touch: `endpoint URL`, `signing secret`. Logs: `Stripe event log`. Checks: (1) Replay from the dashboard

### EXT-HOST · Hosting & database — `Render · SQLite → Postgres`

**Status:** Built (living-pass @ 21355aa) · **CX impact:** C2 Trust

**Purpose.** The service and its disk: env vars (LLM_BACKEND, keys, PUBLIC_BASE_URL, METRICS_TOKEN, EVENTS_PATH, PLANS_DB_PATH), persistent volume for data/, Postgres from Sprint 6.

**Interfaces.** runs API-APP · holds data/

**Validation.** [D] `/health` and a smoke plan after every deploy · [M] host logs and disk

**Cross-inspections.** Deployed commit ⟂ PartyBench pinned environment

**Telemetry and logs.** `host dashboard` · `/health`

**If it breaks — Data lost after deploy.** Touch: `persistent volume`, `PLANS_DB_PATH`. Logs: `host logs`. Checks: (1) Is data/ mounted? Migrate to Postgres

### EXT-VENDORS · Metro vendors — `confirmed rows · windows`

**Status:** Planned · Sprint 1 (26 Oct–1 Nov) · **CX impact:** C1 Safety & money

**Purpose.** 25–40 confirmed vendors in one metro with prices, lead times and pickup windows; re-confirmed 48 h before each party.

**Interfaces.** → CAT-ROWS · → FUL-AVAIL

**Validation.** [D] phone confirmation per row; a dry-run pickup before launch

**Cross-inspections.** Vendor rows ⟂ outcome actuals

**Telemetry and logs.** `vendor call notes` · `outcome log`

**If it breaks — Vendor no-show.** Touch: `replacement vendor`, `row status`. Logs: `outcome log`. Checks: (1) Downgrade the row; pre-choose a second vendor for the slot

## Quality gates

*What must be green before anything ships*

### QA-GATE · Merge gate — `make lint test catalog-check`

**Status:** Built (living-pass @ 21355aa) · **CX impact:** C4 Internal

**Purpose.** The merge gate: ruff clean; pytest (unit, API, property-based with Hypothesis, pentest, adversarial fuzzing, e2e journeys, Living Pass MECE); the catalog staleness check. Nothing merges red.

**Interfaces.** runs on every PR from every lane

**Validation.** [T] itself

**Cross-inspections.** Gate ⟂ PartyBench: a nightly regression that the gate missed becomes a new gate test

**Telemetry and logs.** `CI output`

**If it breaks — Gate red.** Touch: `the PR`. Logs: `pytest -x output`, `ruff output`, `catalog-check diff`. Checks: (1) Never weaken a test to pass; fix the code or the data

### QA-COHERENCE · Coherence gate — `130 profiles · creativity tests`

**Status:** Built (living-pass @ 21355aa) · **CX impact:** C3 Delight & speed

**Purpose.** Every MECE profile plus 37 named cases composed and audited for cultural leakage, off-palette products and characters, adult-only acts, alcohol for minors, occasion items at the wrong occasion, age and segment fit, a real meal, a real activity, a cake at birthdays, dietary safety, budget use and PB&J without being asked.

**Interfaces.** runs on ENG-COMPOSER (and ENG-SOLVER/ARCHIVE output from Sprint 1)

**Validation.** [T] itself

**Cross-inspections.** Gate ⟂ verifier: the gate owns semantics the verifier does not

**Telemetry and logs.** `test output with the offending items`

**If it breaks — Gate fails after a catalog or rule change.** Touch: `the rule or tag that moved the item`. Logs: `the assertion message names the profile and the item`. Checks: (1) concept_debug explain for that profile and slot

### QA-UI · UI matrix — `100 profiles · Playwright + axe`

**Status:** Built (living-pass @ 21355aa) · **CX impact:** C2 Trust

**Purpose.** Drives the shipped HTML the way a person would for 100 profiles on desktop and a stratified phone set: outcome reached (verified / infeasible / native block), page errors, overflow, clipped text, tap targets, WCAG 2.1 AA via axe, copy and dead ends; living-pass states verified / attention / unverifiable.

**Interfaces.** runs against a live server (IPARTY_BASE)

**Validation.** [D] itself

**Cross-inspections.** UI ⟂ API: rendered numbers equal API numbers · X-09 (DAT-LEDGERS ⟂ QA-UI)

**Telemetry and logs.** `.ui-out/ results (ignored by git)`

**If it breaks — Matrix red.** Touch: `web/index.html or web/rsvp.html`. Logs: `.ui-out/ per-profile findings`. Checks: (1) Triage by class: a11y, overflow, copy, flow

### QA-LOOP · Adversarial & live — `loop_harness · validate_live`

**Status:** Built (living-pass @ 21355aa) · **CX impact:** C2 Trust

**Purpose.** 100 randomized hostile-ish profiles through the live API with rotating penetration probes, findings by class; and validate_live: N realistic requests through the full pipeline with publishable reliability stats (mock rehearsal or live).

**Interfaces.** runs against a live server

**Validation.** [D] itself

**Cross-inspections.** Live ⟂ mock stats · Pen probes ⟂ pentest tests

**Telemetry and logs.** `harness reports`

**If it breaks — A probe gets through.** Touch: `api/* validation`, `ratelimit`. Logs: `harness finding class`. Checks: (1) Add the probe to tests/test_pentest.py

### QA-BENCH · PartyBench nightly — `first-try pass · cost · diversity · drift`

**Status:** Planned · Sprint 0 (20–25 Oct) · **CX impact:** C2 Trust

**Purpose.** The nightly benchmark as a gate: no PR merges if the nightly regresses first-try pass, cost or diversity beyond the error bars.

**Interfaces.** reads DAT-BENCH

**Validation.** [A] paired-difference error bars

**Cross-inspections.** Nightly ⟂ gate · Nightly ⟂ production

**Telemetry and logs.** `nightly report`

**If it breaks — Regression.** Touch: `yesterday's merges`. Logs: `report diff`. Checks: (1) Bisect by lane

## Cross-performance inspection matrix

| ID | A ⟂ B | What | Method | Frequency | Pass threshold | Where | Status |
|---|---|---|---|---|---|---|---|
| X-01 | VER-VERIFIER ⟂ VER-GROUND | Prices in a passing plan equal catalog unit_price × quantity; model prices are never accepted | T/A | every PR (property tests) | 0 PRICE_MISMATCH in passing plans | `pytest; report.violations` | built |
| X-02 | ENG-COMPOSER ⟂ VER-VERIFIER | compose() returns only verifier-passing drafts; the coherence gate audits semantics the verifier does not own | T | every PR | 130/130 profiles pass both | `tests/test_composer_creativity.py` | built |
| X-03 | ENG-SOLVER ⟂ ENG-COMPOSER | Solver cost ≤ composer cost and verifier-clean on every profile; feasibility verdicts agree with feasibility.py | T/A | every PR + nightly | 0 disagreements; optimality gap logged | `PartyBench` | S1 |
| X-04 | CAT-JSON ⟂ CAT-BUILD | Committed JSON equals generated JSON; palettes.json equals the projection of web/themes.json | I | every PR (CI) | byte-identical | `make catalog-check` | built |
| X-05 | ENG-LLM ⟂ ENG-COMPOSER | Live backend vs mock backend on the same requests: pass rate, cost, latency, judge score | D/A | before any model or prompt change | live ≥ mock on judge score; cost within budget | `scripts/validate_live.py; PartyBench` | built |
| X-06 | UX-HOST ⟂ API-PLAN | Rendered receipt and ledger equal the API response; every verifier code has host copy; no dead ends | D | before every release | 100/100 profiles reach an outcome; axe 0 serious | `scripts/ui_matrix.py (.ui-out/)` | built |
| X-07 | LIV-ENGINE ⟂ VER-VERIFIER | build_status re-runs verify_plan on the live request; every proposal passes before it is offered; right-size keeps families | T | every PR | accepted-code sets per RSVP wave | `tests/test_living_pass_mece.py` | built |
| X-08 | DAT-TELEMETRY ⟂ DAT-LOGS | A breaker OPEN in /metrics has a matching iparty.ttl trip line; llm_calls match provider billing | M | daily / monthly | 0 unexplained states; spend within 10% of telemetry | `/metrics; host logs; provider dashboard` | built |
| X-09 | DAT-LEDGERS ⟂ QA-UI | Funnel event counts after a matrix run equal the profiles driven | A | after each matrix run | counts match | `GET /events/summary` | built |
| X-10 | DAT-CANDLOG ⟂ ENG-PLANNER | Replaying yesterday's candidate log reproduces every verdict (determinism; catalog hash and verifier version stamped) | A | nightly | 100% agreement | `replay report` | S0 |
| X-11 | DAT-JUDGE ⟂ U-HOST | Judge scores agree with human ratings; re-checked against the Sprint 3 panel and dasher labels | A | Sprint 1, then each sprint | Spearman ≥ 0.7 | `calibration set` | S1 |
| X-12 | DAT-BENCH ⟂ DAT-TELEMETRY | Nightly first-try pass tracks production first-try pass (drift alarm) | M/A | nightly | within error bars | `PartyBench report` | S2 |
| X-13 | CAT-ROWS ⟂ CAT-JSON | Vendor rows load only when approved and schema-valid; bad allergen keys are skipped loudly | T/I | every load | 0 silent skips | `iparty.vendors log; tests/test_vendor_sources.py` | built |
| X-14 | FUL-AVAIL ⟂ DAT-OUTCOME | Predicted availability and pre-chosen replacements vs what happened on the day | M | every party | replacement rate < 10%; 0 unplanned substitutions | `outcome log` | S4 |
| X-15 | FUL-JOBS ⟂ DAT-OUTCOME | Every late party traces to a window the model called feasible; durations re-estimated | M | every party | on-time ≥ 95% | `job record; outcome log` | S4 |
| X-16 | FUL-PAY ⟂ FUL-PRICE | Amount paid equals the bundle price; webhook event equals the booking record | T/I | every booking | 0 mismatches | `Stripe events; bookings ledger` | S3 |

## Triage index

### T-01 · Host gets 422 'No plan could satisfy' on a reasonable request (C2)

Path: API-PLAN → ENG-PLANNER → VER-FEAS → ENG-TTL → ENG-COMPOSER → VER-VERIFIER

1. Read response.telemetry.pattern_log: did the precheck refuse (0 calls) or did all N candidates fail?
2. Read response.violations: which code repeats across candidates? (BUDGET_EXCEEDED → envelopes/prices; *_UNDERSCALED → servings; VENUE_LOCATION/GUEST_RANGE → eligibility)
3. Run `make concept ARGS='"<theme>" <age> <guests> <budget> <location>'` — does the composer find a passing concept offline?
4. Compare minimum_feasible_budget with the budget; if close, the envelopes are starving a slot
5. Check iparty.ttl lines for watchdog timeouts masquerading as failures

Touch: `planning/feasibility.py`, `planning/composer.py ENVELOPES / affinity`, `planning/verifier.py thresholds`

### T-02 · 503 planning_unavailable (C2)

Path: API-PLAN → ENG-TTL → ENG-LLM → EXT-ANTHROPIC → DAT-TELEMETRY → DAT-LOGS

1. GET /api/v1/metrics (METRICS_TOKEN): circuit_breaker.state, failure count, last error
2. iparty.ttl log: 'circuit OPEN' / 'consecutive-failure breaker tripped'; iparty.llm: auth, quota or malformed-output errors
3. If the provider is down: set LLM_BACKEND=mock — the composer path serves verified concepts with no external dependency
4. Wait CB_COOLDOWN_SECONDS (30 s) for the HALF_OPEN probe; two successes close the breaker
5. Check MOCK_FLAW_RATE is 0 in production

Touch: `core/config.py CB_* / LLM_BACKEND`, `llm/client.py`

### T-03 · Concepts are bland, repetitive or off-theme (C3)

Path: ENG-COMPOSER → ENG-LLM → CAT-JSON → QA-COHERENCE → ENG-DPP → ENG-ARCHIVE

1. Is it the mock path (composer) or the live path (model)? Check response.backend
2. `python scripts/concept_debug.py explain(req, slot, course)` — which rule scored the bad item?
3. Check the item's tags in scripts/catalog_src (seg:, cuisine:, theme:, niche, needs:) and the palette id in web/themes.json
4. Run the 130-profile coherence gate after any change; add the offending case as a named case
5. If the live path is worse than the mock: prompts.py (is the verified starting point present? slice too large?)
6. From Sprint 0: check the DPP determinant of the three shown; from Sprint 2: archive cell coverage

Touch: `planning/composer.py`, `scripts/catalog_src/*`, `planning/prompts.py`

### T-04 · Wrong price or a receipt that does not add up (C1)

Path: VER-GROUND → CAT-JSON → CAT-ROWS → CAT-BUILD → UX-HOST

1. Compare plan.line_items (unit_price, quantity, billable guests) with the catalog record
2. per_person items bill max(guests, min_guests): is min_guests right for the item?
3. Is a vendor row (price_basis quote) overriding a research price? Check data/vendor_catalog.jsonl
4. `make catalog-check` — is the JSON stale?
5. If the API total is right and the page is wrong: web/index.html receipt grouping

Touch: `planning/grounding.py`, `scripts/catalog_src/<category>.py`, `data/vendor_catalog.jsonl`, `web/index.html`

### T-05 · An allergen, certification or age rule slipped through (C1)

Path: VER-VERIFIER → VER-DIET → CAT-JSON → CAT-BUILD → QA-GATE

1. Stop: pull the item (set the vendor row to pending or fix the table), `make catalog`, redeploy
2. Read the plan's verification report: which rule should have fired? (ALLERGEN_VIOLATION, CERTIFICATION_MISSING, INGREDIENT_VIOLATION, AGE_INAPPROPRIATE)
3. Check the item record: allergens, certifications, contains:* tags, min/max_age; check build_catalog inference (NO_INFER?)
4. Check DietContext parsing of the request's dietary string (_word_in, _EMPTY_PHRASES, synonyms)
5. Add the exact case to tests/test_verifier.py and the property invariants before any other change; re-run the gate

Touch: `planning/verifier.py`, `pricing/catalog.py DietContext`, `scripts/catalog_src/*`, `scripts/build_catalog.py`

### T-06 · RSVP accepted but the Living Pass status does not change (C1)

Path: UX-RSVP → API-LIVING → LIV-ENGINE → LIV-STORE → UX-HOST

1. GET /api/v1/plans/{id}/status — does the server see the guest? (data/iparty.db guests)
2. 429 from LIVING_RSVP_RATE_PER_MIN (burst 10) in the access log?
3. guest_key collision: the same name twice upserts one guest
4. Host page polling: is index.html refreshing /status after the RSVP?
5. If status is 'attention' with no proposal: the live request is infeasible at the budget — only 'minimum' is offered by design

Touch: `planning/living.py build_status / propose_fix`, `api/living.py`, `web/index.html polling`

### T-07 · Plans are slow (>20 s) or time out (C3)

Path: ENG-TTL → ENG-LLM → EXT-ANTHROPIC → ENG-COMPOSER → DAT-TELEMETRY

1. response.telemetry: elapsed_seconds, watchdog_retries, candidates_generated — one slow candidate or many?
2. iparty.ttl 'watchdog timeout' lines; provider latency on the dashboard
3. Prompt size: catalog_slice caps per category in prompts.py; ANTHROPIC_MAX_TOKENS 3000
4. N: PLAN_CANDIDATES_N 4 and CB_CONSECUTIVE_FAILS 3 bound the worst case; difficulty-adaptive N arrives in Sprint 1
5. The mock path answers in milliseconds: if that is slow too, it is the composer or the catalog load

Touch: `core/config.py timeouts and N`, `planning/prompts.py`, `orchestration/ttl_engine.py`

### T-08 · Vendor lookup returns no listings (C2)

Path: API-VEND → CAT-ROWS → EXT-PLACES

1. response.sources_configured — empty means no keys are set (links still work)
2. iparty.vendors log: quota, auth or parse errors per source
3. Cache TTLs (300 s Google / 24 h Yelp, Foursquare) may serve a stale empty result
4. 422 means `near` failed validation; 404 means the SKU is unknown

Touch: `core/config.py keys`, `pricing/vendors.py`

### T-09 · Blank page, console error or broken layout (C2)

Path: UX-HOST → UX-RSVP → UX-DATA → API-APP → QA-UI

1. Browser console: CSP violation (no unsafe-eval), a failed fetch of /static/themes.json or /static/inspo.json, a JS error
2. GET /health; uvicorn access log for 404/500
3. `make ui-test` (17 profiles) then `make ui-matrix` against the server
4. axe findings in .ui-out/

Touch: `web/index.html`, `web/rsvp.html`, `api/app.py static mount`

### T-10 · CI red on catalog-check (C4)

Path: CAT-BUILD → CAT-JSON → UX-DATA → QA-GATE

1. `python scripts/build_catalog.py --check` shows the diff (tables changed, or themes.json changed the palettes projection)
2. Validation errors name the item and the field
3. `make catalog`, run the coherence gate, commit the regenerated JSON and palettes

Touch: `scripts/catalog_src/*`, `web/themes.json`

### T-11 · Events, bookings or leads are not recorded (C4)

Path: API-EVENTS → DAT-LEDGERS → EXT-HOST

1. File sizes under data/: EVENTS_MAX_BYTES (25 MB) stops writes at the ceiling
2. 429 from EVENTS_RATE_PER_MIN / BOOKINGS_RATE_PER_MIN / BOOKINGS_MAX_PER_SESSION in the access log
3. Meta keys outside the whitelist are rejected (422)
4. EVENTS_PATH points to a writable, persistent path on the host?

Touch: `api/events.py`, `api/bookings.py`, `host env`

### T-12 · Solver says infeasible but the composer finds a plan (Sprint 1+) (C2)

Path: ENG-SOLVER → ENG-COMPOSER → VER-FEAS → VER-VERIFIER → DAT-CANDLOG

1. Candidate log: the solver's binding rows for the request
2. Verify the composer's plan: it must pass verify_plan — if it does, a solver row is stricter than the verifier
3. Diff the rows against verifier.py codes one by one; fix the row, add the profile to the X-03 test

Touch: `planning/solver.py rows`, `planning/feasibility.py eligible()`

### T-13 · Dasher late, item sold out or incident at a party (Sprint 4+) (C1)

Path: U-DASHER → UX-DASHER → FUL-JOBS → FUL-AVAIL → FUL-INCIDENT → DAT-OUTCOME → EXT-VENDORS

1. Incident log and outcome record for the party
2. Was the 48 h availability re-confirmation done? Was the replacement pre-chosen for the slot?
3. Job record: was the window feasible, and which duration estimate was wrong?
4. Downgrade the vendor row if it no-showed; re-estimate durations; add the case to X-14/X-15

Touch: `vendor row status`, `FUL-JOBS durations`, `replacement per slot`
