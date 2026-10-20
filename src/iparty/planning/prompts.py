"""Prompt construction. The relevant slice of the catalog is injected so the
model SELECTS real, priced SKUs instead of inventing prices — and it starts
from the composer's verified Party Concept rather than a blank page."""
from __future__ import annotations

from ..pricing.catalog import Catalog, dietary_context
from .models import PlanDraft

SYSTEM_PROMPT = """You are iParty's creative director and party planner — for toddlers' first
birthdays, kids' and tweens' parties, teens' Sweet 16s and quinceañeras, adult
milestones, cultural celebrations, corporate events and luxury galas.

You design a PARTY CONCEPT, not a shopping list: one signature moment people will
talk about, a table that matches it, a sweet moment, a look, and a run of show.
You build it by SELECTING items from the provided catalog by their SKU. You never
invent prices — the system prices your selections from the catalog and verifies
every promise (budget, servings, place settings, allergens, certifications, ages).

Hard requirements:
- Choose exactly one venue SKU matching the location.
- Choose a MAIN course whose servings >= guest count (or a venue package that
  includes the meal), plus at least one place-setting (tableware) item that covers
  every guest.
- If dietary needs are given, choose only items that are safe for them (allergens,
  vegetarian/vegan, halal/kosher certification, no pork) and keep safe servings >=
  guest count. Kosher events also need the kosher supervision line item.
- Choose at least one age-appropriate activity; keep every item inside its age and
  guest-count ranges.
- Birthdays get a cake. Stay within budget. Provide >= 2 schedule slots in "HH:MM"
  24h order, non-overlapping.
- Keep the concept coherent: no cultural items unless the host asked for that
  culture, no adult-only items for children, no holiday items off-season.

Return ONLY JSON (no prose, no fences):
{
  "theme": str,
  "concept_name": str,            # 2-8 words, e.g. "Jurassic Dig · Walking dinosaur show"
  "story": str,                   # 2-4 sentences a host would read aloud
  "moments": [{"label": str, "text": str}],   # 3-6 beats: Signature, On the table, Sweet moment, The look, ...
  "venue_sku": str,
  "food": [{"sku": str, "quantity": int}],
  "supplies": [{"sku": str, "quantity": int}],
  "activities": [{"sku": str, "quantity": int}],
  "schedule": [{"start": "HH:MM", "end": "HH:MM", "activity": str}],
  "notes": str
}
"""


def catalog_table(request, catalog: Catalog, limit: int = 160) -> str:
    """The slice of the catalog worth showing for this request."""
    from .composer import catalog_slice

    rows = []
    for item in catalog_slice(request, catalog, limit=limit):
        allergens = ",".join(sorted(item.allergens)) or "none"
        facts = [item.category + ("/" + item.subcategory if item.subcategory else ""), f"{item.unit} ${item.unit_price:g}"]
        if item.serves:
            facts.append(f"serves={item.serves}")
        facts.append(f"allergens={allergens}")
        if not item.vegetarian:
            facts.append("non-veg")
        if item.certifications:
            facts.append("cert=" + ",".join(sorted(item.certifications)))
        if item.min_age > 0 or item.max_age < 120:
            facts.append(f"age {item.min_age}-{item.max_age}")
        if item.min_guests > 1 or item.max_guests < 500:
            facts.append(f"guests {item.min_guests}-{item.max_guests}")
        tags = sorted(t for t in item.tags if t.split(":")[0] in {"cuisine", "theme", "mood", "contains", "includes"} or t == "signature")
        if tags:
            facts.append(" ".join(tags))
        rows.append(f"{item.sku} | {item.name} | " + " | ".join(facts))
    return "\n".join(rows)


def _draft_json(draft: PlanDraft) -> str:
    return draft.model_dump_json(exclude_none=True)


def build_user_prompt(req, catalog: Catalog, baseline: PlanDraft | None = None, variant: int = 0) -> str:
    diet = dietary_context(req)
    diet_text = diet.text.strip() or "none"
    age_note = "a toddler" if req.honoree_age <= 4 else "a child" if req.honoree_age <= 12 else "a teen" if req.honoree_age <= 17 else "an adult"
    parts = [
        f"Plan a party for {req.honoree_name} ({age_note}, turning {req.honoree_age}).",
        f"- Date: {req.party_date.isoformat()}",
        f"- Guests: {req.guest_count}",
        f"- Budget (hard cap): ${req.budget:,.2f}",
        f"- Theme / occasion in the host's words: {req.theme or 'your choice — suggest one that fits'}",
        f"- Location: {req.location_type}",
        f"- Dietary needs to honor: {diet_text}",
        "",
        "CATALOG SLICE (sku | name | category/kind | unit price | facts):",
        catalog_table(req, catalog),
    ]
    if baseline is not None:
        parts += [
            "",
            "VERIFIED STARTING POINT — this concept already passes every check. Improve on it",
            f"(variant {variant}: make it more {'surprising' if variant % 2 else 'cohesive'}), swap items for better-fitting",
            "ones from the slice, and keep it verifiable. Return the full JSON, not a diff:",
            _draft_json(baseline),
        ]
    parts.append("\nReturn the JSON concept now.")
    return "\n".join(parts)
