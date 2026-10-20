# The Party Concept composer

`src/iparty/planning/composer.py` is the creative engine behind every plan. It
exists because a verified plan that is *boring* — pizza, a sheet cake, a games
kit, PB&J — is still a failed plan. The composer turns a request into a
**concept**: one signature moment, a table that matches it, a sweet moment, a
look, a run of show, and a two-line story a host would read aloud. It does this
offline, deterministically, in milliseconds, from catalog v2 — and the model
backend starts from that verified concept instead of a blank page.

## How a request is read

`profile_for(request)` builds a `Profile`:

| Field | Source | Example (`"Halal Engagement"`, 40 guests, $5,000, age 30) |
|---|---|---|
| `band` | honoree age | `adult` (toddler 1–4 · kids 5–8 · tween 9–12 · teen 13–17 · adult 18+) |
| `occasion` | theme words, most specific family first | `engagement` (first_birthday, sweet16, quince, mitzvah, wedding, engagement, bridal, baby_shower, welcome, anniversary, graduation, retirement, housewarming, reunion, holiday, gala, corporate, birthday, gathering) |
| `birthday` | occasion, ordinals ("40th"), a blank theme on a "turning N" request, kids' themes | `False` |
| `moods` | theme words + moods the occasion implies | `{elegant, evening}` (from the occasion) |
| `cuisines` | theme words, in order of mention | `[middle_eastern]` ("halal") |
| `words` | weighted vocabulary — the host's words 1.0, two-word phrases 1.0, synonyms 0.6, hub words ("music", "night") 0.5, numbers dropped | `halal, engagement, shawarma, grill, henna, …` |
| `tier` | budget per guest: essential < $30 ≤ standard < $80 ≤ premium < $190 ≤ luxury (luxury words lift to premium) | `premium` ($125/guest) |
| `diet` | `dietary_context`: the dietary field **plus needs the theme states outright** | halal certification required, pork and alcohol avoided |

Matching is whole-word (`word_in`): "ai" never matches "kaiseki". `needs:`
tags match word stems (`quince` → quinceañera).

## How an item is scored

`affinity(item, profile, slot)` sums:

* **theme hits** × 1.4 (non-food) / 1.0 (food), capped at 2.0;
* **palette match** (+1.2) for `theme:<palette>` products when the palette's
  keywords (shipped as `pricing/data/palettes.json`, a projection of
  `web/themes.json`) match the host's words — otherwise themed paper goods
  (−1.6, −2.6 for adults), themed food (−1.6) and character acts
  (`style:character`, −2.5) are kept away;
* **cuisine identity**: matched cuisine +1.8 (main) / +1.2 (food) / +1.0;
  a *specific* cuisine that was not asked for −3.0 (non-food), −2.0 (main),
  −2.6 (other food) — nothing cultural leaks into a party that didn't ask for it;
* `niche` (−2.4 without a hit), `niche:adult` (−3.0 for children or without a
  hit), `needs:<word>` (+1.2 / −5.0), `for:<need>` (+1.0 / −1.5 for explicit
  dietary substitutes), certifications (+0.8 asked / −0.9 not asked);
* moods (+0.5 each), brunch/evening/winter/wellness mismatches, formality
  (sporty/playful acts −1.2 at weddings, galas, corporate, quince, mitzvah);
* occasion- and band-appropriate venue and activity kinds (+0.9 / +0.7 / +0.8 / +0.5);
* tier distance (+0.6 same, +0.2 adjacent, −0.8, −1.4), `signature` +0.4, the
  signature slot's preference for acts (+0.8) and for music at parties (+1.0),
  the cake slot's preference for cakes at birthdays (+1.5);
* segment fit (`seg:<band>` +0.6, `seg:all` +0.3) — items outside the band are
  never candidates at all.

## How a concept is composed

`_Composer.run()` fills slots in order with **spending envelopes** per tier
(`ENVELOPES`; kids' tiers give the entertainer more and the meal less). Unspent
money flows forward, every optional slot has a quality floor, and a **reserve**
for the essentials not yet chosen (venue, main, place settings, an activity,
the birthday cake, decor, kosher supervision) is held back from every pick:

1. **Signature** — the one thing people will talk about, chosen first with
   everything else reserved; variants rotate through the ranked list.
2. **Venue** (packages that include the meal compete on their all-in price).
3. **Main** and **tableware** (always; `essential` picks may exceed their envelope).
4. **Cake** at birthdays and milestones, then **decor** and after-dark **lighting**.
5. **Entertainment** (at least one real activity, always) and **music** for teens,
   adults and party occasions.
6. Drinks, sides, snacks, dessert, an adult bar at premium+, favors; stationery,
   rentals, a second act, photo, staffing at premium+; luxury extras.
7. `upgrade()` spends what is left on a better main, signature, music, venue,
   cake or drink — never on another trinket.

Every pick is deterministic (a seeded mulberry32 PRNG supplies small jitter —
essentials ±0.25, open slots ±0.55 — so parties differ without randomness).
`compose()` tries the tier as read, then `essential`, then a loose pass, and
returns the first draft that **passes the verifier**; `baseline_draft()` in
the LLM client falls back to the cheapest compliant plan after that.

`to_draft()` writes the `concept_name` ("Dino Dig · Magician" — the host's
words, then the anchor; the title alone when the anchor repeats them), the
`story`, 3–6 `moments` (Signature, On the table, Sweet moment, The look, Also
on, Take-home), `notes` (what was checked, lead times) and a monotonic
`schedule` whose window depends on the band and moods.

## How the backends use it

* **MockClient** serves `compose(request, variant)` for the candidate's
  temperature (0.4 → variant 0, 0.55 → 1, …). `MOCK_FLAW_RATE` re-introduces
  broken candidates for tests; the default is 0.
* **AnthropicClient** sends `catalog_slice()` (eligible items ranked by
  affinity, capped per category) and the composer's concept as a *verified
  starting point*, asking the model to improve on it. Whatever comes back is
  grounded, priced and verified like any other candidate.
* **Living Pass** uses `compose(live_request, tier_override="essential")` as
  the `recomposed` fix when the host's own selections can't be repaired.

## Tuning

```
python scripts/concept_debug.py "Dino Dig" 6 14 650 home        # one concept, with the plan and the schedule
python scripts/concept_debug.py --all                          # every MECE profile
python - <<'EOF'
from scripts.concept_debug import explain; ...                  # rank the candidates for one slot
EOF
```

`tests/test_composer_creativity.py` pins the behaviour: vocabulary weights,
occasion/mood/cuisine reading, headlines and articles, determinism, variant
diversity, and the **coherence gate** — every MECE profile plus 37 named
kids/teen/adult/cultural cases, each checked for cultural leakage, off-palette
products and characters, adult-only acts, alcohol for minors, occasion items at
the wrong occasion, age and segment fit, a real meal, a real activity, a cake
at birthdays, dietary safety, budget use, and PB&J without being asked.
