"""Living Pass — a saved plan that re-verifies itself as guests RSVP.

Every other planner goes stale the moment the first RSVP arrives: it counts
heads and stops. iParty owns a verifier, so a saved plan can be re-checked
against the LIVE guest list — real headcount, real declared needs — and when
something breaks, the fix is a minimal, deterministic repair of the host's own
selections, re-verified by the same engine. No model call, no invented advice,
instant on every poll.

How a re-check works:
  1. The saved plan is a set of catalog SELECTIONS (SKUs × quantities). They
     are re-grounded at the live headcount: per-person items scale in price
     and servings; flat items (a cake that serves 20, a pack of 16 settings)
     do not — which is exactly what should trip "underscaled" when 24 show up.
  2. The verifier runs against the live request (confirmed headcount, merged
     dietary picture). Its verdict is the host's status.
  3. If it fails, `repair` keeps every selection it can, drops food that is
     unsafe for a newly declared allergy, and adds the cheapest safe
     servings / place settings until covered — then verifies the result.
     If the host's selections can't be saved within budget, the cheapest
     compliant plan is offered instead; if nothing fits, the honest minimum
     budget is reported.

States a host can see:
  awaiting      nobody has said yes yet — verified for the planned headcount
  verified      still verified for everyone who has confirmed
  attention     the live guest list breaks the plan — a verified fix is attached
  unverifiable  a guest declared a need the catalog can't check (e.g. halal) —
                flagged honestly rather than silently "handled"
"""
from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Any

from ..pricing.catalog import Catalog, CatalogItem, dietary_context, unverifiable_dietary
from .composer import compose
from .feasibility import (
    KOSHER_SUPERVISION_SKU,
    cheapest_compliant_draft,
    minimum_feasible_budget,
    units_to_cover,
)
from .grounding import ground_draft
from .models import PartyPlan, PartyRequest, PlanDraft, Selection, VerificationReport
from .verifier import verify_plan

MAX_DIETARY_LEN = 300  # PartyRequest.dietary_restrictions cap


# ---------------------------------------------------------------------------
# Guest-list arithmetic
# ---------------------------------------------------------------------------
def live_counts(guests: list[dict]) -> dict:
    confirmed = sum(int(g["party_size"]) for g in guests if g.get("attending"))
    going = sum(1 for g in guests if g.get("attending"))
    declined = sum(1 for g in guests if not g.get("attending"))
    return {"confirmed": confirmed, "responses_going": going, "responses_declined": declined}


def split_needs(text: str) -> list[str]:
    """'gluten free; halal' -> ['gluten free', 'halal'] (trimmed, non-empty)."""
    out: list[str] = []
    for piece in (text or "").replace("\n", ";").replace(",", ";").split(";"):
        piece = piece.strip()
        if piece:
            out.append(piece)
    return out


def merge_dietary(base: str, guest_needs: list[str]) -> str:
    """Union of the host's stated restrictions and every attending guest's
    declared need, de-duplicated case-insensitively, capped to the model limit."""
    seen: set[str] = set()
    parts: list[str] = []
    for raw in [base, *guest_needs]:
        for piece in split_needs(raw):
            key = piece.lower()
            if key not in seen:
                seen.add(key)
                parts.append(piece)
    return "; ".join(parts)[:MAX_DIETARY_LEN]


def guest_needs(guests: list[dict]) -> list[str]:
    return [g["dietary"] for g in guests if g.get("attending") and (g.get("dietary") or "").strip()]


def live_request(saved: PartyRequest, guests: list[dict]) -> PartyRequest:
    """The request the plan must now satisfy: confirmed headcount (or the
    planned one until someone says yes) and the merged dietary picture."""
    counts = live_counts(guests)
    headcount = counts["confirmed"] if counts["confirmed"] > 0 else saved.guest_count
    headcount = max(1, min(500, headcount))
    party_date = saved.party_date if saved.party_date >= date.today() else date.today()
    return PartyRequest(
        honoree_name=saved.honoree_name, honoree_age=saved.honoree_age,
        party_date=party_date, guest_count=headcount, budget=saved.budget,
        theme=saved.theme,
        dietary_restrictions=merge_dietary(saved.dietary_restrictions, guest_needs(guests)),
        location_type=saved.location_type,
    )


