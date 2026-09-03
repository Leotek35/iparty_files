# UX/UI matrix — 100 user profiles through the shipped UI

`scripts/ui_matrix.py` drives the real host and guest pages with Playwright,
one browser context per profile from `tests/mece_profiles.py` (7 MECE
partitions: diy, luxury, milestone, micro, tech, cultural, fuzz), on desktop
(1280×900, all 100) and phone (390×844, a stratified 14), plus synthetic hard
cases. Every run records the outcome, page errors, horizontal overflow,
clipped text, tap targets under 40 px, and axe-core WCAG 2.1 AA violations,
then follows the verified plans into a Living Pass, a guest RSVP on a phone
(allergy / halal / 8-person party, so every host-panel state is reached) and
back to the host panel.

```bash
pip install -e ".[ui]" && playwright install chromium && npm i axe-core
make ui-test                              # 17-profile smoke through pytest (IPARTY_UI=1)
python scripts/ui_matrix.py --base http://127.0.0.1:8000 --strict   # all 100, gate summary
```

## Gates (all must hold)

no exceptions · every profile reaches the outcome its partition expects · no
page errors · no horizontal overflow · no clipped text or content escaping
its card · no tap target under 40 px · no serious/critical axe violation · no
machine codes in copy · the infeasible retry lands on a verified pass · guest
times in a 12-hour clock · "Change my RSVP" is prefilled · the host sees
names · booking errors are specific · the default date is a Saturday ·
verified, attention and unverifiable Living Pass states were all reached ·
accepting a fix (or re-planning at the minimum) lands on verified.

## Round 1 → round 2

| | before | after |
|---|---|---|
| runs (100 desktop + 14 phone + 4 synthetic) | 118 | 118 |
| profiles that could not create a Living Pass (429 on create) | 30 | 0 |
| phone runs scrolling sideways (55–64 px) | 12 of 14 | 0 |
| serious axe nodes (all `color-contrast`) | 121 | 0 |
| runs with a tap target under 40 px (theme chips, 31 px) | 114 of 114 | 0 |
| host panels showing raw codes (`INSUFFICIENT_FOOD`) | 16 | 0 |
| infeasible screens with a dead end | 2 | 0 (one-tap retry → verified) |
| Living Pass states reached | verified · attention · unverifiable | same |
| attention states the host could act on | 0 of 12 (proposals were read-only) | 15 of 15 → verified after one tap |

## Findings and owners

Severity: **S1** blocks a core journey · **S2** hurts most users · **S3** polish.

### Engineering

| ID | Sev | Finding | Fix | Status |
|---|---|---|---|---|
| E1 | S1 | Phone pages scrolled sideways: the `.stage` grid track widened to the pass's min-content (421 px) | `.stage > * { min-width: 0 }` | fixed · guarded |
| E2 | S1 | 30 profiles hit the Living Pass create limit (10/min, burst 5) — one shared IP is one client | 30/min, burst 10; harness sends a distinct `X-Forwarded-For` per context | fixed · guarded |
| E3 | S2 | A stale or mistyped host link spun forever on "checking…" | 401/404 handled with specific copy | fixed · guarded |
| E4 | S3 | Allergen copy leaked catalog keys and over-listed: "PB&J contain peanut, tree_nut" | name only the allergens present, in words | fixed · tested |
| E5 | S2 | Booking with a bad email showed "Something went wrong" | surface the 422 field message | fixed · guarded |
| E6 | S3 | Times read "14:00–17:00" on the invite and the pass | 12-hour clock in the viewer's locale | fixed · guarded |
| E7 | S3 | Two date-default setters; the Saturday one never ran | single setter | fixed · guarded |
| E8 | S1 | The host panel showed a verified fix, a right-size plan and an honest minimum budget — and no way to accept any of them; the plan stayed broken (round 2) | `POST /plans/{id}/apply` recomputes the proposal server-side, re-verifies at the live headcount, saves it; the pass above the panel refreshes in place | fixed · tested (10 API tests + every MECE profile) · browser-gated |
| E9 | S2 | Fix receipt amounts pushed 47–84 px past the card on phones: single-column grids sized to the widest line's max-content (round 2) | `grid-template-columns:minmax(0,1fr)` on every one-column grid; descriptions wrap on phones | fixed · guarded |

