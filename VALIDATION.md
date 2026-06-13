# Validation: what is proven, and what you must still prove

This document exists because the fastest way to lose a serious investor is to
overclaim. Here is the honest line between what the code now guarantees and what
remains an open business risk.

## What the code now guarantees (verified by tests)

These are enforced deterministically and covered by the test suite, including
**property-based tests** that assert invariants over 200+ randomized inputs each
(so the guarantees are not merely checked on hand-picked examples):

1. **No invalid plan is ever returned as valid.** If no candidate satisfies every
   hard constraint, the API responds `422` with the binding violations and the
   *minimum feasible budget* — it does not ship a broken plan. (`test_planner_api`,
   `test_safety_adversarial`)
2. **Prices are real, not hallucinated.** The model selects catalog SKUs; the
   system prices them. Any tampered or unknown price fails the realizability check.
   (`test_hallucinated_price_is_rejected`, `test_unknown_sku_is_rejected`)
3. **Allergen safety is semantic.** Restrictions are mapped to FDA big-9 allergens
   and checked against each item's real allergen profile. A peanut dish fails a
   nut-allergy request. (`test_peanut_dish_fails_nut_allergy`, property test
   `test_invariant_passing_plan_is_allergen_safe`)
4. **Budget is a hard ceiling.** A passing plan never exceeds budget — proven as an
   invariant over random plans. (`test_invariant_overbudget_always_fails`)
5. **The circuit breaker protects across requests.** It is a process-wide singleton,
   not per-request. (`/api/v1/metrics` exposes its live state.)

## What the code CANNOT prove (open risks you must close outside the repo)

Be explicit about these in any pitch. They are not engineering gaps; they are
business facts that code cannot manufacture.

1. **Plan quality / delight.** The verifier proves a plan is *valid and buyable*,
   not that it is *good*. "Will kids enjoy it?" is not machine-checkable here.
   *De-risk by:* human-rated quality scores on real plans; a held-out eval set.
2. **Catalog realism and coverage.** Prices are representative seed data, not a
   live market. "Budget-valid" is only as true as the catalog.
   *De-risk by:* integrating a real vendor/pricing source behind the `Catalog`
   protocol (one file changes), starting in one metro.
3. **Execution, not just planning.** A plan is a checklist; a *party* requires
   booking, purchasing, and coordination. The current product stops at the plan.
   *De-risk by:* wiring real booking/checkout for at least one category and
   measuring conversion.
4. **Demand and willingness to pay.** No amount of code shows a parent will pay.
   *De-risk by:* 20–50 real parents, one question — would you pay, and did the
   plan survive contact with reality? Tie a business metric (booked-party rate)
   to the eval.
5. **Moat.** The verifier is replicable. Defensibility must come from proprietary
   catalog/vendor relationships, booking integrations, or a data flywheel — none
   of which exist yet.

## The smallest experiment that would tell you the truth

Pick one metro. Load a real local catalog (vendors, real prices) behind the
`Catalog` protocol. Run 25 real parent requests through the live Anthropic
backend. Measure: (a) % that produce a verified, *buyable* plan; (b) human
quality rating; (c) how many parents would pay; (d) how many would let you book
it. That single run decides whether to keep building — and it reuses this exact
code unchanged except for the catalog source.