# ---------------------------------------------------------------------------
# Selections <-> plans
# ---------------------------------------------------------------------------
def _selections(plan: PartyPlan) -> tuple[str, list[Selection], list[Selection], list[Selection]]:
    venue = next((li.sku for li in plan.line_items if li.category == "venue"), "VEN-HOME")
    pick = lambda cat: [Selection(sku=li.sku, quantity=li.quantity)  # noqa: E731
                        for li in plan.line_items if li.category == cat]
    return venue, pick("food"), pick("supplies"), pick("activities")


def _draft(plan: PartyPlan, venue: str, food: list[Selection], supplies: list[Selection],
           activities: list[Selection]) -> PlanDraft:
    """The host's selections as a draft — the concept (name, story, moments)
    rides along so a repaired plan is still their party."""
    return PlanDraft(theme=plan.theme, venue_sku=venue, food=food, supplies=supplies,
                     activities=activities, schedule=plan.schedule, notes=plan.notes,
                     concept_name=plan.concept_name, story=plan.story, moments=list(plan.moments))


def reground(plan: PartyPlan, catalog: Catalog, guests: int) -> PartyPlan:
    """The host's own selections, priced and portioned for `guests`."""
    venue, food, supplies, activities = _selections(plan)
    return ground_draft(_draft(plan, venue, food, supplies, activities), catalog, guests)


def _line_key(li: dict) -> tuple[str, int]:
    return (li["sku"], int(li["quantity"]))


def diff_lines(old: PartyPlan, new: PartyPlan) -> dict:
    old_map = {_line_key(li.model_dump()): li for li in old.line_items}
    new_map = {_line_key(li.model_dump()): li for li in new.line_items}
    added = [li.model_dump() for k, li in new_map.items() if k not in old_map]
    removed = [li.model_dump() for k, li in old_map.items() if k not in new_map]
    return {"added": added, "removed": removed}


# ---------------------------------------------------------------------------
# Assessment
# ---------------------------------------------------------------------------
def unverifiable_needs(dietary: str) -> list[str]:
    """Each declared need judged on its own, so 'gluten free; halal' never lets
    'halal' hide behind a need we do understand."""
    return [n for n in split_needs(dietary) if unverifiable_dietary(n) is not None]


def assess(saved_req: PartyRequest, saved_plan: PartyPlan, guests: list[dict],
           catalog: Catalog) -> dict:
    counts = live_counts(guests)
    live_req = live_request(saved_req, guests)
    current = reground(saved_plan, catalog, live_req.guest_count)
    report = verify_plan(current, live_req, catalog)
    errors = [v for v in report.violations if v.severity == "error"]
    attention = [{"code": v.code, "message": v.message} for v in errors]

    unverifiable = unverifiable_needs(live_req.dietary_restrictions)
    for need in unverifiable:
        if not any(a["code"] == "DIETARY_UNVERIFIABLE" for a in attention):
            attention.insert(0, {"code": "DIETARY_UNVERIFIABLE",
                                 "message": f"'{need}' can't be verified against catalog data yet — "
                                            f"confirm it with the guest or a certified vendor."})

    if counts["confirmed"] == 0:
        state = "awaiting"
    elif unverifiable:
        state = "unverifiable"
    elif report.passed:
        state = "verified"
    else:
        state = "attention"

    return {"state": state, "counts": counts, "planned_guests": saved_req.guest_count,
            "live_request": live_req, "current": current, "report": report,
            "attention": attention, "unverifiable": unverifiable}


