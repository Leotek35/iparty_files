"""Grounded pricing + allergen catalog — the source of truth for realizability.

The core fix to the "hallucinated prices" problem: the language model never sets
prices. It *selects* catalog SKUs; the system prices them from this catalog. A
plan is therefore "budget-valid" only if it is **buyable** from real, priced
inventory. Swap `StaticCatalog` for a live vendor/pricing API behind the same
`Catalog` protocol and nothing else changes.

Prices are representative US market rates (2025–2026) for a children's party and
are intentionally conservative. Allergen data uses the FDA "big-9" allergens.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol

Category = Literal["venue", "food", "supplies", "activities"]

# FDA big-9 allergens
ALLERGENS = frozenset(
    {"milk", "egg", "peanut", "tree_nut", "soy", "wheat", "fish", "shellfish", "sesame"}
)


@dataclass(frozen=True)
class CatalogItem:
    sku: str
    category: Category
    name: str
    unit: Literal["per_person", "flat", "per_hour", "each"]
    unit_price: float
    serves: int = 0                      # servings produced per unit (food only)
    allergens: frozenset[str] = field(default_factory=frozenset)
    vegetarian: bool = True
    min_age: int = 0
    max_age: int = 120
    location_types: frozenset[str] = field(
        default_factory=lambda: frozenset({"home", "venue", "park", "restaurant"})
    )

    def price_for(self, quantity: int, guests: int) -> float:
        if self.unit == "per_person":
            return round(self.unit_price * guests, 2)
        return round(self.unit_price * quantity, 2)

    def servings_for(self, quantity: int, guests: int) -> int:
        if self.category != "food":
            return 0
        if self.unit == "per_person":
            return guests * max(1, self.serves or 1)
        return self.serves * quantity


class Catalog(Protocol):
    def all(self) -> list[CatalogItem]: ...
    def get(self, sku: str) -> CatalogItem | None: ...
    def by_category(self, category: Category) -> list[CatalogItem]: ...


_ITEMS: list[CatalogItem] = [
    # --- venues ---
    CatalogItem("VEN-HOME", "venue", "Home / backyard setup", "flat", 0.0,
                location_types=frozenset({"home"})),
    CatalogItem("VEN-PARK", "venue", "Park pavilion permit", "flat", 75.0,
                location_types=frozenset({"park"})),
    CatalogItem("VEN-KIDS", "venue", "Kids party venue (2 hr)", "flat", 350.0,
                location_types=frozenset({"venue"})),
    CatalogItem("VEN-REST", "venue", "Restaurant party room", "per_person", 22.0,
                location_types=frozenset({"restaurant"})),
    # --- food (serves = servings per unit) ---
    CatalogItem("FD-PIZZA", "food", "Pizza (per person)", "per_person", 4.50, serves=1,
                allergens=frozenset({"wheat", "milk"})),
    CatalogItem("FD-SANDW", "food", "Sandwich platter (per person)", "per_person", 6.00, serves=1,
                allergens=frozenset({"wheat", "milk", "egg"})),
    CatalogItem("FD-VEGGIE", "food", "Fruit & veggie platter (serves 12)", "flat", 38.0, serves=12,
                allergens=frozenset()),
    CatalogItem("FD-CAKE", "food", "Birthday cake (serves 20)", "flat", 45.0, serves=20,
                allergens=frozenset({"wheat", "egg", "milk"})),
    CatalogItem("FD-CAKE-GF", "food", "Gluten-free cake (serves 20)", "flat", 62.0, serves=20,
                allergens=frozenset({"egg", "milk"})),
    CatalogItem("FD-CAKE-VG", "food", "Vegan GF cake (serves 16)", "flat", 70.0, serves=16,
                allergens=frozenset()),
    CatalogItem("FD-FRUIT", "food", "Fruit cups (per person)", "per_person", 2.25, serves=1,
                allergens=frozenset()),
    CatalogItem("FD-PBJ", "food", "PB&J sandwiches (serves 10)", "flat", 18.0, serves=10,
                allergens=frozenset({"peanut", "wheat"})),  # deliberately allergen-heavy
    CatalogItem("FD-CATER", "food", "Premium catering buffet (per person)", "per_person", 24.0, serves=1,
                allergens=frozenset({"milk", "wheat", "egg", "soy"}), vegetarian=False),
    # --- supplies ---
    CatalogItem("SUP-BASIC", "supplies", "Basic party pack (16 place settings)", "flat", 35.0, serves=16),
    CatalogItem("SUP-DELUXE", "supplies", "Deluxe themed pack (24 settings)", "flat", 65.0, serves=24),
    CatalogItem("SUP-TABLE", "supplies", "Tableware (per person)", "per_person", 2.25),
    CatalogItem("SUP-DECOR", "supplies", "Balloon & decoration kit", "flat", 40.0),
    CatalogItem("SUP-ECO", "supplies", "Compostable eco tableware (per person)", "per_person", 3.0),
    CatalogItem("SUP-PAPER", "supplies", "Simple paper tableware (per person)", "per_person", 1.25),
    CatalogItem("SUP-FAVOR", "supplies", "Party favor gift bags (per person)", "per_person", 8.0),
    # --- activities ---
    CatalogItem("ACT-CLASSIC", "activities", "Classic party games kit (printables & prizes)", "flat", 12.0),
    CatalogItem("ACT-GAMES", "activities", "DIY games & favors kit", "flat", 45.0),
    CatalogItem("ACT-SENSORY", "activities", "Soft-play & sensory corner (babies)", "flat", 80.0, max_age=3),
    CatalogItem("ACT-KARAOKE", "activities", "Karaoke setup (3 hr)", "flat", 120.0, min_age=8),
    CatalogItem("ACT-TRIVIA", "activities", "Trivia & quiz night kit", "flat", 60.0, min_age=12),
    CatalogItem("ACT-PHOTO", "activities", "Photo booth rental (2 hr)", "flat", 200.0, min_age=5),
    CatalogItem("ACT-DJ", "activities", "DJ + sound system (3 hr)", "flat", 300.0, min_age=10),
    CatalogItem("ACT-CHAR", "activities", "Costumed character visit (1 hr)", "flat", 175.0, min_age=2, max_age=10),
    CatalogItem("ACT-STEM", "activities", "Science experiments station", "flat", 110.0, min_age=5),
    CatalogItem("ACT-PHOTOG", "activities", "Event photographer (per hour)", "per_hour", 150.0),
    CatalogItem("ACT-BOUNCE", "activities", "Bounce house rental", "flat", 180.0, min_age=3, max_age=12),
    CatalogItem("ACT-FACE", "activities", "Face painter (2 hr)", "flat", 150.0, min_age=2),
    CatalogItem("ACT-MAGIC", "activities", "Magician (1 hr)", "per_hour", 250.0, min_age=4),
    CatalogItem("ACT-CRAFT", "activities", "Craft station", "flat", 90.0, min_age=3),
]


class StaticCatalog:
    """Default in-repo catalog. Replace with a live vendor API behind `Catalog`."""

    def __init__(self, items: list[CatalogItem] | None = None) -> None:
        self._items = items or list(_ITEMS)
        self._by_sku = {i.sku: i for i in self._items}

    def all(self) -> list[CatalogItem]:
        return list(self._items)

    def get(self, sku: str) -> CatalogItem | None:
        return self._by_sku.get(sku)

    def by_category(self, category: Category) -> list[CatalogItem]:
        return [i for i in self._items if i.category == category]


def load_catalog_csv(path: "str | Path") -> "StaticCatalog":
    """Vendor onboarding without code: build a catalog from a CSV.

    Columns: sku,category,name,unit,unit_price,serves,allergens,vegetarian,
             min_age,max_age,location_types
    allergens: semicolon-separated FDA big-9 keys (blank = none)
    location_types: semicolon-separated (blank = all)
    Unknown allergen keys raise immediately — a typo in safety data must fail
    loudly at load time, never silently at verify time.
    """
    import csv
    from pathlib import Path as _Path

    items: list[CatalogItem] = []
    with _Path(path).open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            allergens = frozenset(a.strip() for a in row.get("allergens", "").split(";") if a.strip())
            unknown = allergens - ALLERGENS
            if unknown:
                raise ValueError(f"SKU {row['sku']}: unknown allergen keys {sorted(unknown)}; "
                                 f"allowed: {sorted(ALLERGENS)}")
            locs = frozenset(x.strip() for x in row.get("location_types", "").split(";") if x.strip())
            items.append(CatalogItem(
                sku=row["sku"].strip(), category=row["category"].strip(),  # type: ignore[arg-type]
                name=row["name"].strip(), unit=row["unit"].strip(),        # type: ignore[arg-type]
                unit_price=float(row["unit_price"]),
                serves=int(row.get("serves") or 0),
                allergens=allergens,
                vegetarian=(row.get("vegetarian", "true").strip().lower() != "false"),
                min_age=int(row.get("min_age") or 0),
                max_age=int(row.get("max_age") or 120),
                location_types=locs or frozenset({"home", "venue", "park", "restaurant"}),
            ))
    if not items:
        raise ValueError(f"catalog CSV {path} contained no items")
    return StaticCatalog(items)


# Map free-text dietary restrictions to allergens that MUST be excluded.
_RESTRICTION_TO_ALLERGENS = {
    "nut": {"peanut", "tree_nut"}, "peanut": {"peanut"}, "tree nut": {"tree_nut"},
    "gluten": {"wheat"}, "wheat": {"wheat"}, "celiac": {"wheat"},
    "dairy": {"milk"}, "milk": {"milk"}, "lactose": {"milk"},
    "egg": {"egg"}, "soy": {"soy"}, "fish": {"fish"}, "shellfish": {"shellfish"},
    "sesame": {"sesame"},
    # Common non-English / colloquial aliases — a safety parser must meet
    # people in their own words. (Substring-matched, lowercase.)
    "laktose": {"milk"}, "lattosio": {"milk"}, "sin lacteos": {"milk"},
    "glutine": {"wheat"}, "glúten": {"wheat"}, "麩質": {"wheat"}, "グルテン": {"wheat"},
    "arachide": {"peanut"}, "maní": {"peanut"}, "erdnuss": {"peanut"},
    "cacahuete": {"peanut"}, "🥜": {"peanut", "tree_nut"},
    "sesam": {"sesame"}, "sésamo": {"sesame"},
}


def parse_forbidden_allergens(restrictions: str) -> set[str]:
    text = (restrictions or "").lower()
    forbidden: set[str] = set()
    for key, allergens in _RESTRICTION_TO_ALLERGENS.items():
        if key in text:
            forbidden |= allergens
    # Vegan excludes all animal-derived allergen categories we track. (Within
    # this catalog's taxonomy that is milk, egg, fish, shellfish; honey/gelatin
    # would need explicit item flags in a richer catalog.)
    if "vegan" in text:
        forbidden |= {"milk", "egg", "fish", "shellfish"}
    return forbidden


def requires_vegetarian(restrictions: str) -> bool:
    """Vegetarian menu required. Kosher/halal/jain are honored with a vegetarian
    menu as the safe approximation (no mixed/uncertified meat); pescatarian is
    satisfied by a vegetarian menu too (fish optional, never required)."""
    text = (restrictions or "").lower()
    return any(k in text for k in
               ("vegetarian", "vegan", "kosher", "halal", "jain", "pescatarian",
                "végétalien", "vegetalien", "халяль", "حلال", "코셔", "כשר"))


# Every keyword the dietary parser understands and acts on.
_KNOWN_DIET_KEYWORDS = tuple(_RESTRICTION_TO_ALLERGENS) + (
    "vegan", "vegetarian", "kosher", "halal", "jain", "pescatarian",
    "végétalien", "vegetalien", "халяль", "حلال", "코셔", "כשר",
    "allerg", "intoleran", "free", "frei", "none", "no ",
)


def unrecognized_restrictions(restrictions: str) -> list[str]:
    """Phrases in the dietary text the system cannot verify against the catalog.
    These must be surfaced honestly, never silently dropped."""
    text = (restrictions or "").strip().lower()
    if not text:
        return []
    import re as _re
    phrases = [p.strip(" .!") for p in _re.split(r"[,;]| and | plus |\n", text) if p.strip(" .!")]
    unknown = []
    for ph in phrases:
        if not any(k in ph for k in _KNOWN_DIET_KEYWORDS):
            unknown.append(ph[:60])
    return unknown