### UX

| ID | Sev | Finding | Fix | Status |
|---|---|---|---|---|
| U1 | S1 | `--ink-3` (#AEAEB2) at 2.0:1 — 121 axe nodes; white on the bright green CTA at 3.2:1 | tokens #5F5F64 / #6B6B70 (≥4.5:1 on canvas, surface and fill); live CTA on the darker green | fixed · guarded (contrast computed in test) |
| U2 | S2 | Theme chips 31 px tall on phones | 44 px minimum | fixed · guarded |
| U3 | S2 | Hosts saw `INSUFFICIENT_FOOD` beside the plain message | codes kept as `data-code` only | fixed · guarded |
| U4 | S1 | "Can't be done at $X — minimum is $Y" was a dead end | "Plan it at $Y" retry, verified end-to-end | fixed · guarded |
| U5 | S2 | "Save $518" card after the very first RSVP read as a demand to downsize | offer only once half have confirmed or everyone answered; calmer copy; "everyone has answered" variant | fixed · tested |
| U6 | S2 | Host panel showed counts but never who replied | collapsible guest list with going / can't | fixed · guarded |
| U7 | S1 | Allergy field defaulted to "gluten-free" — most profiles planned a gluten-free party they never asked for | empty default | fixed · guarded |
| U8 | S3 | Default date was a mid-week day | Saturday about three weeks out | fixed · guarded |
| U9 | S3 | No native share for the invite link | "Share…" when `navigator.share` exists | fixed · guarded |
| U10 | S3 | Native validation bubbles only (no inline hints) on the planner form | — | backlog |
| U11 | S2 | "Change my RSVP" returned a blank form | prefill from the same device | fixed · guarded |
| U12 | S3 | Stage transition has no motion on phones | — | backlog |
| U13 | S2 | "Re-plan at $153" was missing where the panel said "$153 is the minimum" (round 2) | one-tap re-plan at the minimum; success/error notices with `role="status"` | fixed · browser-gated |
| U14 | S3 | Booking field errors read "contact_email uses…" | "Your email uses…" | fixed |

### Product

| ID | Sev | Finding | Decision needed |
|---|---|---|---|
| P1 | S1 | Catalog breadth: 21 SKUs cannot express luxury, cultural or adult-milestone parties — those profiles verify, but on a children's-party menu | expand the catalog per partition before marketing to those segments |
| P2 | S2 | Host token travels in the URL (Partiful-style edit link) | accept for launch; add host accounts later |
| P3 | S2 | Delivery is link-only (no email/SMS) | accept for launch; notifier behind the same endpoints |
| P4 | S3 | Guests can't see the menu on the invite | decide whether the pass is public to guests |
| P5 | S3 | The pass has no visible number for support | add a short Pass Nº |
| P6 | S2 | SQLite, single instance | Postgres before multi-instance |
| P7 | S2 | An unverifiable need (halal, kosher) has no action beyond "confirm with the guest" | vendor certification field, or a guest-supplied "bringing my own" |
| P8 | S2 | Accepting a fix changes the saved plan silently for guests who already RSVP'd (menu swap) | decide whether guests are told; a "plan updated" line on the invite is cheap |

## Launch readiness

- **Desktop planner** — Go. 100/100 profiles reach the expected outcome; 0
  page errors; 0 serious axe nodes.
- **Phone** — Go. 0 sideways scroll, 0 clipped text, 0 sub-40 px targets on
  the stratified set; contrast at AA everywhere.
- **Living Pass + guest page** — Go. All three states reached across the
  matrix; every attention state was accepted with one tap and came back
  verified; retry, prefill, names, 12-hour times, share and specific error
  copy all verified in the browser.
- **Product scope** — No-go for luxury, cultural and adult-milestone
  positioning until P1 (catalog depth); the engine is sound, the menu is not
  theirs yet.
