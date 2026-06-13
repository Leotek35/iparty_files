"""Ground a PlanDraft (choices) into a priced PartyPlan using the catalog.

This is the step that makes prices real: every line item's price is read from
the catalog, never from the model. Unknown SKUs are dropped here and caught by
the verifier's realizability check.
"""
from __future__ import annotations

from ..pricing.catalog import Catalog
from .models import LineItem, MenuItem, PartyPlan, PlanDraft


def ground_draft(draft: PlanDraft, catalog: Catalog, guests: int) -> PartyPlan:
    line_items: list[LineItem] = []
    menu: list[MenuItem] = []
    supplies_labels: list[str] = []
    activity_labels: list[str] = []

    def add(sku: str, quantity: int) -> None:
        item = catalog.get(sku)
        if item is None:
            # Unknown SKU -> realizability violation will fire in the verifier.
            line_items.append(LineItem(sku=sku, category="extras",
                                       description=f"UNKNOWN SKU {sku}", quantity=quantity,
                                       unit_price=0.0, subtotal=0.0))
            return
        price = item.price_for(quantity, guests)
        line_items.append(LineItem(sku=item.sku, category=item.category,
                                   description=item.name, quantity=quantity,
                                   unit_price=item.unit_price, subtotal=price))
        if item.category == "food":
            menu.append(MenuItem(sku=item.sku, name=item.name,
                                 servings=item.servings_for(quantity, guests),
                                 allergens=sorted(item.allergens), vegetarian=item.vegetarian))
        elif item.category == "supplies":
            supplies_labels.append(item.name)
        elif item.category == "activities":
            activity_labels.append(item.name)

    add(draft.venue_sku, 1)
    for s in draft.food:
        add(s.sku, s.quantity)
    for s in draft.supplies:
        add(s.sku, s.quantity)
    for s in draft.activities:
        add(s.sku, s.quantity)

    venue_item = catalog.get(draft.venue_sku)
    return PartyPlan(
        theme=draft.theme,
        venue=venue_item.name if venue_item else draft.venue_sku,
        line_items=line_items,
        menu=menu,
        schedule=draft.schedule,
        activities=activity_labels or [s.activity for s in draft.schedule],
        supplies=supplies_labels,
        notes=draft.notes,
    )
