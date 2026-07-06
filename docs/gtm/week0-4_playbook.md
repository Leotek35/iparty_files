# iParty — Weeks 0–4 Field Playbook (loop-engineered)

The 90-day GTM stands or falls on three gates: **≥50% verified-plan rate,
≥30% plan-taken, ≥60% feedback-yes.** This kit makes the first four weeks
executable. Every artifact below has been critic-reviewed (see notes).

---
## Week 0 — Proof before people
1. `LLM_BACKEND=anthropic ANTHROPIC_API_KEY=... python scripts/validate_live.py --n 50`
   → publishes verified-rate, calls/plan, repair-saves to `data/validation_run.json`.
2. Deploy latest to Render; open `/api/v1/events/summary`; confirm zeros.
3. Legal wording check (done in copy): we say **"checked against declared
   allergen data"** — never any stronger safety language. Keep it that way
   everywhere, in every channel.

## Weeks 1–2 — Recruit 25 allergy-metro parents
**Channels (3 minimum, to avoid single-community bias):** local allergy-parent
Facebook group; r/foodallergies or metro parenting subreddit; one school /
allergist-office contact.

**Recruitment DM (critic-reviewed for Mom Test compliance):**
> Hi — I'm a local founder building a party-planning tool for families managing
> food allergies. I'm NOT selling anything; I'm looking for 5 parents to try a
> 10-minute demo while I watch quietly, so I can learn where it fails. As
> thanks: a $15 coffee card. Interested?

*Critic notes:* offers value, states no-sell, asks for observation not opinion,
small honest incentive. Avoids "would you use an app that…" (hypothetical bias).

**Session script (Mom Test rules: past behavior > hypotheticals):**
1. "Tell me about the last party you planned. Walk me through what you actually did."
2. "What went wrong, or almost did?" (listen for allergy near-misses, budget blowups)
3. *Silent observation:* they use the app on their real upcoming party. Note every
   hesitation — hesitations are the bug tracker.
4. "What would you do with this plan tomorrow?" (NOT "would you use this?")
5. "What did you pay, in money or hours, to solve this last time?"
6. Only after everything: "If booking the cake/venue from this plan cost a small
   fee, talk me through whether that's interesting." Record words, not yes/no.

**Do NOT ask:** "Would you pay for this?" / "Do you like it?" — both produce
polite lies. The dashboard (plan-taken, booking-interest) answers payment intent
behaviorally.

## Weeks 2–4 — Sign 3 pilot vendors
**Target order:** allergen-certified bakery → party venue → supply retailer.

**Vendor pitch (one paragraph, verbal):**
> I run a planning tool for allergy-conscious parents in [metro]. When it builds
> a party plan, it only recommends items from a verified catalog — real products,
> real prices, declared allergens. I'd like to list [N] of your products. It
> costs you nothing; you get qualified customers who arrive knowing exactly what
> they want to order. All I need is a product list with prices and allergen info
> — I'll do the data entry.

**Onboarding = one CSV** (`docs/gtm/vendor_catalog_template.csv`) →
`load_catalog_csv()`. Typos in allergen data are rejected at load, so vendor
mistakes cannot silently reach a parent.

## The dashboard is the weekly meeting
`/api/v1/events/summary` → funnel, plan-taken rate, feedback yes-rate,
**booking_interest_rate** (transaction-intent), dietary share. Review every
Friday; fix the biggest leak; repeat.