# ---------------------------------------------------------------------------
# Minimal, verified repair of the host's own selections
# ---------------------------------------------------------------------------
def _same_family(a: CatalogItem, b: CatalogItem) -> bool:
    """Siblings that can stand in for each other without changing the party:
    same kind of thing, same safety profile, just a different size."""
    return (a.category == b.category and a.subcategory == b.subcategory and a.unit == b.unit
            and a.allergens == b.allergens and a.vegetarian == b.vegetarian
            and a.certifications == b.certifications and a.min_age == b.min_age and a.max_age == b.max_age
            and a.location_types == b.location_types
            and {t for t in a.tags if t.startswith("contains:")} == {t for t in b.tags if t.startswith("contains:")})


def requantify(selections: list[Selection], catalog: Catalog, guests: int) -> list[Selection]:
    """The same items portioned for `guests`: fewer units of a flat item when
    fewer people come, and a smaller same-family sibling (a 20-serving cake
    instead of a 48-serving one) when that is cheaper and still covers."""
    out: list[Selection] = []
    for s in selections:
        item = catalog.get(s.sku)
        if item is None:
            out.append(s)
            continue
        if item.unit != "flat" or (item.category == "food" and item.serves <= 0) or (
                item.category == "supplies" and not item.is_tableware):
            out.append(s)
            continue
        qty = min(s.quantity, units_to_cover(item, guests))
        best_item, best_qty, best_price = item, qty, item.price_for(qty, guests)
        for sib in catalog.by_category(item.category):
            if sib.sku == item.sku or not _same_family(item, sib):
                continue
            sq = units_to_cover(sib, guests)
            provided = sib.servings_for(sq, guests) if sib.category == "food" else sib.settings_for(sq, guests)
            if provided < guests:
                continue
            price = sib.price_for(sq, guests)
            if price < best_price - 0.005:
                best_item, best_qty, best_price = sib, sq, price
        out.append(Selection(sku=best_item.sku, quantity=best_qty))
    return out


_SHED_COURSES = ("drink", "snack", "side", "dessert", "cake")


def _shed_steps(food: list[Selection], supplies: list[Selection], activities: list[Selection],
                catalog: Catalog, guests: int):
    """Ways to save money that keep the party recognisable, cheapest loss first:
    an extra activity (dearest first), non-tableware supplies, then courses
    around the meal, then the last activity down to the cheapest."""
    acts = [(catalog.get(s.sku), s) for s in activities]
    real = [(it, s) for it, s in acts if it is not None and not it.is_service]
    if len(real) > 1:
        dearest = max(real, key=lambda x: x[0].price_for(x[1].quantity, guests))
        yield food, supplies, [s for s in activities if s is not dearest[1]]
    for s in supplies:
        it = catalog.get(s.sku)
        if it is not None and not it.is_tableware:
            yield food, [x for x in supplies if x is not s], activities
    for course in _SHED_COURSES:
        for s in food:
            it = catalog.get(s.sku)
            if it is not None and it.course == course:
                yield [x for x in food if x is not s], supplies, activities


