# Round 2 — Widened User Simulation + Penetration Test

Method note: the "user simulation" is a 120-profile synthetic sweep through the
real API across demographics the earlier runs never touched (cultural/religious
diets, multi-allergy, non-ASCII names, phrasing variants, ages 1–16, budgets
$25–$4000, 1–250 guests). It stresses the product; it is NOT a substitute for
real humans. The penetration test hit every live endpoint.

## Widened simulation — key finding: SILENT DIETARY GAPS (safety)
Across 120 profiles, budget/servings/allergen invariants held on all verified
plans. But widening demographics exposed a new failure class: needs the parser
did not recognize were **silently ignored**, and the plan still shipped as
"verified."

| Need expressed | Before | After |
|---|---|---|
| `coeliac` (British spelling of celiac) | ignored → unsafe gluten | **maps to wheat, enforced** |
| `halal`, `kosher`, `no pork` | ignored → shipped "verified" | **fail closed: honest 409, 0 LLM calls** |

This is the original peanut bug in a new disguise. Fix: (1) added the `coeliac`
synonym; (2) architectural — a **dietary-recognition precheck**: if the user
expresses a need iParty cannot verify, it refuses with a clear message and
routes it to the roadmap, rather than implying safety it hasn't checked. The
verifier carries the same check as a safety net. Fail-closed is the correct
posture for child safety, and it turns halal/kosher into a visible roadmap +
market-expansion signal rather than a hidden liability.

## Penetration test — 10 probes, 4 real gaps fixed
| ID | Probe | Result | Fix |
|---|---|---|---|
| PEN-1 | Reflected XSS via API | Safe — API is JSON, UI escapes | (harness header-casing artifact; no change) |
| PEN-2 | Security headers | No CSP/HSTS | **CSP + HSTS added** (inline UI needs 'unsafe-inline'; all else same-origin) |
| PEN-3 | 100k-char field | 422 (pydantic caps) | OK |
| PEN-4 | 5MB body | 422 | OK |
| PEN-5 | Path traversal in session_id | 422 (regex) | OK |
| PEN-6 | Metadata injection | 422 (whitelist) | OK |
| PEN-7 | Distributed event flood (2000 unique sessions) | filled log unbounded | **per-IP rate limit + hard disk ceiling** |
| PEN-8 | Cost-DoS: `/plan` unmetered | 15 rapid calls all 200 | **per-IP rate limit (429 + Retry-After)** — protects the API bill |
| PEN-9 | `/metrics`, `/events/summary` public | business data exposed | **optional `METRICS_TOKEN` gate** |
| PEN-10 | Wrong HTTP method | 405 | OK |

All fixes locked as regression tests (`tests/test_pentest.py`). 48 tests total.

## Production notes
- Rate limits are in-process (single instance). At multi-instance scale, back
  `RateLimiter.allow()` with Redis.
- Set `METRICS_TOKEN` in the deploy environment to gate operational endpoints.
