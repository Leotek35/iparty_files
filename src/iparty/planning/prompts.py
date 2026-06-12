"""Prompt construction for the planning LLM."""
from __future__ import annotations

from .models import PartyRequest

SYSTEM_PROMPT = """You are iParty's expert children's party planner.
You produce complete, budget-accurate party plans as STRICT JSON.

Hard requirements you MUST satisfy:
- The sum of every line_item (quantity * unit_cost) must be <= the stated budget.
- Include line_items in all of these categories: venue, food, supplies, activities.
- The menu's total servings must be >= the guest count.
- Provide at least 2 schedule slots in "HH:MM" 24h format, in order, non-overlapping.
- If dietary restrictions are given, tag compliant menu items and mention them in notes.
- Provide at least one activity appropriate to the honoree's age.

Output ONLY a JSON object with this exact shape (no prose, no markdown fences):
{
  "theme": str,
  "venue": str,
  "line_items": [{"category": "venue|food|supplies|activities|extras",
                   "description": str, "quantity": int, "unit_cost": number}],
  "menu": [{"name": str, "servings": int, "dietary_tags": [str]}],
  "schedule": [{"start": "HH:MM", "end": "HH:MM", "activity": str}],
  "activities": [str],
  "supplies": [str],
  "notes": str
}
"""


def build_user_prompt(req: PartyRequest) -> str:
    diet = req.dietary_restrictions.strip() or "none"
    return (
        f"Plan a birthday party.\n"
        f"- Honoree: {req.honoree_name}, turning {req.honoree_age}\n"
        f"- Date: {req.party_date.isoformat()}\n"
        f"- Guests: {req.guest_count}\n"
        f"- Budget (hard cap): ${req.budget:,.2f}\n"
        f"- Theme preference: {req.theme or 'planner''s choice'}\n"
        f"- Location: {req.location_type}\n"
        f"- Dietary restrictions: {diet}\n"
        f"Return the JSON plan now."
    )
