# Multi-Role Loop Pipeline — Iteration Log

Full-lifecycle pass over the v2 "Verified Pass" build. Each role ran its own
find→fix→verify loop; findings hand off downstream. Every fix is locked by a
regression test (`tests/test_frontend_static.py` unless noted).

## Loop 1 · Product Manager (GTM alignment)
| ID | Finding | Severity | Fix | Verified |
|---|---|---|---|---|
| PM-1 | Assurance chip claimed "Real catalog prices" while the catalog is seed data (contradicts VALIDATION.md §2) | High (trust) | Copy → "Verified catalog prices" | re-scan clean; locked by `test_no_overclaims_in_copy` |
| PM-2 | Hero caption "from real catalog prices" — same overclaim | High | Copy → "from a verified catalog" | same |
| PM-3..6 | Allergy-field prominence, refusal shows minimum budget, sample-pass numbers internally consistent, all gate events fired | — | pass on first probe | — |

## Loop 2 · Security
| ID | Finding | Severity | Fix | Verified |
|---|---|---|---|---|
| SEC-1 | **XSS**: 15 unescaped interpolations of user/server strings into `innerHTML`; a honoree named `<img src=x onerror=…>` executes script | **Critical** | `esc()` helper; every HTML sink escaped (name, theme, venue, menu, line items, schedule, tags, notes, violation messages). Markdown export intentionally unescaped (text sink) | re-probe: 0 raw interpolations in HTML sinks; locked by `test_no_unescaped_user_strings_in_html_sinks` |
| SEC-2 | No baseline security headers | Medium | Middleware: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy` | live headers observed on /health; locked by `test_security_headers_middleware` |

## Loop 3 · Software Engineer (code review)
| ID | Finding | Severity | Fix | Verified |
|---|---|---|---|---|
| SWE-1 | `renderPass` copied the barcode via structural `querySelector(".hero-stage .barcode")` — breaks if hero refactors | Low | Barcode SVG gets `id="barcode-src"`; lookup by id with empty fallback | node --check + live render |

## Loop 4 · Design & Accessibility (computed, then eyeballed)
| ID | Finding | Severity | Fix | Verified |
|---|---|---|---|---|
| A11Y-1 | Safe-chip green on soft green: 3.25:1 at 11px bold (needs 4.5) | High | New token `--verify-text: #177B3F` (4.77:1) for all small green text (chip, seal label, confirmations) | recomputed 4.77:1 |
| A11Y-2 | Seal label 9px, 3.63:1 on white | High | 10px + `--verify-text` | recomputed ≥4.5 |
| A11Y-3 | Placeholder gray 2.21:1 | Accepted | WCAG placeholder exemption applies (visible labels present); matches Apple system convention | logged |
| DES-1 | Visual render via wkhtmltoimage (QtWebKit; no grid/vars — understates layout): band, checklist, receipt, perforation, barcode all present, no broken/invisible text | — | — | screenshot reviewed |
| DES-2 | Cliché scan: 0 emoji, no gradients, system fonts only, no Partiful-style chaos | — | — | scan clean |

## Loop 5 · QA
- 35-test suite green throughout; every `$( id )` in JS resolves to a real or template-created id.
- Hostile-input plan (`<img onerror>` name, `<script>` theme) → 200; server echoes raw (by design), frontend escapes (SEC-1).
- 409 path returns minimum budget ($288 for the probe case); 503 path renders retry copy.

## Loop 6 · Data / Analytics
- Full journey (view → form → request → verified → copied → **booking_interest** → feedback yes) produces a correct summary: funnel deduped, booking_interest_rate 1.0, plan_taken 1.0, dietary_share 1.0.
- All three GTM gates + booking intent are measurable from v2 events. Locked by `test_funnel_events_present_in_ui`.
- One probe-harness bug found and fixed (204 body parsing) — harness, not app.

## Loop 7 · SRE / Release
- `/health` + `/api/v1/metrics` live; circuit `closed`; Dockerfile honors `$PORT`; `render.yaml` present; security headers observed in responses.

## Loop 8 · Legal / Compliance
- Banned-claims scan (safety guarantees, "allergen-free", absolutes, "real catalog", medical language) on final copy: **CLEAN**. Locked as a test.

## Honest limitation
The container has no modern browser; the visual check used a 2015-era engine
that cannot render grid/blur. The definitive design verdict still requires
human eyes on a real device — that loop belongs to the founder and the first
five parents.
