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
    # --- supplies ---
    CatalogItem("SUP-BASIC", "supplies", "Basic party pack (16 place settings)", "flat", 35.0, serves=16),
    CatalogItem("SUP-DELUXE", "supplies", "Deluxe themed pack (24 settings)", "flat", 65.0, serves=24),
    CatalogItem("SUP-TABLE", "supplies", "Tableware (per person)", "per_person", 2.25),
    CatalogItem("SUP-DECOR", "supplies", "Balloon & decoration kit", "flat", 40.0),
    # --- activities ---
    CatalogItem("ACT-GAMES", "activities", "DIY games & favors kit", "flat", 45.0),
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


# Map free-text dietary restrictions to allergens that MUST be excluded.
_RESTRICTION_TO_ALLERGENS = {
    "nut": {"peanut", "tree_nut"}, "peanut": {"peanut"}, "tree nut": {"tree_nut"},
    "gluten": {"wheat"}, "wheat": {"wheat"}, "celiac": {"wheat"},
    "dairy": {"milk"}, "milk": {"milk"}, "lactose": {"milk"},
    "egg": {"egg"}, "soy": {"soy"}, "fish": {"fish"}, "shellfish": {"shellfish"},
    "sesame": {"sesame"},
}


def parse_forbidden_allergens(restrictions: str) -> set[str]:
    text = (restrictions or "").lower()
    forbidden: set[str] = set()
    for key, allergens in _RESTRICTION_TO_ALLERGENS.items():
        if key in text:
            forbidden |= allergens
    return forbidden


def requires_vegetarian(restrictions: str) -> bool:
    text = (restrictions or "").lower()
    return "vegetarian" in text or "vegan" in text
