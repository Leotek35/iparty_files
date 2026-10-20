"""Constraint verifier — the ground-truth gate.

Grounded in the catalog: it checks realizability (every SKU is real and priced
at the catalog rate), budget, completeness, schedule, scaling (a real main
course and a place setting for every guest), capacity and billing minimums,
allergen safety against catalog allergen profiles, certifications (halal,
kosher — including supervision), ingredient promises (no pork), and
age-appropriateness of everything bought, not just the activities.
"""
from __future__ import annotations

from ..core.config import settings
from ..pricing.catalog import Catalog, dietary_context
from .feasibility import KOSHER_SUPERVISION_SKU
from .models import PartyPlan, PartyRequest, VerificationReport, Violation

BIRTHDAY_WORDS = ("birthday", "bday", "b-day", "sweet 16", "sweet sixteen", "quince", "turning")


def _parse_hhmm(s: str) -> int | None:
    try:
        h, m = s.split(":")
        return int(h) * 60 + int(m)
    except Exception:  # noqa: BLE001
        return None


def looks_like_birthday(request: PartyRequest) -> bool:
    theme = (request.theme or "").lower()
    if any(w in theme for w in BIRTHDAY_WORDS):
        return True
    import re
    if re.search(r"\b\d{1,3}(st|nd|rd|th)\b", theme):
        return True
    return not theme.strip()  # a blank theme on a 'turning N' request is a birthday


