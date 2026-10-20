#!/usr/bin/env python3
"""Print the Party Concept the composer builds for a request (or for every
MECE profile with --all). Handy while tuning affinity rules.

    python scripts/concept_debug.py "Dino Dig" 6 14 650 home
    python scripts/concept_debug.py --all
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from iparty.planning.composer import compose, profile_for  # noqa: E402
from iparty.planning.feasibility import minimum_feasible_budget  # noqa: E402
from iparty.planning.grounding import ground_draft  # noqa: E402
from iparty.planning.models import PartyRequest  # noqa: E402
from iparty.planning.verifier import verify_plan  # noqa: E402
from iparty.pricing.catalog import StaticCatalog  # noqa: E402

CAT = StaticCatalog()


def show(req: PartyRequest, variant: int = 0) -> None:
    p = profile_for(req)
    print(f"=== {req.theme!r} age {req.honoree_age} · {req.guest_count} guests · ${req.budget:,.0f} · {req.location_type} · diet {req.dietary_restrictions!r}")
    print(f"    band={p.band} occasion={p.occasion} birthday={p.birthday} tier={p.tier} moods={sorted(p.moods)} cuisines={p.cuisines}")
    print(f"    words={ {k: v for k, v in sorted(p.words.items(), key=lambda kv: -kv[1])[:12]} }")
    print(f"    floor=${minimum_feasible_budget(req, CAT)}")
    d = compose(req, CAT, variant=variant)
    if d is None:
        print("    NO CONCEPT")
        return
    plan = ground_draft(d, CAT, req.guest_count)
    rep = verify_plan(plan, req, CAT)
    print(f"    CONCEPT: {d.concept_name}")
    print(f"    STORY: {d.story}")
    for m in d.moments:
        print(f"      - {m.label.upper()}: {m.text}")
    for li in plan.line_items:
        print(f"      {li.category:10s} {li.subcategory:12s} {li.sku:28s} x{li.quantity:<3d} ${li.subtotal:>9,.2f}  {li.description}")
    print(f"    TOTAL ${plan.total_cost:,.2f} of ${req.budget:,.2f} · passed={rep.passed} {[v.code for v in rep.violations]}")
    for s in plan.schedule:
        print(f"      {s.start}-{s.end} {s.activity}")
    if d.notes:
        print(f"    NOTES: {d.notes}")


def main(argv: list[str]) -> int:
    future = date.today() + timedelta(days=30)
    if argv and argv[0] == "--all":
        from tests.mece_profiles import PROFILES_MECE, build_request
        for prof in PROFILES_MECE:
            try:
                req = build_request(prof)
            except Exception as exc:  # noqa: BLE001
                print(f"=== {prof['id']} invalid: {exc.__class__.__name__}")
                continue
            print(prof["id"], end=" ")
            show(req)
        return 0
    theme, age, guests, budget = argv[0], int(argv[1]), int(argv[2]), float(argv[3])
    loc = argv[4] if len(argv) > 4 else "home"
    diet = argv[5] if len(argv) > 5 else ""
    variant = int(argv[6]) if len(argv) > 6 else 0
    show(PartyRequest(honoree_name="Sam", honoree_age=age, party_date=future, guest_count=guests, budget=budget,
                      theme=theme, dietary_restrictions=diet, location_type=loc), variant)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))


def explain(req: PartyRequest, slot: str, course: str | None = None, top: int = 12) -> None:
    """Rank the candidates for one slot the way the composer sees them."""
    from iparty.planning.composer import _Composer, affinity, fit, theme_hits
    p = profile_for(req)
    c = _Composer(req, CAT, p, 0, False)
    if course:
        cands = c.of_course(course)
    elif slot == "venue":
        cands = c.venues
    elif slot in ("decor", "lighting", "favors", "tableware", "stationery", "rentals"):
        cands = [s for s in c.supplies if (s.is_tableware if slot == "tableware" else s.subcategory == slot)]
    else:
        cands = c.activities
    target = c.envelope.get(slot, 0.05 * c.budget)
    rows = []
    for it in cands:
        qty = c.qty_for(it)
        price = it.price_for(qty, c.guests)
        h = theme_hits(it, p.words)
        fp = fit(price, target, p.tier, p.band)
        if fp < 0 and h >= 1.0:
            fp *= 0.3 if h >= 1.6 else 0.5
        rows.append((affinity(it, p, slot) + fp, affinity(it, p, slot), fp, h, price, it.sku, it.name))
    rows.sort(key=lambda r: -r[0])
    print(f"--- slot {slot} target ${target:,.0f}")
    for r in rows[:top]:
        print(f"  {r[0]:6.2f} aff {r[1]:6.2f} fit {r[2]:6.2f} hits {r[3]:.1f} ${r[4]:>8,.0f} {r[5]:26s} {r[6]}")