def repair(saved_plan: PartyPlan, live_req: PartyRequest,
           catalog: Catalog) -> tuple[PartyPlan, VerificationReport] | None:
    guests = live_req.guest_count
    diet = dietary_context(live_req)
    loc, age = live_req.location_type, live_req.honoree_age

    def usable(item: CatalogItem) -> bool:
        return item.min_age <= age <= item.max_age and item.within_capacity(guests) and loc in item.location_types

    venue, food, supplies, activities = _selections(saved_plan)
    venue_item = catalog.get(venue)
    venue_feeds = venue_item is not None and "includes:main" in venue_item.tags and diet.venue_ok(venue_item)

    # 1. Drop food that is unsafe for the live dietary picture (allergens,
    #    vegetarian, certification, ingredient promises).
    food = [s for s in food if (it := catalog.get(s.sku)) is not None and diet.safe(it)]

    # 2. Add the cheapest safe MAIN servings until every confirmed guest has a
    #    meal, preferring one more unit of something already chosen (minimal diff).
    safe_mains = [f for f in catalog.by_category("food") if diet.safe(f) and f.serves > 0 and f.course == "main"
                  and "style:included" not in f.tags and usable(f)]
    if not safe_mains and not venue_feeds:
        return None

    def main_servings(sel: list[Selection]) -> int:
        return sum(it.servings_for(s.quantity, guests) for s in sel
                   if (it := catalog.get(s.sku)) is not None and it.course == "main")

    def bump(sel: list[Selection], sku: str) -> list[Selection]:
        out, hit = [], False
        for s in sel:
            if s.sku == sku:
                out.append(Selection(sku=sku, quantity=s.quantity + 1))
                hit = True
            else:
                out.append(s)
        return out if hit else [*out, Selection(sku=sku, quantity=1)]

    guard = 0
    while not venue_feeds and main_servings(food) < guests and guard < 200:
        guard += 1
        chosen = {s.sku for s in food}
        best = min(
            safe_mains,
            key=lambda f: (
                (f.price_for(1, guests) / max(1, f.servings_for(1, guests)))
                * (0.85 if f.sku in chosen else 1.0),
                f.sku,
            ),
        )
        if best.unit == "per_person" and best.sku in chosen:
            break  # a per-person item already covers everyone
        food = bump(food, best.sku)

    # 3. Add place settings until every confirmed guest has one.
    def capacity(sel: list[Selection]) -> int:
        return sum(it.settings_for(s.quantity, guests) for s in sel if (it := catalog.get(s.sku)) is not None)

    options = [c for c in catalog.by_category("supplies") if c.is_tableware and usable(c)]
    guard = 0
    while options and capacity(supplies) < guests and guard < 200:
        guard += 1
        chosen = {s.sku for s in supplies}
        best = min(
            options,
            key=lambda c: (
                (c.price_for(1, guests) / max(1, c.settings_for(1, guests)))
                * (0.85 if c.sku in chosen else 1.0),
                c.sku,
            ),
        )
        if best.unit == "per_person" and best.sku in chosen:
            break
        supplies = bump(supplies, best.sku)

    # 4. Keep an age-appropriate activity on the plan; kosher needs supervision.
    acts = [a for a in catalog.by_category("activities") if usable(a) and not a.is_service]
    if not any((it := catalog.get(s.sku)) is not None and not it.is_service for s in activities) and acts:
        cheapest = min(acts, key=lambda a: (a.price_for(1, guests), a.sku))
        activities = [*activities, Selection(sku=cheapest.sku, quantity=1)]
    if ("kosher" in diet.certifications and not any(s.sku == KOSHER_SUPERVISION_SKU for s in activities)
            and catalog.get(KOSHER_SUPERVISION_SKU) is not None):
        activities = [*activities, Selection(sku=KOSHER_SUPERVISION_SKU, quantity=1)]

    plan = ground_draft(_draft(saved_plan, venue, food, supplies, activities), catalog, guests)
    report = verify_plan(plan, live_req, catalog)
    if report.passed:
        return plan, report

    # 5. If the only thing wrong now is money, shed the least important things
    #    first — never the meal, the settings or the last activity — and keep
    #    the first version that verifies.
    errors = {v.code for v in report.violations if v.severity == "error"}
    if errors <= {"BUDGET_EXCEEDED"}:
        f2, s2, a2 = food, supplies, activities
        for _ in range(12):
            progressed = False
            for f3, s3, a3 in _shed_steps(f2, s2, a2, catalog, guests):
                plan2 = ground_draft(_draft(saved_plan, venue, f3, s3, a3), catalog, guests)
                report2 = verify_plan(plan2, live_req, catalog)
                if report2.passed:
                    return plan2, report2
                if plan2.total_cost < ground_draft(_draft(saved_plan, venue, f2, s2, a2), catalog, guests).total_cost:
                    f2, s2, a2, progressed = f3, s3, a3, True
                    break
            if not progressed:
                break
        if acts:
            cheapest = min(acts, key=lambda a: (a.price_for(1, guests), a.sku))
            trimmed = [Selection(sku=cheapest.sku, quantity=1)] + [s for s in a2 if s.sku == KOSHER_SUPERVISION_SKU]
            plan2 = ground_draft(_draft(saved_plan, venue, f2, s2, trimmed), catalog, guests)
            report2 = verify_plan(plan2, live_req, catalog)
            if report2.passed:
                return plan2, report2
    return plan, report


