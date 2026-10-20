#!/usr/bin/env python3
"""Build catalog v2 (src/iparty/pricing/data/catalog_v2.json) from the source
tables in scripts/catalog_src/.

    python scripts/build_catalog.py           # regenerate the JSON
    python scripts/build_catalog.py --check   # exit 1 if the JSON is stale

The JSON is what ships; the tables are how it is edited. A post-pass fills in
ingredient facts the verifier relies on (contains:pork / contains:beef) from
names and descriptions so a forgotten tag can never make a 'no pork' plan look
verified, and the validator rejects anything the engine could not reason about
(unknown allergen keys, courses, segments, theme ids).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from catalog_src.activities import ACTIVITIES  # noqa: E402
from catalog_src.food_mains import MAINS  # noqa: E402
from catalog_src.food_more import MORE  # noqa: E402
from catalog_src.supplies import SUPPLIES  # noqa: E402
from catalog_src.venues import VENUES  # noqa: E402

OUT = ROOT / "src" / "iparty" / "pricing" / "data" / "catalog_v2.json"
PALETTES = ROOT / "src" / "iparty" / "pricing" / "data" / "palettes.json"
THEMES = ROOT / "web" / "themes.json"

ALLERGENS = {"milk", "egg", "peanut", "tree_nut", "soy", "wheat", "fish", "shellfish", "sesame"}
COURSES = {"main", "side", "snack", "dessert", "cake", "drink"}
UNITS = {"per_person", "flat", "per_hour", "each"}
TIERS = {"essential", "standard", "premium", "luxury"}
SEGMENTS = {"seg:toddler", "seg:kids", "seg:tween", "seg:teen", "seg:adult", "seg:all"}
CERTS = {"halal", "kosher"}
LOCATIONS = {"home", "venue", "park", "restaurant"}

# Ingredient facts inferred from words in the name/description (post-pass).
PORK_WORDS = re.compile(r"\b(pork|bacon|ham|prosciutto|jam[oó]n|chorizo|sausage|brat(wurst)?s?|lech[oó]n|carnitas|al pastor|pepperoni|salami|cured meats?|lorraine)\b", re.I)
BEEF_WORDS = re.compile(r"\b(beef|steak|brisket|burgers?|barbacoa|asada|koobideh|bulgogi|prime rib|sliders?|lasagna|meatballs?|suya|ćevapi|boerewors)\b", re.I)
ALCOHOL_WORDS = re.compile(r"\b(wine|beer|cocktails?|champagne|sake|whisky|spirits|open bar|mimosa)\b", re.I)

# Items whose words would mislead the inference (vegetarian 'sausage', 'beer-cheese' with alcohol cooked off, ...).
NO_INFER = {"FD-PRETZEL-BITES", "FD-BBQ-VEGAN", "FD-VEGAN-FEAST", "FD-SLIDER-TRIO", "FD-WAFFLE-STATION", "FD-COOKIE-DECORATING"}


def _apply_post_pass(items: list[dict]) -> None:
    for it in items:
        tags = set(it["tags"])
        if it["category"] == "food" and it["sku"] not in NO_INFER:
            text = f"{it['name']} {it['description']}"
            if PORK_WORDS.search(text):
                tags.add("contains:pork")
            if BEEF_WORDS.search(text):
                tags.add("contains:beef")
        if (it["category"] in {"food", "venue", "activities"} and it["sku"] not in NO_INFER
                and it["subcategory"] in {"drink", "workshop", "staffing", "rooftop", "taproom", "garden", "restaurant"}
                and ALCOHOL_WORDS.search(f"{it['name']} {it['description']}")):
            tags.add("contains:alcohol")
        if tags & {"contains:pork", "contains:beef"}:
            it["vegetarian"] = False
        it["tags"] = sorted(tags)


def _validate(items: list[dict], theme_ids: set[str]) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for it in items:
        sku = it["sku"]
        if sku in seen:
            errors.append(f"{sku}: duplicate SKU")
        seen.add(sku)
        if it["category"] not in {"venue", "food", "supplies", "activities"}:
            errors.append(f"{sku}: bad category {it['category']}")
        if it["unit"] not in UNITS:
            errors.append(f"{sku}: bad unit {it['unit']}")
        if it["tier"] not in TIERS:
            errors.append(f"{sku}: bad tier {it['tier']}")
        if set(it["allergens"]) - ALLERGENS:
            errors.append(f"{sku}: unknown allergens {sorted(set(it['allergens']) - ALLERGENS)}")
        if set(it["certifications"]) - CERTS:
            errors.append(f"{sku}: unknown certifications {it['certifications']}")
        if set(it["location_types"]) - LOCATIONS or not it["location_types"]:
            errors.append(f"{sku}: bad location_types {it['location_types']}")
        if it["category"] == "food" and it["subcategory"] not in COURSES:
            errors.append(f"{sku}: food subcategory must be a course, got {it['subcategory']}")
        if it["category"] == "food" and it["serves"] <= 0:
            errors.append(f"{sku}: food must declare serves > 0")
        if it["min_age"] > it["max_age"] or it["min_guests"] > it["max_guests"]:
            errors.append(f"{sku}: inverted age/guest range")
        if it["unit_price"] < 0:
            errors.append(f"{sku}: negative price")
        segs = {t for t in it["tags"] if t.startswith("seg:")}
        if not segs or segs - SEGMENTS:
            errors.append(f"{sku}: bad segment tags {sorted(segs)}")
        for t in it["tags"]:
            if t.startswith("theme:") and t[6:] not in theme_ids:
                errors.append(f"{sku}: unknown theme id {t[6:]!r}")
            if ":" in t and t.split(":", 1)[0] not in {"seg", "cuisine", "theme", "mood", "style", "contains", "niche", "needs", "for", "includes"}:
                errors.append(f"{sku}: unknown tag family {t!r}")
        if it["category"] == "food" and not it["vegetarian"] and "for:vegetarian" in it["tags"]:
            errors.append(f"{sku}: non-vegetarian item tagged for:vegetarian")
        if "contains:pork" in it["tags"] and it["certifications"]:
            errors.append(f"{sku}: certified item contains pork")
        if it["category"] == "supplies" and it["subcategory"] == "tableware" and it["unit"] == "flat" and it["serves"] <= 0:
            errors.append(f"{sku}: flat tableware must declare settings via serves")
    return errors


def build() -> dict:
    items = [*VENUES, *MAINS, *MORE, *SUPPLIES, *ACTIVITIES]
    _apply_post_pass(items)
    theme_ids = {t["id"] for t in json.loads(THEMES.read_text(encoding="utf-8"))["themes"]}
    errors = _validate(items, theme_ids)
    if errors:
        raise SystemExit("catalog validation failed:\n  " + "\n  ".join(errors))
    counts: dict[str, int] = {}
    for it in items:
        counts[it["category"]] = counts.get(it["category"], 0) + 1
    return {
        "version": 2,
        "note": "Generated by scripts/build_catalog.py from scripts/catalog_src/ — edit the tables, not this file.",
        "counts": counts,
        "items": items,
    }


def render(doc: dict) -> str:
    return json.dumps(doc, ensure_ascii=False, indent=1, sort_keys=False) + "\n"


def palettes() -> str:
    """The palette vocabulary the composer matches themed products against —
    a projection of web/themes.json so the engine never reads the web folder."""
    themes = json.loads(THEMES.read_text(encoding="utf-8"))["themes"]
    rows = [{"id": t["id"], "band": t["band"], "keywords": t["keywords"]} for t in themes]
    return json.dumps({"note": "Generated from web/themes.json by scripts/build_catalog.py", "palettes": rows},
                      ensure_ascii=False, indent=1) + "\n"


def main(argv: list[str]) -> int:
    doc = build()
    text = render(doc)
    pal = palettes()
    if "--check" in argv:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        current_pal = PALETTES.read_text(encoding="utf-8") if PALETTES.exists() else ""
        if current != text or current_pal != pal:
            print(f"STALE: {OUT.parent} differs from the source tables — run `make catalog`.")
            return 1
        print(f"ok: {OUT} is up to date ({len(doc['items'])} items)")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    PALETTES.write_text(pal, encoding="utf-8")
    print(f"wrote {OUT}: {len(doc['items'])} items {doc['counts']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
