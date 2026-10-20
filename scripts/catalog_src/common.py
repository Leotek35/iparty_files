"""Compact item constructor shared by the catalog source tables.

Every item is one call. Prices are representative US market rates for 2026
(see docs/CATALOG.md for the research basis per subcategory); `basis` records
whether a price is research-derived, a vendor quote, or a legacy fixture.

Tag vocabulary (space-separated in `tags`):
  seg:toddler|kids|tween|teen|adult|all   who the item is for (band gate)
  cuisine:<key>                            cultural / culinary identity
  theme:<themes.json id>                   a themed product for one palette
  mood:<word>                              elegant, playful, glow, cozy, outdoor,
                                           winter, brunch, evening, wellness, nerdy,
                                           retro, wild, sporty, festive
  style:<word>                             diy, station, buffet, plated, kit,
                                           rental, included, shared, formal
  signature                                can anchor a concept on its own
  contains:pork|beef|alcohol               ingredient facts the verifier can act on
  niche / niche:adult                      never without a theme hit (adult-only)
  needs:<word>                             only when the theme says <word>
  for:<need>                               built for a dietary need (gluten_free,
                                           vegan, vegetarian, nut_free, kosher, halal)
  includes:main                            a venue package that feeds everyone
  nut_free_kitchen                         prepared in a nut-free facility
"""
from __future__ import annotations

ALL_LOC = "home;venue;park;restaurant"
VENUE_ONLY = "venue"
OUTDOOR = "home;park;venue"
INDOOR = "home;venue;restaurant"

SOURCES = {
    "venue": ["Peerspace & Tagvenue 2025-26 hourly medians", "Yelp venue listings", "The Knot 2025 venue report"],
    "food": ["Catering quotes (ezCater, CaterCow 2025-26)", "Thumbtack catering price guide 2026", "local caterer menus"],
    "cake": ["Bakery price sheets 2025-26", "Thumbtack custom cake guide"],
    "supplies": ["Party City / Amazon 2026 list prices", "rental company price lists (Peerspace vendors)"],
    "activities": ["GigSalad & The Bash 2025-26 booking averages", "Thumbtack entertainer guides", "rental company price lists"],
}


def item(sku: str, cat: str, sub: str, name: str, price: float, unit: str = "flat", *, serves: int = 0,
         al: str = "", veg: bool = True, age: str = "0-120", loc: str = ALL_LOC, tier: str = "standard",
         tags: str = "", certs: str = "", guests: str = "1-500", lead: int = 0, desc: str = "",
         basis: str = "research") -> dict:
    lo, hi = (int(x) for x in age.split("-"))
    glo, ghi = (int(x) for x in guests.split("-"))
    tag_set = sorted(set(tags.split()))
    if not any(t.startswith("seg:") for t in tag_set):
        tag_set = sorted({*tag_set, "seg:all"})
    return {
        "sku": sku, "category": cat, "subcategory": sub, "name": name, "description": desc,
        "unit": unit, "unit_price": float(price), "serves": int(serves),
        "allergens": sorted({a.strip() for a in al.split(",") if a.strip()}),
        "vegetarian": bool(veg), "min_age": lo, "max_age": hi,
        "location_types": sorted({x.strip() for x in loc.split(";") if x.strip()}),
        "tier": tier, "tags": tag_set,
        "certifications": sorted({c.strip() for c in certs.split(",") if c.strip()}),
        "min_guests": glo, "max_guests": ghi, "lead_days": int(lead),
        "price_basis": basis,
        "sources": SOURCES["cake" if sub == "cake" else cat],
    }
