"""Prompt construction. The catalog is injected so the model SELECTS real,
priced SKUs instead of inventing prices."""
from __future__ import annotations

from ..pricing.catalog import Catalog

SYSTEM_PROMPT = """You are iParty's expert children's party planner.
You build a plan by SELECTING items from the provided catalog by their SKU.
You never invent prices — the system prices your selections from the catalog.

Hard requirements:
- Choose exactly one venue SKU matching the location.
- Choose food whose total servings >= guest count.
- If dietary restrictions are given, choose only items whose allergens do not
  conflict, and ensure safe servings >= guest count.
- Choose at least one age-appropriate activity and one supplies item.
- Provide >= 2 schedule slots in "HH:MM" 24h order, non-overlapping.

Return ONLY JSON (no prose, no fences):
{
  "theme": str,
  "venue_sku": str,
  "food": [{"sku": str, "quantity": int}],
  "supplies": [{"sku": str, "quantity": int}],
  "activities": [{"sku": str, "quantity": int}],
  "schedule": [{"start": "HH:MM", "end": "HH:MM", "activity": str}],
  "notes": str
}
"""


def _catalog_table(catalog: Catalog) -> str:
    rows = []
    for item in catalog.all():
        allergens = ",".join(sorted(item.allergens)) or "none"
        rows.append(
            f"{item.sku} | {item.category} | {item.name} | {item.unit} "
            f"${item.unit_price} | serves={item.serves} | allergens={allergens} "
            f"| age {item.min_age}-{item.max_age}"
        )
    return "\n".join(rows)


def build_user_prompt(req, catalog: Catalog) -> str:
    diet = req.dietary_restrictions.strip() or "none"
    return (
        f"Plan a birthday party.\n"
        f"- Honoree: {req.honoree_name}, turning {req.honoree_age}\n"
        f"- Date: {req.party_date.isoformat()}\n"
        f"- Guests: {req.guest_count}\n"
        f"- Budget (hard cap): ${req.budget:,.2f}\n"
        f"- Theme: {req.theme or 'your choice'}\n"
        f"- Location: {req.location_type}\n"
        f"- Starts at {getattr(req, 'start_time', '14:00')} for "
        f"{getattr(req, 'duration_hours', 2.5)} hours (schedule must fit this window)\n"
        f"- Dietary restrictions: {diet}\n"
        f"- Special requests: {getattr(req, 'special_requests', '') or 'none'}\n\n"
        f"CATALOG (sku | category | name | unit price | serves | allergens | age):\n"
        f"{_catalog_table(catalog)}\n\n"
        f"Return the JSON selection now."
    )
