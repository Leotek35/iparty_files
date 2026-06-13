"""Cheapest compliant plan — used to (a) tell users the minimum viable budget,
and (b) give the mock/LLM a guaranteed-valid fallback to select from."""
from __future__ import annotations

from ..pricing.catalog import Catalog, parse_forbidden_allergens, requires_vegetarian
from .models import PlanDraft, ScheduleSlot, Selection


def _default_schedule(theme: str) -> list[ScheduleSlot]:
    return [
        ScheduleSlot(start="14:00", end="14:30", activity="Guests arrive & welcome"),
        ScheduleSlot(start="14:30", end="15:30", activity=f"{theme} games & activities"),
        ScheduleSlot(start="15:30", end="16:00", activity="Cake & singing"),
        ScheduleSlot(start="16:00", end="16:30", activity="Free play & goodbyes"),
    ]


def cheapest_compliant_draft(request, catalog: Catalog) -> PlanDraft | None:
    """Build the lowest-cost draft that satisfies all non-budget constraints."""
    forbidden = parse_forbidden_allergens(request.dietary_restrictions)
    veg = requires_vegetarian(request.dietary_restrictions)
    guests = request.guest_count

    # venue: cheapest for the location
    venues = [v for v in catalog.by_category("venue")
              if request.location_type in v.location_types]
    if not venues:
        venues = catalog.by_category("venue")
    venue = min(venues, key=lambda i: i.price_for(1, guests))

    # food: cheapest safe items to cover guests by cost-per-safe-serving
    def safe(item) -> bool:
        if forbidden & item.allergens:
            return False
        if veg and not item.vegetarian:
            return False
        return True

    foods = [f for f in catalog.by_category("food") if safe(f) and f.serves > 0]
    if not foods:
        return None
    # cost per serving
    foods.sort(key=lambda i: i.price_for(1, guests) / max(1, i.servings_for(1, guests)))
    food_sel: list[Selection] = []
    cheapest = foods[0]
    per_unit_serv = max(1, cheapest.servings_for(1, guests))
    if cheapest.unit == "per_person":
        food_sel.append(Selection(sku=cheapest.sku, quantity=1))
    else:
        units = max(1, -(-guests // per_unit_serv))  # ceil
        food_sel.append(Selection(sku=cheapest.sku, quantity=units))

    # supplies: cheapest
    supplies = catalog.by_category("supplies")
    sup = min(supplies, key=lambda i: i.price_for(1, guests))
    # activities: cheapest age-appropriate
    acts = [a for a in catalog.by_category("activities")
            if a.min_age <= request.honoree_age <= a.max_age]
    if not acts:
        return None
    act = min(acts, key=lambda i: i.price_for(1, guests))

    theme = request.theme or "Celebration"
    return PlanDraft(
        theme=theme, venue_sku=venue.sku,
        food=food_sel, supplies=[Selection(sku=sup.sku, quantity=1)],
        activities=[Selection(sku=act.sku, quantity=1)],
        schedule=_default_schedule(theme),
        notes=(f"Allergen-safe for: {request.dietary_restrictions}." if forbidden or veg else ""),
    )


def minimum_feasible_budget(request, catalog: Catalog) -> float | None:
    draft = cheapest_compliant_draft(request, catalog)
    if draft is None:
        return None
    total = 0.0
    g = request.guest_count
    for sel_list in (draft.food, draft.supplies, draft.activities):
        for s in sel_list:
            item = catalog.get(s.sku)
            if item:
                total += item.price_for(s.quantity, g)
    venue = catalog.get(draft.venue_sku)
    if venue:
        total += venue.price_for(1, g)
    return round(total, 2)
