# Iteration 1 — 100-Persona Continuous Improvement Loop (v1.1.0)

## Method

100 synthetic customers with mutually exclusive, maximally complex requirements
(allergies × diets × ages 1–100 × budgets $0.01–$25k × 1–500 guests × hostile
inputs × feature seekers) were run against the live API. Every unmet need became
structured feedback; the highest-frequency issues were fixed, then the whole
suite was re-run. The harness ships in `scripts/personas.py` +
`scripts/run_personas.py` so the loop is repeatable.

## Results

| Metric | v1.0 baseline | v1.1 after iteration |
|---|---|---|
| Delighted (zero complaints) | 33 / 100 | **80 / 100** |
| Personas hitting blockers | 6 | **0** |
| Personas with major issues | 59 | 15 (all roadmap features) |
| Test suite | 35 passed | **47 passed** (12 new regression tests) |

## What changed and why

1. **Budget floor removed (was: 6 refusals).** Cheapest activity was $45, so
   $40–$80 parties were rejected. Added `ACT-CLASSIC` printable games ($12) and
   `SUP-PAPER` tableware ($1.25/person). A $40 backyard party for 8 now verifies.

2. **Dietary silence ended (was: kosher/halal/keto/jain requests silently
   ignored on a "verified" plan).** Kosher, halal, jain, and pescatarian now map
   to a fully vegetarian menu (safe approximation, explained in plan notes).
   Anything the parser cannot verify (keto, paleo, low-sugar…) triggers an
   `UNVERIFIED_RESTRICTION` warning and an explicit note — flagged for a human,
   never dropped.

3. **Time-window control (was: every party hardcoded 14:00–16:30).** New request
   fields `start_time` and `duration_hours` (defaults preserve back-compat);
   schedules are generated proportionally inside the window and the verifier
   warns if a plan falls outside it. Evening, brunch, and 6-hour parties work.

4. **Special-requests channel (was: no way to say "wheelchair access" or "rain
   backup").** New `special_requests` field; requests are echoed into plan notes
   for the coordinator, and the UI gained the input.

5. **Budget-aware enrichment (was: a $10k party got one $45 activity kit).** The
   mock planner now greedily adds a safe birthday cake, deluxe supplies, up to
   six age-appropriate activities, favor bags, premium catering, and per-hour
   entertainment scaled to party length — never exceeding the budget. When the
   catalog genuinely can't absorb a luxury budget, the plan says so honestly.

6. **Catalog expansion for underserved ages.** Babies: soft-play sensory corner.
   Teens/adults: karaoke, trivia, DJ, photo booth. All ages: costumed character,
   STEM station, event photographer, eco tableware, premium catering.

7. **UI.** Start-time + duration + special-requests inputs; verification
   warnings (e.g. unverified diet) now render on the pass card instead of being
   invisible.

## Remaining feedback → roadmap (deliberately not faked in code)

- Alcohol service for 21+ parties (licensing/liability decision needed)
- Real venue directory + beach/other location types
- Multi-day events and multi-honoree (twins) support
- Licensed character themes (legal review)
- PDF/calendar export, emailed invites (markdown download exists today)
- Multiple side-by-side plan options; vendor names on line items
- True keto/paleo/low-sugar menu verification (needs nutrition data per SKU)

## Repeat the loop

```bash
python scripts/run_personas.py   # prints delight metrics, writes persona_results.json
```
