# iParty 🎈

**Verifier-gated party planning for every celebration — toddlers to galas — built on the TTL reliability engine.**

iParty turns a few details about the guest of honor into a complete **Party
Concept** — a signature moment, a table that matches it, a sweet moment, a
look and a run of show — priced from a 600-item catalog that covers kids and
tweens, teens and Sweet 16s, adult milestones, cultural celebrations and luxury
events. And it *guarantees* that concept fits your budget, headcount, dietary
needs (allergens, vegan, **halal, kosher, no pork**), ages and schedule before
you ever see it. Concepts aren't just generated; they're **checked against your
real constraints** by a deterministic verifier, and only a passing concept is
returned. No model reachable? The built-in composer still produces a verified
concept offline. Details: [docs/COMPOSER.md](docs/COMPOSER.md) ·
[docs/CATALOG.md](docs/CATALOG.md).

This is the production realization of the architecture validated in the
[TTL research notebooks](#research-foundation): **TTL-for-planning = verifier-gated
best-of-N + circuit breaker + watchdog.**

---

## Why this is different from "call an LLM and hope"

A raw LLM call returns something *plausible*. iParty returns something *verified*:

| Concern | How iParty handles it |
|---|---|
| Plan blows the budget | **Verifier** rejects any plan whose line items exceed the cap |
| Not enough food for the guests | **Verifier** checks menu servings ≥ guest count |
| Missing venue / supplies / activities | **Verifier** enforces completeness |
| Dietary needs ignored | **Verifier** requires the menu to address them |
| Model returns junk / times out | **Watchdog** retries malformed or slow generations |
| Repeated failures waste money | **Circuit breaker** (process-wide) stops early (fail fast) |
| One sample is unreliable | **Best-of-N** generates candidates, returns the first that *passes* |
| **Prices are hallucinated** | The model **selects catalog SKUs**; the system prices them. Unreal prices are rejected. |
| **Allergens are unsafe** | Checked against FDA big-9 allergen profiles, not string tags. A peanut dish fails a nut-allergy request. |
| **"Halal" or "kosher" is hand-waved** | Certifications are catalog facts: every meat course must be certified (kosher: every course, plus on-site supervision), and `contains:pork` items never reach a no-pork table. Needs the catalog has no data for (keto, paleo) are refused honestly, never implied. |
| **The plan is bland** (PB&J at a party) | The **Party Concept composer** reads the theme, occasion, age band, moods and cuisines, scores all 600 items for fit, and builds a concept around a signature moment — then the model is asked to improve on that verified starting point, not on a blank page. |
| **A kids' act shows up at a gala, a mariachi at a Burns supper** | Segment, cuisine, palette and occasion rules in the composer; a 100-profile coherence gate (`tests/test_composer_creativity.py`) fails the build on any leak. |
| **No valid plan exists** | The API returns `422` with the binding constraints and the **minimum feasible budget** — it never ships an invalid plan. |
| **The plan goes stale once RSVPs arrive** | **Living Pass** re-verifies the saved plan against the *live* guest list on every response — headcount, place settings, budget, declared allergies — and attaches a verified fix. See [docs/LIVING_PASS.md](docs/LIVING_PASS.md). |

The orchestration emits **telemetry** describing exactly which patterns fired,
which the UI renders as a live *reliability ledger*.

## Living Pass — the plan that re-checks itself as guests RSVP

Every RSVP tool on the market counts heads and stops. A Living Pass is a saved,
verified plan with an invite link: as guests respond (name, party size,
optional dietary needs — no account), the plan is re-grounded at the confirmed
headcount and re-verified. Too many mouths for the cake → a verified fix with
its cost. A guest declares a peanut allergy → the menu is re-checked and the
unsafe item swapped. Fewer confirm than planned → the cheaper verified plan and
the savings — the same party, portioned smaller, never a different one. A
guest asks for halal → certified food is swapped in. A need the catalog can't
verify (keto, paleo) → flagged by name, never silently "handled". Every proposal is one tap to accept — it is
recomputed and re-verified server-side, then becomes the saved plan. Every
re-check is model-free and instant.

Host: build a plan → **Make it a Living Pass** → send the invite link, keep the
host link. Guest: `/rsvp?p=<plan_id>`. Details, API and trust boundaries in
[docs/LIVING_PASS.md](docs/LIVING_PASS.md).

## The TTL → planning mapping

| TTL hardware pattern | Planning realization (`src/iparty/orchestration/ttl_engine.py`) |
|---|---|
| Circuit breaker (NAND gate) | Fail fast after N consecutive verifier-rejections |
| TMR (triple modular redundancy) | Verifier-gated best-of-N candidate selection |
| Watchdog timer | Graduated soft/hard timeout + bounded retry on malformed output |
| Verification gate | `src/iparty/planning/verifier.py` — the objective constraint check |

## Quickstart

```bash
# 1. install
pip install -e ".[dev]"

# 2. run (offline mock backend — no API key needed)
make run            # or: uvicorn iparty.api.app:app --reload

# 3. open http://localhost:8000
```

Run the test suite:

```bash
pytest -q
```

### Use the live Claude backend

```bash
cp .env.example .env
# set LLM_BACKEND=anthropic and ANTHROPIC_API_KEY=sk-ant-...
make run
```

### Docker

```bash
docker compose up --build      # http://localhost:8000
```

## API

`POST /api/v1/plan`

```json
{
  "honoree_name": "Aria", "honoree_age": 6, "party_date": "2026-08-01",
  "guest_count": 14, "budget": 650, "theme": "Under the Sea",
  "dietary_restrictions": "gluten-free", "location_type": "home"
}
```

Returns the plan, a `verification` report (passed / score / violations), and
`telemetry` (candidates generated, verifier passes, watchdog retries, circuit
state, elapsed time, and a human-readable pattern log).

`GET /health` — liveness + active backend.

Living Pass: `POST /api/v1/plans` (save + links) · `GET /api/v1/plans/{id}`
(public pass) · `GET|POST /api/v1/plans/{id}/rsvp` (invitation / respond) ·
`GET /api/v1/plans/{id}/status` and `/guests` (host token required) ·
`POST /api/v1/plans/{id}/apply` (accept a fix / right-size / re-budget).

Vendors: `GET /api/v1/vendors/lookup?sku=ACT-DJ-PRO&near=Austin,TX` — real
businesses near the host for one line item (Google Places / Yelp / Foursquare /
OpenStreetMap when keys are set; marketplace deep links always). Leads, never
prices: a price only enters a plan through the catalog, or through an approved
vendor row in `data/vendor_catalog.jsonl` (`price_basis: quote`).

## Project layout

```
src/iparty/
  core/          config, exceptions, logging
  orchestration/ ttl_engine.py  — circuit breaker, watchdog, best-of-N orchestrator
  pricing/       catalog.py (catalog v2 loader, dietary context, certifications)
                 data/catalog_v2.json (600 items, generated) · vendors.py (live listings, vendor rows)
  planning/      models, grounding, verifier (the gate), feasibility, composer (the Party Concept
                 engine), prompts, planner, living (Living Pass)
  llm/           Anthropic + offline Mock backends — both start from the composer's verified concept
  api/           FastAPI app + routes (+ vendors/lookup)
web/             single-page UI (concept-first pass, reliability ledger) + guest RSVP page
scripts/         build_catalog.py + catalog_src/ (the catalog tables), concept_debug.py,
                 ui_matrix.py (the browser harness), suite packaging
tests/           verifier, engine, planner, API, 100-profile MECE matrix, Living Pass waves,
                 composer creativity + 130-profile coherence gate, vendor fixtures, UX guards
tests/ui/        opt-in browser matrix (IPARTY_UI=1): 100 profiles × desktop/phone, axe-core
```

## Testing

```bash
make test        # 677 tests: engine, verifier, API, 100-profile MECE matrix, Living Pass waves,
                 # composer coherence gate (130 profiles), vendor fixtures, static UX guards
make lint
make catalog     # regenerate src/iparty/pricing/data/catalog_v2.json from scripts/catalog_src/
make catalog-check   # CI: fail if the JSON is stale
pip install -e ".[ui]" && playwright install chromium && npm i axe-core
make ui-test     # browser smoke: 17 stratified profiles on desktop + phone (IPARTY_UI_FULL=1 for all 100)
```

The browser matrix drives the real pages the way a person would — form →
verified pass or honest "can't be done" → Living Pass → guest RSVP on a phone →
host panel — and gates on layout (no sideways scroll, no clipped text, 44px
tap targets), WCAG 2.1 AA (axe-core), copy (no machine codes), and flow (no
dead ends). Findings and their owners: [docs/UX_MATRIX.md](docs/UX_MATRIX.md).

## Research foundation

The orchestration strategy here was validated in two notebooks before being
built:

1. **TTL Architecture Evaluation** — TTL patterns vs injected infrastructure
   failures (reliability surface, recovery dynamics, Pareto frontier).
2. **TTL Planning Contest** — verifier-gated orchestration vs raw models and
   other scaffolds on a ground-truth-verifiable planning benchmark, using the
   paired-difference statistics of Miller (2024), *Adding Error Bars to Evals*.

Key honest finding carried into this design: verifier-gated best-of-N captures
most of the reliability gain, and the **circuit breaker makes it cost-efficient**
— TTL is a cost-reliability Pareto choice, not a claim to beat every alternative
on raw accuracy.

## Honest validation

See **[VALIDATION.md](VALIDATION.md)** for a precise statement of what the code
guarantees (with tests) versus the business risks code cannot close. Read it
before pitching.

## License

MIT — see [LICENSE](LICENSE).