def propose_fix(saved_plan: PartyPlan, current: PartyPlan, live_req: PartyRequest,
                catalog: Catalog) -> dict:
    """A verified way forward, in order of least disruption:
    repair the host's selections → cheapest compliant plan → honest minimum."""
    repaired = repair(saved_plan, live_req, catalog)
    if repaired and repaired[1].passed:
        plan, report = repaired
        return _fix_payload(plan, report, saved_plan, current, live_req, "repair")

    # The host's choices can't be saved: a fresh concept for the live list
    # (lean tier) beats a bare-minimum plan, when the budget allows one.
    for strategy, draft in (("recomposed", compose(live_req, catalog, tier_override="essential")),
                            ("cheapest_compliant", cheapest_compliant_draft(live_req, catalog))):
        if draft is None:
            continue
        plan = ground_draft(draft, catalog, live_req.guest_count)
        report = verify_plan(plan, live_req, catalog)
        if report.passed:
            return _fix_payload(plan, report, saved_plan, current, live_req, strategy)

    minimum = minimum_feasible_budget(live_req, catalog)
    if minimum is not None and minimum > live_req.budget:
        return {"available": False, "reason": "BUDGET_INFEASIBLE",
                "message": f"Feeding {live_req.guest_count} within ${live_req.budget:,.2f} isn't "
                           f"possible from the catalog; the cheapest compliant plan is ${minimum:,.2f}.",
                "minimum_feasible_budget": minimum}
    return {"available": False, "reason": "CONSTRAINTS_UNSATISFIABLE",
            "message": "No catalog combination satisfies the live guest list's needs.",
            "minimum_feasible_budget": minimum}


def _fix_payload(plan: PartyPlan, report: VerificationReport, saved_plan: PartyPlan,
                 current: PartyPlan, live_req: PartyRequest, strategy: str) -> dict:
    return {
        "available": True, "verified": report.passed, "strategy": strategy,
        "new_total": plan.total_cost, "budget": live_req.budget,
        "delta_vs_planned": round(plan.total_cost - saved_plan.total_cost, 2),
        "delta_vs_current": round(plan.total_cost - current.total_cost, 2),
        **diff_lines(current, plan),
        "plan": plan.model_dump(), "verification": report.model_dump(),
    }


def headcount_settled(planned: int, guests: list[dict]) -> bool:
    """A right-size offer is only meaningful once the picture is real: at least
    half the planned seats have confirmed, or every planned seat has answered
    (confirmed seats plus declined seats cover the plan)."""
    confirmed = sum(int(g["party_size"]) for g in guests if g.get("attending"))
    declined_seats = sum(int(g["party_size"]) for g in guests if not g.get("attending"))
    return confirmed * 2 >= planned or confirmed + declined_seats >= planned


def all_answered(planned: int, guests: list[dict]) -> bool:
    """Every planned seat has a yes or a no against it."""
    return sum(int(g["party_size"]) for g in guests) >= planned


