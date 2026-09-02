# Living Pass — the plan that re-checks itself every time a guest says yes

## The gap it closes

In a head-to-head benchmark against PartyGenius AI (Aug 2026), iParty's worst
category was **guest & collaboration: 25/100**. PartyGenius — and every other
tool we tested — collects RSVPs: headcount, plus-ones, dietary needs. Then it
stops. Partiful, Evite, Paperless Post, RSVPify, Punchbowl, Fotify, Invyt and
Apple Invites all share the same ceiling: the best of them turns dietary
answers into a chart "for human review". Not one feeds a single RSVP back into
the plan. No food-quantity recalculation, no budget adjustment, no allergen
conflict check.

That is the host's real problem. After the invites go out, the question is not
"how many said yes" — every app answers that. It is **"is my party still going
to work, and what do I change?"** — at 11pm the night before, when 18 confirmed
instead of 15 and one parent texted that Maya is allergic to peanuts.

## The unique value

iParty owns a verifier. So a saved plan can be re-checked against the **live**
guest list, and when it breaks, the fix is re-planned through the same engine
— verified by construction, never advice.

| A guest… | Living Pass… |
|---|---|
| RSVPs and the headcount grows | re-checks portions, place settings and budget; hands you the fix: *"+1 fruit & veggie platter (+$38), still under budget"* |
| declares a peanut allergy | re-checks every menu item's declared allergen data; swaps the unsafe item for the cheapest safe one |
| RSVPs and fewer confirm than planned | shows the cheaper verified plan for the real headcount — savings, not just shortfalls |
| declares a need the catalog can't verify (halal, kosher…) | flags it **by name** rather than silently "handling" it, and still fixes everything it *can* verify |

Every status check is deterministic and model-free: it re-grounds the host's
own selections at the live headcount and re-verifies. Zero LLM calls, instant,
free to poll.

### Why competitors can't copy it quickly
The feature is a consequence of the architecture, not a screen: it needs a
catalog with declared allergen data, a grounding step that prices selections
for a headcount, and a verifier that decides pass/fail. PartyGenius's plan is
a static, ungrounded document — there is nothing to re-check against.

## How it works

1. **Save** — `POST /api/v1/plans` runs the normal verified planner and stores
   the request, plan and verification under an unguessable `plan_id`. The host
   gets a **host token** (returned once), an invite link and a bookmarkable host
   link.
2. **Invite** — the invite link (`/rsvp?p=<plan_id>`) is a guest page: the
   party, not the guest list. Guests give a name, going / can't, party size and
   optional dietary needs. No account. They receive a `guest_key` (kept in
   their browser) to change their answer later.
3. **Re-check** — `GET /api/v1/plans/<id>/status` (host token required):
   - the saved plan is a set of catalog **selections**; they are re-grounded at
     the confirmed headcount (per-person items scale in price and servings;
     flat items don't — exactly what should trip "underscaled" when 24 show up);
   - the verifier runs against the live request (confirmed headcount, merged
     dietary picture) — its verdict is the status;
   - on failure, `repair` keeps every selection it can, drops food unsafe for a
     newly declared allergy, adds the cheapest safe servings / place settings
     until covered, trims the discretionary category (activities) if money is
     the only thing wrong, then verifies. If the host's choices can't be saved
     within budget, the cheapest compliant plan is offered; if nothing fits,
     the honest minimum budget is reported.

States: `awaiting` · `verified` · `attention` (fix attached) · `unverifiable`
(need flagged by name; any fix is marked `covers_unverifiable: false`).

## API

| Endpoint | Who | Purpose |
|---|---|---|
| `POST /api/v1/plans` | host | plan + save → `plan_id`, `host_token`, links (201) |
| `GET /api/v1/plans/{id}` | public | the verified pass (no guest list, no host token) |
| `GET /api/v1/plans/{id}/rsvp` | guest | the invitation + `confirmed_guests` (count only) |
| `POST /api/v1/plans/{id}/rsvp` | guest | respond / update own response |
| `GET /api/v1/plans/{id}/status` | host | live re-verification, attention items, verified fix, right-size |
| `GET /api/v1/plans/{id}/guests` | host | names, party sizes, needs |

Status contract: 201 / 200 / 401 bad host token / 404 unknown plan / 409
infeasible / 422 malformed / 429 rate-limited or guest list full / 503 backend.

## Trust boundaries and limits (read this)

- **Credentials.** `plan_id` is public by design (it *is* the invite link);
  `host_token` is required for status and guests, compared in constant time,
  and never appears in any public payload. The host link carries the token as a
  query parameter — the same trade-off Partiful-style edit links make. Treat it
  like a password; a signed-in host account can replace it later.
- **Guest keys** only update the row they were issued for. A key from another
  plan, or a made-up one, is treated as a new response — it can never hijack
  someone else's RSVP.
- **Input hardening.** RSVP fields are length-capped, control-characters are
  stripped, extra keys are rejected, party size is capped
  (`LIVING_MAX_PARTY_SIZE`), guest lists are capped per plan
  (`LIVING_MAX_GUESTS_PER_PLAN`), and responses are rate-limited per client.
  Hostile text is stored as inert data; the UI renders it via `textContent`.
- **Storage** is SQLite (stdlib, `PLANS_DB_PATH`) — durable across restarts on
  a single instance. Swap `PlanStore` for Postgres before multi-instance.
- **Delivery** is link-based on purpose: it works today with no email/SMS keys
  and any channel the host already uses. A notifier can be added behind the
  same endpoints.
- **What it does not claim.** A Living Pass verifies against the catalog's
  declared allergen data and the needs it understands. Needs it can't verify
  are surfaced by name, never absorbed. It is not a substitute for asking the
  guest.

## Verification

- `tests/test_living_pass_mece.py` — every verified profile in the 100-profile
  MECE matrix through five RSVP waves (awaiting, exact, overflow, allergy,
  unverifiable, shrink), asserting product invariants rather than fixed
  outcomes, plus a coverage assertion that the minimal repair path is what
  fixes most parties (mutation-tested: a dead repair path fails it).
- `tests/test_living_pass_api.py` — contract, credential separation, forged
  keys, input fuzzing, caps and rate limits, persistence across a restart,
  40-way concurrent RSVPs recorded exactly once, dietary-parsing honesty, and
  frontend guards (RSVP page renders only via `textContent`; host renderer
  escapes every server string; no over-claiming copy; form defaults pass the
  browser's own validation).
