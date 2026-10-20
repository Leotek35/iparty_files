# Catalog v2

`src/iparty/pricing/data/catalog_v2.json` is the priced inventory every plan is
built from and verified against: **601 items** across venues (68), food (212),
supplies (118) and activities (203), covering every segment the product serves —
toddlers and first birthdays, kids and tweens, teens and Sweet 16s /
quinceañeras / mitzvahs, adult milestones and showers, cultural celebrations
(Mexican, Indian, Chinese, Japanese, Korean, Middle Eastern, Jewish, Nigerian,
Caribbean, Greek, Scandinavian, Scottish, Tibetan, …), corporate events and
luxury galas.

The JSON is **generated**: edit the tables in `scripts/catalog_src/`
(`venues.py`, `food_mains.py`, `food_more.py`, `supplies.py`, `activities.py`)
and run `make catalog`. `make catalog-check` fails CI when the JSON is stale.
The generator validates every item (allergen keys, courses, segments, theme
ids, ranges) and infers ingredient facts (`contains:pork`, `contains:beef`,
`contains:alcohol`) from names and descriptions so a forgotten tag can never
make a "no pork" plan look verified.

## Item schema

| Field | Meaning |
|---|---|
| `sku`, `category`, `name`, `description` | identity (`venue` / `food` / `supplies` / `activities`) |
| `subcategory` | food: a **course** (`main`, `side`, `snack`, `dessert`, `cake`, `drink`); supplies: `tableware`, `decor`, `lighting`, `rentals`, `favors`, `stationery`; activities: `entertainment`, `music`, `games`, `inflatables`, `workshop`, `sports`, `photo`, `tech`, `wellness`, `effects`, `ceremony`, `staffing`, `planning`, `transport`; venues: their kind |
| `unit`, `unit_price`, `serves` | `per_person` (billed per guest, with a billing floor), `flat`, `per_hour`, `each`; `serves` = servings per unit (food) / settings per pack (tableware) |
| `allergens`, `vegetarian` | FDA big-9 keys, authoritative for the verifier |
| `certifications` | `halal`, `kosher` — facts the verifier checks when the host asks |
| `min_age`, `max_age` | the honoree's age range |
| `min_guests`, `max_guests` | billing floor (per-person items) and capacity (`GUEST_RANGE` is an error, `VENDOR_MINIMUM` a warning) |
| `location_types` | where the item can be used (`home`, `venue`, `park`, `restaurant`) |
| `tier` | `essential`, `standard`, `premium`, `luxury` |
| `tags` | see below |
| `lead_days` | how far ahead to book (surfaced in the concept notes) |
| `price_basis`, `sources` | `research` (2026 US market rates; sources per category), `legacy` (original fixtures), `quote` (an approved vendor row) |

## Tags

| Family | Meaning |
|---|---|
| `seg:toddler/kids/tween/teen/adult/all` | who the item is for; items outside the honoree's band are never candidates |
| `cuisine:<key>` | cultural / culinary identity — matched to the theme, penalized elsewhere (`mexican`, `italian`, `american`, `bbq` are *popular* and allowed anywhere; the rest are *specific*) |
| `theme:<palette id>` | a themed product for one palette in `web/themes.json` (dino plates, a neon pack) |
| `mood:<word>` | elegant, playful, glow, cozy, outdoor, winter, brunch, evening, wellness, nerdy, retro, sporty, festive |
| `style:<word>` | diy, station, buffet, plated, kit, rental, included, shared, formal, **character** (a costumed character act) |
| `signature` | can anchor a concept on its own |
| `contains:pork/beef/alcohol` | ingredient facts the verifier enforces for "no pork", halal, alcohol-free |
| `niche`, `niche:adult` | never without a theme hit; adult-only |
| `needs:<word>` | only when the theme says the word (holiday, ceremony and occasion items) |
| `for:<need>` | built for a dietary need (`gluten_free`, `vegan`, `vegetarian`, `nut_free`, `halal`, `kosher`) |
| `includes:main` | a venue package that feeds everyone |
| `nut_free_kitchen` | prepared in a nut-free facility |
| `vendor` | an onboarded vendor row (see below) |

## Dietary semantics

`dietary_context(request)` merges the dietary field with needs the theme states
outright ("Halal Engagement", "Vegan Brunch", "Jain Pure Veg"):

* allergens → items containing them are unsafe; "peanut allergy" is read as a
  nut allergy (peanut + tree nut);
* vegetarian / vegan → non-vegetarian items are unsafe (vegan also excludes
  milk, egg, fish, shellfish);
* **halal** → every non-vegetarian food item must carry `halal`; pork and
  alcohol are avoided;
* **kosher** → every food item except drinks must carry `kosher`, and the plan
  must include `ACT-KOSHER-SUPERVISION` (a mashgiach on site);
* "no pork", "no beef", "alcohol-free" → `contains:*` items are unsafe;
* keto, paleo, pescatarian and anything else the catalog has no data for are
  **unverifiable** → the planner refuses (409) rather than imply safety, and a
  Living Pass flags them by name.

## Legacy SKUs

The original fixtures (`VEN-HOME`, `FD-PIZZA`, `FD-PBJ`, `SUP-BASIC`,
`ACT-GAMES`, …) are still real items; `LEGACY_SKUS` in `catalog.py` maps a few
renamed codes so saved Living Passes keep resolving.

## Vendor rows

`data/vendor_catalog.jsonl` holds one JSON item per line in this schema with
`"status": "approved"`; `StaticCatalog.with_vendors()` merges them (tagged
`vendor`, `price_basis: quote`) and `GET /api/v1/vendors/lookup` finds real
businesses near the host for any line item. See `src/iparty/pricing/vendors.py`.
