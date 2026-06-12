"""Constraint verifier — the ground-truth gate for party plans.

This is the analogue of the symbolic plan-validator in the research notebooks.
A party plan either satisfies the hard constraints (budget, completeness, guest
scaling, dietary, schedule sanity) or it does not — decided here, deterministically,
*not* by an LLM. This is what makes TTL orchestration meaningful: candidates are
gated on objective correctness, so the system can guarantee a budget-valid,
complete plan rather than merely a plausible-looking one.
"""
from __future__ import annotations

from .models import PartyPlan, PartyRequest, VerificationReport, Violation
from ..core.config import settings


def _parse_hhmm(s: str) -> int | None:
    try:
        h, m = s.split(":")
        return int(h) * 60 + int(m)
    except Exception:  # noqa: BLE001
        return None


def verify_plan(plan: PartyPlan, request: PartyRequest) -> VerificationReport:
    """Return a verification report. `passed` is True iff there are no errors."""
    violations: list[Violation] = []
    checks: list[bool] = []

    def check(ok: bool, code: str, severity: str, message: str) -> None:
        checks.append(ok)
        if not ok:
            violations.append(Violation(code=code, severity=severity, message=message))  # type: ignore[arg-type]

    total = plan.total_cost
    cap = request.budget * (1 + settings.BUDGET_TOLERANCE)

    # 1. Budget ceiling (hard)
    check(total <= cap, "BUDGET_EXCEEDED", "error",
          f"Plan costs ${total:,.2f}, over the ${request.budget:,.2f} budget.")

    # 2. Budget floor (warn if suspiciously cheap — likely incomplete)
    floor = request.budget * settings.BUDGET_FLOOR_FRACTION
    check(total >= floor, "BUDGET_SUSPICIOUSLY_LOW", "warning",
          f"Plan only uses ${total:,.2f} of ${request.budget:,.2f}; may be incomplete.")

    # 3. Completeness — required categories present
    cats = {li.category for li in plan.line_items}
    for required in ("venue", "food", "supplies", "activities"):
        check(required in cats, f"MISSING_{required.upper()}", "error",
              f"Plan is missing a '{required}' line item.")

    # 4. Schedule present and sane
    check(len(plan.schedule) >= 2, "SCHEDULE_TOO_SHORT", "error",
          "Schedule needs at least two time slots.")
    times = [(_parse_hhmm(s.start), _parse_hhmm(s.end)) for s in plan.schedule]
    monotonic = all(
        a is not None and b is not None and a < b for a, b in times
    ) and all(
        times[i][1] is not None and times[i + 1][0] is not None
        and times[i][1] <= times[i + 1][0]
        for i in range(len(times) - 1)
    )
    check(monotonic or len(plan.schedule) < 2, "SCHEDULE_NOT_MONOTONIC", "error",
          "Schedule slots overlap or run backwards.")
    if times and all(t[0] is not None and t[1] is not None for t in times):
        duration = times[-1][1] - times[0][0]
        check(60 <= duration <= 480, "SCHEDULE_DURATION", "warning",
              f"Party runs {duration} min; typical range is 1–8 hours.")

    # 5. Guest scaling — food servings cover guests
    total_servings = sum(m.servings for m in plan.menu)
    check(total_servings >= request.guest_count, "FOOD_UNDERSCALED", "error",
          f"Menu serves {total_servings} but {request.guest_count} guests are coming.")

    # 6. Supplies scale with guests (plates/cups heuristic)
    check(len(plan.supplies) >= 1, "NO_SUPPLIES", "error", "No supplies listed.")

    # 7. Dietary restrictions addressed
    if request.dietary_restrictions.strip():
        addressed = any(m.dietary_tags for m in plan.menu) or (
            request.dietary_restrictions.lower() in plan.notes.lower()
        )
        check(addressed, "DIETARY_UNADDRESSED", "error",
              f"Dietary restriction '{request.dietary_restrictions}' is not addressed in the menu.")

    # 8. Age-appropriateness (light heuristic: activities exist & non-empty)
    check(len(plan.activities) >= 1, "NO_ACTIVITIES", "error", "No activities planned.")

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