def right_size(saved_req: PartyRequest, saved_plan: PartyPlan, guests: list[dict],
               catalog: Catalog) -> dict | None:
    """When fewer guests confirm than were planned for, show the SAME party
    portioned for the real headcount — fewer units, smaller same-family
    siblings — never a different, cheaper party. Savings, not shortfalls."""
    counts = live_counts(guests)
    if counts["confirmed"] == 0 or counts["confirmed"] >= saved_req.guest_count:
        return None
    if not headcount_settled(saved_req.guest_count, guests):
        return None  # too early: one early "yes" is not a smaller party
    live_req = live_request(saved_req, guests)
    n = live_req.guest_count
    current = reground(saved_plan, catalog, n)
    venue, food, supplies, activities = _selections(saved_plan)
    sized = ground_draft(_draft(saved_plan, venue, requantify(food, catalog, n), requantify(supplies, catalog, n),
                                activities), catalog, n)
    report = verify_plan(sized, live_req, catalog)
    if not report.passed or sized.total_cost >= current.total_cost - 0.005:
        return None
    return {"available": True, "confirmed": counts["confirmed"],
            "final": all_answered(saved_req.guest_count, guests),
            "current_total": current.total_cost, "new_total": sized.total_cost,
            "savings": round(current.total_cost - sized.total_cost, 2),
            "plan": sized.model_dump(), **diff_lines(current, sized)}


# ---------------------------------------------------------------------------
# Apply — the host accepts a verified way forward and it becomes the plan
# ---------------------------------------------------------------------------
class ApplyError(Exception):
    def __init__(self, reason: str, message: str, minimum: float | None = None) -> None:
        super().__init__(message)
        self.reason, self.message, self.minimum = reason, message, minimum


def apply(saved: dict, guests: list[dict], catalog: Catalog, action: str,
          budget: float | None = None) -> tuple[PartyRequest, PartyPlan, VerificationReport]:
    """Turn a proposal into the saved plan. Everything is recomputed here from
    the saved selections and the live guest list — a client can never hand us
    a plan to store. Returns the new (request, plan, report); the report has
    passed for every verifiable need, or ApplyError says why nothing can.

    action = "fix"        the attention/unverifiable fix (repair, else cheapest compliant)
             "right_size" the cheaper verified plan for the confirmed headcount
             "budget"     re-plan at `budget` (the honest minimum, or more)
    """
    saved_req = PartyRequest.model_validate(saved["request"])
    saved_plan = PartyPlan.model_validate(saved["plan"])
    if action == "budget":
        if budget is None or budget <= 0:
            raise ApplyError("bad_budget", "A budget above zero is required.")
        saved_req = saved_req.model_copy(update={"budget": float(budget)})
    counts = live_counts(guests)
    headcount = counts["confirmed"] if counts["confirmed"] > 0 else saved_req.guest_count
    live_req = live_request(saved_req, guests)
    excluded = unverifiable_needs(live_req.dietary_restrictions)
    keep = [n for n in split_needs(live_req.dietary_restrictions) if n.lower() not in {e.lower() for e in excluded}]
    check_req = live_req.model_copy(update={"dietary_restrictions": "; ".join(keep)})
    current = reground(saved_plan, catalog, check_req.guest_count)

    if action == "right_size":
        rs = right_size(saved_req, saved_plan, guests, catalog)
        if not rs or not rs.get("available"):
            raise ApplyError("no_right_size", "There is no cheaper verified plan for the confirmed headcount yet.")
        plan = PartyPlan.model_validate(rs["plan"])
    elif action in ("fix", "budget"):
        report = verify_plan(current, check_req, catalog)
        if report.passed:
            plan = current  # nothing broken (a budget change alone): keep the host's selections
        else:
            fix = propose_fix(saved_plan, current, check_req, catalog)
            if not fix.get("available"):
                raise ApplyError("no_verified_plan", fix.get("message", "No verified plan is possible."),
                                 fix.get("minimum_feasible_budget"))
            plan = PartyPlan.model_validate(fix["plan"])
    else:
        raise ApplyError("bad_action", "action must be fix, right_size or budget.")

    # planned headcount: right-sizing adopts the confirmed number; a fix for an
    # overflow grows the plan to it; an allergy fix at 5 of 14 keeps "14 planned".
    planned = headcount if action == "right_size" else max(saved_req.guest_count, headcount)
    new_req = saved_req.model_copy(update={"guest_count": planned})
    final = verify_plan(plan, check_req.model_copy(update={"guest_count": headcount}), catalog)
    if not final.passed:  # defence in depth: never save an unverified plan
        raise ApplyError("no_verified_plan", "The proposed plan did not verify at the live headcount.")
    return new_req, plan, final