def verify_plan(plan: PartyPlan, request: PartyRequest, catalog: Catalog) -> VerificationReport:
    violations: list[Violation] = []
    checks: list[bool] = []
    guests = request.guest_count
    diet = dietary_context(request)

    def check(ok: bool, code: str, severity: str, message: str) -> None:
        checks.append(ok)
        if not ok:
            violations.append(Violation(code=code, severity=severity, message=message))  # type: ignore[arg-type]

    # 1. REALIZABILITY — every line item maps to a real SKU at the catalog price.
    realizable = True
    for li in plan.line_items:
        item = catalog.get(li.sku)
        if item is None:
            realizable = False
            check(False, "UNREALIZABLE_SKU", "error",
                  f"'{li.description}' ({li.sku}) is not a real catalog item.")
            continue
        expected = item.price_for(li.quantity, guests)
        if abs(expected - li.subtotal) > 0.01:
            realizable = False
            check(False, "PRICE_MISMATCH", "error",
                  f"'{item.name}' priced ${li.subtotal:.2f}, catalog says ${expected:.2f}.")
    check(realizable, "REALIZABLE", "error", "Plan contains items that cannot be bought as priced.")

    # 2. Budget ceiling (hard)
    total = plan.total_cost
    cap = request.budget * (1 + settings.BUDGET_TOLERANCE)
    check(total <= cap, "BUDGET_EXCEEDED", "error",
          f"Plan costs ${total:,.2f}, over the ${request.budget:,.2f} budget.")

    # 3. Budget floor (warn if suspiciously cheap)
    check(total >= request.budget * settings.BUDGET_FLOOR_FRACTION, "BUDGET_SUSPICIOUSLY_LOW",
          "warning", f"Plan uses only ${total:,.2f} of ${request.budget:,.2f}; may be incomplete.")

    # 4. Completeness
    cats = {li.category for li in plan.line_items}
    for required in ("venue", "food", "supplies", "activities"):
        check(required in cats, f"MISSING_{required.upper()}", "error",
              f"Plan is missing a '{required}' item.")

    # 4b. The venue must suit the place the host chose.
    venue_items = [catalog.get(li.sku) for li in plan.line_items if li.category == "venue"]
    venue_items = [v for v in venue_items if v is not None]
    check(all(request.location_type in v.location_types for v in venue_items), "VENUE_LOCATION", "error",
          f"The venue chosen doesn't match '{request.location_type}'.")
    venue_feeds = any("includes:main" in v.tags for v in venue_items)

    # 5. Schedule sanity
    check(len(plan.schedule) >= 2, "SCHEDULE_TOO_SHORT", "error",
          "Schedule needs at least two slots.")
    times = [(_parse_hhmm(s.start), _parse_hhmm(s.end)) for s in plan.schedule]
    monotonic = all(a is not None and b is not None and a < b for a, b in times) and all(
        times[i][1] is not None and times[i + 1][0] is not None and times[i][1] <= times[i + 1][0]
        for i in range(len(times) - 1)
    )
    check(monotonic or len(plan.schedule) < 2, "SCHEDULE_NOT_MONOTONIC", "error",
          "Schedule slots overlap or run backwards.")

    # 6. Guest scaling — safe servings cover guests, and a real MEAL covers guests.
    total_servings = sum(m.servings for m in plan.menu)
    check(total_servings >= guests or venue_feeds, "FOOD_UNDERSCALED", "error",
          f"Menu serves {total_servings} but {guests} guests are coming.")
    main_servings = sum(m.servings for m in plan.menu if (m.course or "main") == "main")
    check(main_servings >= guests or venue_feeds, "MAIN_UNDERSCALED", "error",
          f"Main course covers {main_servings} of {guests} guests — snacks and sweets don't count as a meal.")

    # 6b. Supplies scaling — place-setting capacity (tableware only) must cover guests.
    capacity = 0
    for li in plan.line_items:
        if li.category != "supplies":
            continue
        item = catalog.get(li.sku)
        if item is None:
            continue
        capacity += item.settings_for(li.quantity, guests)
    check(capacity >= guests, "SUPPLIES_UNDERSCALED", "error",
          f"Supplies cover {capacity} place settings but {guests} guests are coming.")

    # 6c. Dietary recognition — never imply we honored a need we cannot verify.
    unverifiable = diet.unverifiable[0] if diet.unverifiable else None
    check(unverifiable is None, "DIETARY_UNVERIFIABLE", "error",
          f"We can't yet verify the dietary need '{unverifiable}', so we won't imply "
          f"this plan is safe for it." if unverifiable else "")

    # 6d. Capacity and billing minimums.
    over_cap, under_min = [], []
    for li in plan.line_items:
        item = catalog.get(li.sku)
        if item is None:
            continue
        if not item.within_capacity(guests):
            over_cap.append(f"{item.name} (max {item.max_guests})")
        if item.unit == "per_person" and item.below_minimum(guests):
            under_min.append(f"{item.name} (billed for {item.min_guests})")
    check(not over_cap, "GUEST_RANGE", "error",
          f"Too many guests for: {', '.join(over_cap)}.")
    check(not under_min, "VENDOR_MINIMUM", "warning",
          f"Vendor minimums apply, you pay the floor: {', '.join(under_min)}.")

    # 7. ALLERGEN SAFETY — real check against catalog allergen profiles.
    forbidden = diet.forbidden
    if forbidden:
        unsafe = [m.name for m in plan.menu if forbidden & set(m.allergens)]
        present = sorted({a for m in plan.menu for a in m.allergens if a in forbidden})
        check(not unsafe, "ALLERGEN_VIOLATION", "error",
              f"Unsafe for '{diet.text}': {', '.join(unsafe)} "
              f"contain {', '.join(a.replace('_', ' ') for a in present)}.")
        safe_servings = sum(m.servings for m in plan.menu if not (forbidden & set(m.allergens)))
        check(safe_servings >= guests or venue_feeds, "INSUFFICIENT_SAFE_FOOD", "error",
              f"Only {safe_servings} allergen-safe servings for {guests} guests.")

    # 8. Vegetarian style, if requested
    if diet.vegetarian:
        veg_servings = sum(m.servings for m in plan.menu if m.vegetarian)
        check(veg_servings >= guests or venue_feeds, "INSUFFICIENT_VEGETARIAN", "error",
              f"Only {veg_servings} vegetarian servings for {guests} guests.")

    # 8b. Certifications — halal / kosher are promises we can now check.
    if diet.certifications:
        uncertified = []
        for m in plan.menu:
            item = catalog.get(m.sku)
            if item is None:
                continue
            if "halal" in diet.certifications and not item.vegetarian and "halal" not in item.certifications:
                uncertified.append(item.name)
            if "kosher" in diet.certifications and item.course != "drink" and "kosher" not in item.certifications:
                uncertified.append(item.name)
        for v in venue_items:
            if "includes:main" in v.tags and not diet.venue_ok(v):
                uncertified.append(v.name)
        certs = " / ".join(sorted(diet.certifications))
        check(not uncertified, "CERTIFICATION_MISSING", "error",
              f"Not {certs}-certified: {', '.join(dict.fromkeys(uncertified))}.")
        if "kosher" in diet.certifications:
            supervised = any(li.sku == KOSHER_SUPERVISION_SKU for li in plan.line_items)
            check(supervised, "KOSHER_SUPERVISION_MISSING", "error",
                  "A kosher event needs on-site supervision (mashgiach) on the plan.")

    # 8c. Ingredient promises — 'no pork', 'alcohol-free'.
    if diet.avoid:
        offenders = []
        for m in plan.menu:
            item = catalog.get(m.sku)
            if item and any(f"contains:{t}" in item.tags for t in diet.avoid):
                offenders.append(item.name)
        for v in venue_items:
            if any(f"contains:{t}" in v.tags for t in diet.avoid) and "includes:main" in v.tags:
                offenders.append(v.name)
        check(not offenders, "INGREDIENT_VIOLATION", "error",
              f"Contains {', '.join(sorted(diet.avoid))}: {', '.join(offenders)}.")

    # 9. Age-appropriateness — everything bought fits the honoree's age.
    bad_age = []
    for li in plan.line_items:
        item = catalog.get(li.sku)
        if item and not (item.min_age <= request.honoree_age <= item.max_age):
            bad_age.append(item.name)
    check(not bad_age, "AGE_INAPPROPRIATE", "error",
          f"Not suitable for age {request.honoree_age}: {', '.join(bad_age)}.")
    real_activities = [li for li in plan.line_items if li.category == "activities"
                       and not ((it := catalog.get(li.sku)) is not None and it.is_service)]
    check(bool(real_activities), "NO_ACTIVITIES", "error", "No activities planned.")

    # 10. A birthday without a cake moment is a party with a hole in it (warning).
    if looks_like_birthday(request) and request.honoree_age <= 17:
        has_cake = any((m.course == "cake") or ("cake" in m.name.lower()) for m in plan.menu)
        check(has_cake, "NO_CAKE_MOMENT", "warning", "No cake on the plan for a birthday.")

    checks_total = len(checks)
    checks_passed = sum(1 for c in checks if c)
    has_error = any(v.severity == "error" for v in violations)
    return VerificationReport(
        passed=not has_error,
        score=round(checks_passed / checks_total, 3) if checks_total else 0.0,
        checks_total=checks_total,
        checks_passed=checks_passed,
        violations=violations,
    )
