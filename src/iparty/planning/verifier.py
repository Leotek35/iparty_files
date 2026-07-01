"""Constraint verifier — the ground-truth gate.

Now grounded in the catalog: it checks realizability (every SKU is real and
priced at the catalog rate), real allergen safety (against catalog allergen
profiles, not string tags), age-appropriateness, budget, scaling, and schedule.
"""
from __future__ import annotations

from ..core.config import settings
from ..pricing.catalog import Catalog, parse_forbidden_allergens, requires_vegetarian
from .models import PartyPlan, PartyRequest, VerificationReport, Violation


def _parse_hhmm(s: str) -> int | None:
    try:
        h, m = s.split(":")
        return int(h) * 60 + int(m)
    except Exception:  # noqa: BLE001
        return None


def verify_plan(plan: PartyPlan, request: PartyRequest, catalog: Catalog) -> VerificationReport:
    violations: list[Violation] = []
    checks: list[bool] = []

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
        expected = item.price_for(li.quantity, request.guest_count)
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

    # 6. Guest scaling — safe servings cover guests
    total_servings = sum(m.servings for m in plan.menu)
    check(total_servings >= request.guest_count, "FOOD_UNDERSCALED", "error",
          f"Menu serves {total_servings} but {request.guest_count} guests are coming.")

    # 6b. Supplies scaling — place-setting capacity must cover guests.
    #     per_person supplies cover everyone; flat packs cover serves * quantity.
    capacity = 0
    for li in plan.line_items:
        if li.category != "supplies":
            continue
        item = catalog.get(li.sku)
        if item is None:
            continue
        capacity += request.guest_count if item.unit == "per_person" else item.serves * li.quantity
    check(capacity >= request.guest_count, "SUPPLIES_UNDERSCALED", "error",
          f"Supplies cover {capacity} place settings but {request.guest_count} guests are coming.")

    # 7. ALLERGEN SAFETY — real check against catalog allergen profiles.
    forbidden = parse_forbidden_allergens(request.dietary_restrictions)
    if forbidden:
        unsafe = [m.name for m in plan.menu if forbidden & set(m.allergens)]
        check(not unsafe, "ALLERGEN_VIOLATION", "error",
              f"Unsafe for '{request.dietary_restrictions}': {', '.join(unsafe)} "
              f"contain {', '.join(sorted(forbidden))}.")
        safe_servings = sum(m.servings for m in plan.menu if not (forbidden & set(m.allergens)))
        check(safe_servings >= request.guest_count, "INSUFFICIENT_SAFE_FOOD", "error",
              f"Only {safe_servings} allergen-safe servings for {request.guest_count} guests.")

    # 8. Vegetarian style, if requested
    if requires_vegetarian(request.dietary_restrictions):
        veg_servings = sum(m.servings for m in plan.menu if m.vegetarian)
        check(veg_servings >= request.guest_count, "INSUFFICIENT_VEGETARIAN", "error",
              f"Only {veg_servings} vegetarian servings for {request.guest_count} guests.")

    # 9. Age-appropriateness — chosen activities fit the honoree's age.
    bad_age = []
    for li in plan.line_items:
        if li.category != "activities":
            continue
        item = catalog.get(li.sku)
        if item and not (item.min_age <= request.honoree_age <= item.max_age):
            bad_age.append(item.name)
    check(not bad_age, "AGE_INAPPROPRIATE", "error",
          f"Activities not suitable for age {request.honoree_age}: {', '.join(bad_age)}.")
    check(any(li.category == "activities" for li in plan.line_items), "NO_ACTIVITIES",
          "error", "No activities planned.")

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