# ---------------------------------------------------------------------------
# Status (what the host sees) with a per-guest-list cache
# ---------------------------------------------------------------------------
_CACHE: dict[str, tuple[str, dict]] = {}


def _fingerprint(guests: list[dict], saved: dict | None = None) -> str:
    rows = sorted((g["guest_key"], int(bool(g["attending"])), int(g["party_size"]),
                   g.get("dietary", "")) for g in guests)
    payload = [rows, saved["request"] if saved else None, saved["plan"] if saved else None]
    return hashlib.sha256(json.dumps(payload, default=str, sort_keys=True).encode()).hexdigest()


def _headline(state: str, counts: dict, planned: int, attention: list[dict]) -> str:
    c = counts["confirmed"]
    if state == "awaiting":
        return f"Verified for the planned {planned} — waiting on RSVPs."
    if state == "verified":
        return f"Still verified for {c} confirmed."
    if state == "unverifiable":
        return f"{c} confirmed — one need can't be verified yet."
    return f"{c} confirmed — needs attention ({len(attention)})."


def build_status(plan_id: str, saved: dict, guests: list[dict], catalog: Catalog) -> dict:
    fp = _fingerprint(guests, saved)
    cached = _CACHE.get(plan_id)
    if cached and cached[0] == fp:
        return cached[1]

    saved_req = PartyRequest.model_validate(saved["request"])
    saved_plan = PartyPlan.model_validate(saved["plan"])
    a = assess(saved_req, saved_plan, guests, catalog)
    live_req: PartyRequest = a["live_request"]
    current: PartyPlan = a["current"]

    fix = None
    if a["state"] in ("attention", "unverifiable"):
        # A need we can't verify must not block help with the ones we can:
        # repair against the verifiable picture and say plainly what's excluded.
        excluded = a["unverifiable"]
        fix_req = live_req
        if excluded:
            keep = [n for n in split_needs(live_req.dietary_restrictions)
                    if n.lower() not in {e.lower() for e in excluded}]
            fix_req = live_req.model_copy(update={"dietary_restrictions": "; ".join(keep)})
        fix_current = reground(saved_plan, catalog, fix_req.guest_count)
        fix_report = verify_plan(fix_current, fix_req, catalog)
        fix = None if fix_report.passed else propose_fix(saved_plan, fix_current, fix_req, catalog)
        if fix is not None and excluded:
            fix["covers_unverifiable"] = False
            fix["excluded_needs"] = excluded
    resize = None
    if a["state"] in ("verified", "attention"):
        resize = right_size(saved_req, saved_plan, guests, catalog)

    status: dict[str, Any] = {
        "plan_id": plan_id,
        "state": a["state"],
        "headline": _headline(a["state"], a["counts"], a["planned_guests"], a["attention"]),
        "planned_guests": a["planned_guests"],
        "confirmed_guests": a["counts"]["confirmed"],
        "responses": {"going": a["counts"]["responses_going"],
                      "declined": a["counts"]["responses_declined"]},
        "dietary_needs": split_needs(live_req.dietary_restrictions),
        "unverifiable_needs": a["unverifiable"],
        "verification": a["report"].model_dump(),
        "attention": a["attention"],
        "fix": fix,
        "right_size": resize,
        "saved_total": saved_plan.total_cost,
        "current_total": current.total_cost,
        "budget": saved_req.budget,
        "llm_calls": 0,
    }
    _CACHE[plan_id] = (fp, status)
    return status


def reset_state() -> None:
    _CACHE.clear()
