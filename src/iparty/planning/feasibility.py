"""Cheapest compliant plan — used to (a) tell users the minimum viable budget,
(b) give the composer a floor it must stay above, and (c) give every backend a
guaranteed-valid fallback. 'Compliant' now means a real meal: a main course
(or a venue package that includes one) for every guest, a place setting each,
an age-appropriate activity, and certified food where the request asks for it."""
from __future__ import annotations

from ..pricing.catalog import Catalog, CatalogItem, DietContext, dietary_context
from .models import PlanDraft, ScheduleSlot, Selection

KOSHER_SUPERVISION_SKU = "ACT-KOSHER-SUPERVISION"


def _default_schedule(theme: str) -> list[ScheduleSlot]:
    return [
        ScheduleSlot(start="14:00", end="14:30", activity="Guests arrive & welcome"),
        ScheduleSlot(start="14:30", end="15:30", activity=f"{theme} games & activities"),
        ScheduleSlot(start="15:30", end="16:00", activity="Cake & singing"),
        ScheduleSlot(start="16:00", end="16:30", activity="Free play & goodbyes"),
    ]


def units_to_cover(item: CatalogItem, guests: int) -> int:
    """How many units of a flat item feed / seat `guests` (per_person: 1)."""
    if item.unit == "per_person":
        return 1
    per_unit = max(1, item.serves)
    return max(1, -(-guests // per_unit))


def cost_per_cover(item: CatalogItem, guests: int) -> float:
    units = units_to_cover(item, guests)
    covered = max(1, item.servings_for(units, guests) if item.category == "food" else item.settings_for(units, guests))
    return item.price_for(units, guests) / covered


def eligible(request, catalog: Catalog, diet: DietContext | None = None) -> dict:
    """Everything the request may buy, by slot, before any taste is applied."""
    diet = diet or dietary_context(request)
    guests, age, loc = request.guest_count, request.honoree_age, request.location_type

    def ok(item: CatalogItem) -> bool:
        return (item.min_age <= age <= item.max_age and item.within_capacity(guests)
                and loc in item.location_types)

    venues = [v for v in catalog.by_category("venue") if ok(v) and diet.venue_ok(v)]
    foods = [f for f in catalog.by_category("food") if ok(f) and f.serves > 0 and diet.safe(f)]
    supplies = [s for s in catalog.by_category("supplies") if ok(s)]
    activities = [a for a in catalog.by_category("activities") if ok(a)]
    return {
        "diet": diet,
        "venues": venues,
        "mains": [f for f in foods if f.course == "main" and "style:included" not in f.tags],
        "foods": foods,
        "tableware": [s for s in supplies if s.is_tableware],
        "supplies": supplies,
        "activities": [a for a in activities if not a.is_service],
        "services": [a for a in activities if a.is_service],
    }


def cheapest_compliant_draft(request, catalog: Catalog) -> PlanDraft | None:
    """Build the lowest-cost draft that satisfies all non-budget constraints."""
    guests = request.guest_count
    pool = eligible(request, catalog)
    diet: DietContext = pool["diet"]
    if diet.unverifiable:
        return None

    venues = pool["venues"]
    if not venues:
        return None  # nothing at that location holds this many — an honest refusal, not a broken plan
    # Cheapest venue; a package that includes the meal competes on its total.
    venue = min(venues, key=lambda v: (v.price_for(1, guests), v.sku))

    food_sel: list[Selection] = []
    if "includes:main" not in venue.tags:
        mains = pool["mains"]
        if not mains:
            return None
        main = min(mains, key=lambda i: (cost_per_cover(i, guests), i.sku))
        food_sel.append(Selection(sku=main.sku, quantity=units_to_cover(main, guests)))

    tableware = pool["tableware"]
    if not tableware:
        return None
    sup = min(tableware, key=lambda s: (cost_per_cover(s, guests), s.sku))
    sup_sel = [Selection(sku=sup.sku, quantity=units_to_cover(sup, guests))]

    acts = pool["activities"]
    if not acts:
        return None
    act = min(acts, key=lambda i: (i.price_for(1, guests), i.sku))
    act_sel = [Selection(sku=act.sku, quantity=1)]
    if "kosher" in diet.certifications:
        sup_item = catalog.get(KOSHER_SUPERVISION_SKU)
        if sup_item is None:
            return None
        act_sel.append(Selection(sku=sup_item.sku, quantity=1))

    theme = request.theme or "Celebration"
    return PlanDraft(
        theme=theme, venue_sku=venue.sku,
        food=food_sel, supplies=sup_sel, activities=act_sel,
        schedule=_default_schedule(theme),
        notes=(f"Checked for: {diet.text}." if diet.any else ""),
    )


def draft_cost(draft: PlanDraft, catalog: Catalog, guests: int) -> float:
    total = 0.0
    venue = catalog.get(draft.venue_sku)
    if venue:
        total += venue.price_for(1, guests)
    for sel_list in (draft.food, draft.supplies, draft.activities):
        for s in sel_list:
            item = catalog.get(s.sku)
            if item:
                total += item.price_for(s.quantity, guests)
    return round(total, 2)


def minimum_feasible_budget(request, catalog: Catalog) -> float | None:
    draft = cheapest_compliant_draft(request, catalog)
    if draft is None:
        return None
    return draft_cost(draft, catalog, request.guest_count)
