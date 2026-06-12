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
| Repeated failures waste money | **Circuit breaker** stops early (fail fast) |
| One sample is unreliable | **Best-of-N** generates candidates, returns the first that *passes* |

The orchestration emits **telemetry** describing exactly which patterns fired,
which the UI renders as a live *reliability ledger*.

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

## Project layout

```
src/iparty/
  core/          config, exceptions, logging
  orchestration/ ttl_engine.py  — circuit breaker, watchdog, best-of-N orchestrator
  planning/      models, verifier (the gate), prompts, planner
  llm/           Anthropic + offline Mock backends
  api/           FastAPI app + routes
web/             single-page UI with the reliability ledger
tests/           verifier, engine, planner, and API tests
```

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

## License

MIT — see [LICENSE](LICENSE).
