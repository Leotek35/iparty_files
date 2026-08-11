# iParty Commercial Playbook

Consulting-grade commercialization plan grounded in researched benchmarks
(sources at bottom). This document is the business counterpart to
VALIDATION.md: it states what the model is, what the numbers must prove, and
which product levers are already instrumented in code.

## Business model: verified-services marketplace

iParty is a two-sided marketplace. Families plan free; vendors pay a platform
fee on confirmed bookings. The verifier is the moat: every plan a family sees
was checked against real catalog prices and declared allergen data, which is
the trust wedge incumbents (venue directories, DIY Pinterest planning) lack.

Take rate: **15% vendor-side** at launch (`COMMISSION_RATE` in config).
Service-marketplace benchmarks run 15–30% (median 20–30%; Airbnb standardized
15.5% host-side in 2025). Launching at the low end is deliberate: supply
density beats margin until liquidity is proven. Fee is disclosed in-product in
the booking modal — never a markup on the family's verified price.

## Market

- US party & event planners: ~$1.7B (2025); broader party industry ~$11.4B.
- Average US kids party spend: $200–500 (home $100–300, venue $300–800);
  common quoted average ~$450–500.
- Wedge (from Round-3 affordability data): the $301–800 band is where 50%+ of
  requests verify AND where families actually plan — that band is the
  serviceable beachhead. The <$300 band needs cheaper vendor SKUs first
  (budget cake, bulk supplies) — vendor recruitment priority #1.

## Unit economics (pilot targets)

| Metric | Value | Basis |
|---|---|---|
| Avg GBV / booked party | $350–500 | request data + market avg |
| Take @15% | $52–75 / booking | config |
| Pilot goal (90 days) | 20 confirmed bookings, ≥10 active vendors, ~$8–10k GBV | YC-style liquidity proof |
| North-star metric | booking_interest_rate x plan verified rate | funnel, tracked in /events/summary |

Instrumented in code (not spreadsheet-ware):
- `/api/v1/bookings/summary`: `gbv_pipeline`, `commission_rate`,
  `est_take_revenue` — live GBV x take.
- `/api/v1/events/summary`: full funnel incl. `booking_interest_rate`.
- `/api/v1/vendors` + summary: supply-side lead count.

## GTM sequencing (YC: do things that don't scale)

1. Weeks 0–4 (existing playbook): 3 pilot vendors hand-onboarded via
   `load_catalog_csv`, 25 recruited parents, weekly funnel ritual.
2. Weeks 5–8: close the loop on booking_interest sessions by hand (concierge
   booking); measure request→confirmed conversion; recruit budget SKUs to
   attack the <$300 band.
3. Weeks 9–12: charge the fee on concierge bookings (manual invoice is fine —
   revenue proof precedes payments infra). Only then consider Stripe.

## Risks / honest limits

- Take-rate revenue here is *estimated pipeline*, not recognized revenue;
  nothing in the code processes payments yet.
- Vendor liquidity is the binding constraint (classic marketplace cold start);
  the product can verify plans it cannot yet fulfill.
- Fee wording in-product describes the intended model; first paid booking must
  come with vendor agreements (legal review before charging).

## Sources

- IBISWorld, Party & Event Planners in the US (2025 market size).
- Jobera / PartyGenius birthday industry statistics (2026 spend averages).
- Sharetribe / Origami / TechVinta marketplace take-rate benchmarks (2026).
- Airbnb 15.5% host-fee standardization (2025).
