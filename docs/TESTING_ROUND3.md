# Round 3 — 100-Loop Adversarial Harness (×5 seeds) + Penetration Sweep

`scripts/loop_harness.py` runs N iterations against a live server. Each loop
builds a randomized hostile-ish profile (non-ASCII/overlong/markup names, ages
1–17, 1–300 guests, $20–$5000, cultural/religious + multi-allergy diets) and
asserts every safety and economic invariant. Every 5th loop fires one of 10
rotating penetration probes.

## Result: 500 loops (5 independent seeds × 100), 100 penetration probes
**Zero invariant failures. Zero penetration failures.** Latency p50 1–2 ms,
p95 2 ms (mock backend; excludes provider time).

Invariants asserted on every verified plan: budget never exceeded; servings ≥
guests; no forbidden allergen in any menu item; vegetarian honored when
required; unverifiable diets never ship as verified; positive prices; valid
line-item quantities. Refusals must carry violations.

Probes (each fired 10×): CSP/HSTS headers · JSON-not-HTML response ·
50k-char field · path traversal in session_id · metadata injection ·
wrong HTTP method · negative budget · past date · null injection ·
malformed JSON. All defended.

## One finding — in the harness, not the product
The first run reported `PEN-CTYPE :: plan response not JSON`. Investigation:
the server returns `application/json` correctly; the probe used a
**case-sensitive** header lookup (`Content-Type` vs the wire's `content-type`).
Fixed by normalising headers at the harness boundary. Logged because an
auditor's own bugs belong in the report — this is the second time this exact
casing artifact produced a false positive.

## Product signal (not a defect): the affordability floor
Verified-plan rate by budget band across 300 requests:

| Budget | Verified |
|---|---|
| <$100 | 2% |
| $100–300 | 16% |
| $301–800 | 50% |
| $801+ | 62% |

Refusal causes: `BUDGET_INFEASIBLE` 113, `DIETARY_UNVERIFIABLE` 97 (the latter
inflated by the synthetic diet mix — 3 of 9 sampled diets are halal/kosher/
no-pork, far above real-world share).

Cheapest verifiable party from the current seed catalog:

| Guests | Home | Park | Venue |
|---|---|---|---|
| 10 | $86 | $160 | $436 |
| 20 | $126 | $201 | $476 |
| 60 | $288 | $363 | $638 |

Marginal cost ≈ **$4.05 per additional guest at home**.

**GTM implication.** The ≥50% verified-plan gate is reachable in the $301–800
band where real families actually plan ($300–500 typical), but the product is
near-useless below $100. Two levers, both vendor-side: recruit cheaper SKUs
(budget cake, bulk supplies) to lower the floor, and set the hero's default
budget within a range the catalog can actually serve so first-time users don't
hit a refusal wall. Track verified-rate by `budget_band` in the live funnel —
that segmentation, not a UI A/B test, is the meaningful early experiment.

## CI lock
`tests/test_loop_harness_smoke.py` runs a fast in-process version (60 profiles,
all invariants) on every push, so these guarantees can't silently regress.
