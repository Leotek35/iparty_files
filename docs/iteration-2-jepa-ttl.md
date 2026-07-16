# Iteration 2 — JEPA-TTL Bridge + 150-Persona Hard Suite (v1.2.0)

## The architectural question

v1.1 changed *what* the planner selects, not *how* the TTL orchestrator
decides. The engine was reliability-only and fully reactive: first-pass-wins
selection, a fixed candidate budget N for every request, a fixed temperature
ladder, repair feedback only *after* a failure, and zero memory across
requests.

## The bridge (`src/iparty/orchestration/jepa_bridge.py`)

JEPA's core idea — predict outcomes in a joint representation space scored by
an energy function, instead of predicting raw outputs — maps directly onto
this system, because **the verifier already is a ground-truth energy
function** (violations = energy):

| JEPA concept | Realisation here |
|---|---|
| Joint embedding of context + candidate | `encode_request` / `encode_plan`: catalog-grounded feature vectors (budget tightness, food scarcity under the diet, servings/supplies ratios, age fit…) |
| Energy function | The constraint verifier (ground truth) |
| Predictor trained in latent space | `OutcomePredictor`: per-violation online logistic heads, pure Python, learned continuously from real verifier reports |
| Using predictions to act, not just react | `JepaAdvisor` hooks inside `TTLOrchestrator.run_verified` |

Five decision points went from blind to anticipatory:

1. **Adaptive candidate budget** — predicted request difficulty sets N before
   any generation is spent (easy request → 1 candidate, hard → up to N).
2. **Preemptive repair** — the predictor's top-risk violations become concrete
   instructions injected into the *first* prompt, not after the first failure.
3. **Energy assessment per candidate** — predicted energy is logged against
   the verifier's verdict; calibration is exposed at `/api/v1/metrics`.
4. **Online learning** — every verified candidate is a labelled example; the
   shared predictor improves on the live workload across requests.
5. **Energy-based continuation** — after a mediocre pass on a hard request the
   loop may keep sampling instead of blind first-pass-wins; the best passing
   candidate is returned.

Fully backward compatible: `advisor=None` reproduces the old engine exactly,
and `JEPA_BRIDGE_ENABLED=false` disables it globally.

## Measured A/B (150-persona hard suite, identical code otherwise)

| Metric | Bridge OFF | Bridge ON |
|---|---|---|
| Delighted | 147/150 | **148/150** |
| Mean LLM calls per verified plan | 1.34 | **1.09** (−19%) |
| Repeat-customer cohort (calls, 1st half → 2nd half) | 1.27 → 1.33 (no learning) | 1.07 → **1.00** (learns) |
| Predictor calibration accuracy | — | **91.4%** after 139 examples |

Suite 1 (100 personas) re-run: 80/100 delighted, no regression — remaining 15
majors are the same roadmap features documented in iteration 1.

## The harder customer base (`scripts/personas2.py`)

150 personas: 30 exact boundary surfers (guest counts at serving-size edges,
age gates 2/3 and 12/13, 23:00 + 6 h midnight clamp, budget one cent under the
floor), 30 compound stackers (4+ simultaneous constraints, e.g. vegan + GF +
sesame + evening park + 120 guests + rain backup), 20 multilingual dietary
texts, 20 adversarial payloads, a 30-request repeat-customer learning cohort,
and 20 chaos combinations.

## Bugs the hard suite caught (fixed + regression-tested)

1. **"laktosefrei" served a milk cake.** The dietary parser only knew English.
   Added multilingual aliases (German, Spanish, French, Italian, Japanese,
   Chinese… and 🥜) to the allergen map and vegetarian-tradition detection.
   Unknown phrases were already flagged honestly; now common ones are enforced.
2. **The mock's "flawed" candidate passed verification on big budgets** and
   shipped a thin plan. Overshoot quantity now scales with the budget so an
   injected flaw is guaranteed to be a flaw for any budget.

## Explored but deferred (documented, not faked)

Beam search over repair space, learned temperature policy per failure mode,
persistent predictor state across process restarts, latent rollouts of
candidate *edits* (predict energy of a repair before applying it), and
replacing the logistic heads with a small learned embedding when a real LLM
backend supplies text features.

## Repeat the loop

```bash
python scripts/run_personas.py personas2                        # hard suite
JEPA_BRIDGE_ENABLED=false python scripts/run_personas.py personas2  # ablation
```
