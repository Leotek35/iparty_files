# iParty 🎈

**Verifier-gated birthday-party planning, built on the TTL reliability engine.**

iParty turns a few details about the guest of honor into a complete party plan —
and *guarantees* that plan fits your budget, headcount, dietary needs, and
schedule before you ever see it. Plans aren't just generated; they're **checked
against your real constraints** by a deterministic verifier, and only a passing
plan is returned.

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
the savings. A need the catalog can't verify (halal, kosher) → flagged by name,
never silently "handled". Every proposal is one tap to accept — it is
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
`GET /api/v1/plans/{id}/status` and `/guests` (host token required).

## Project layout

```
src/iparty/
  core/          config, exceptions, logging
  orchestration/ ttl_engine.py  — circuit breaker, watchdog, best-of-N orchestrator
  pricing/       catalog (grounded prices + allergen profiles) — swap for a live vendor API
  planning/      models, grounding, verifier (the gate), feasibility, prompts, planner
  llm/           Anthropic + offline Mock backends
  api/           FastAPI app + routes
web/             single-page UI with the reliability ledger + guest RSVP page
tests/           verifier, engine, planner, API, 100-profile MECE matrix, UX guards
tests/ui/        opt-in browser matrix (IPARTY_UI=1): 100 profiles × desktop/phone, axe-core
scripts/         ui_matrix.py (the browser harness), suite packaging
```

## Testing

```bash
make test        # 487 tests: engine, verifier, API, 100-profile MECE matrix, static UX guards
make lint
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
