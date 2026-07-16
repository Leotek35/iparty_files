"""TTLPartyPlanner — verifier-gated, catalog-grounded, honest about failure.

Two orchestration upgrades from Loop 4:

1. FEASIBILITY PRECHECK — before spending a single LLM call, the planner
   computes the cheapest constraint-compliant plan. If even that exceeds the
   budget (or no compliant plan exists at all), it refuses instantly with the
   minimum feasible budget: zero LLM calls on provably-impossible requests.

2. VERIFIER-GUIDED REPAIR — failed candidates are not discarded blindly. The
   verifier's violations are fed into the next generation attempt as concrete
   repair instructions (Reflexion-style feedback, but grounded in a sound
   verifier rather than model self-critique).
"""
from __future__ import annotations

from ..core.exceptions import NoValidPlanError
from ..core.logging import get_logger
from ..llm.client import LLMClient
from ..core.config import settings
from ..orchestration.jepa_bridge import JepaAdvisor
from ..orchestration.ttl_engine import TTLOrchestrator
from ..pricing.catalog import Catalog, unrecognized_restrictions
from .feasibility import minimum_feasible_budget
from .grounding import ground_draft
from .models import PartyRequest, PlanResult
from .verifier import verify_plan

logger = get_logger("planner")


class TTLPartyPlanner:
    def __init__(self, client: LLMClient, catalog: Catalog, orchestrator: TTLOrchestrator) -> None:
        self.client = client
        self.catalog = catalog
        self.orchestrator = orchestrator

    async def plan(self, request: PartyRequest) -> PlanResult:
        # ---- 1. Feasibility precheck: refuse impossible requests for free ----
        min_budget = minimum_feasible_budget(request, self.catalog)
        if min_budget is None:
            raise NoValidPlanError(
                message="No catalog combination can satisfy these constraints "
                        "(e.g. no allergen-safe food or age-appropriate activity exists).",
                violations=[{"code": "CONSTRAINTS_UNSATISFIABLE", "severity": "error",
                             "message": "No compliant plan exists in the catalog."}],
                minimum_feasible_budget=None,
                telemetry={"llm_calls": 0, "pattern_log": ["feasibility precheck: unsatisfiable"]},
            )
        if min_budget > request.budget:
            raise NoValidPlanError(
                message="The budget cannot cover any compliant plan.",
                violations=[{"code": "BUDGET_INFEASIBLE", "severity": "error",
                             "message": f"Cheapest compliant plan costs ${min_budget:,.2f}, "
                                        f"over the ${request.budget:,.2f} budget."}],
                minimum_feasible_budget=min_budget,
                telemetry={"llm_calls": 0,
                           "pattern_log": ["feasibility precheck: refused with 0 LLM calls"]},
            )

        # ---- 2. Verified best-of-N with repair feedback ----
        advisor = (JepaAdvisor(request, self.catalog)
                   if settings.JEPA_BRIDGE_ENABLED else None)
        # JEPA bridge: predicted risk areas become *preemptive* instructions —
        # the first generation already knows what usually goes wrong here.
        last_feedback: str | None = advisor.prehint() if advisor else None

        async def produce(i: int):
            nonlocal last_feedback
            temperature = 0.4 + 0.15 * i
            draft = await self.client.generate_draft(
                request, self.catalog, temperature=temperature, feedback=last_feedback
            )
            return ground_draft(draft, self.catalog, request.guest_count)

        def verify(plan):
            nonlocal last_feedback
            report = verify_plan(plan, request, self.catalog)
            if not report.passed:
                errs = [v for v in report.violations if v.severity == "error"]
                last_feedback = "Previous attempt failed verification. Fix exactly these: " + \
                    "; ".join(f"[{v.code}] {v.message}" for v in errs)
            return report.passed, report.score, report

        candidate, telemetry = await self.orchestrator.run_verified(
            produce, verify, advisor=advisor)
        report = candidate.detail

        if not candidate.passed:
            binding = [v.model_dump() for v in report.violations if v.severity == "error"]
            raise NoValidPlanError(
                message="No plan could satisfy all constraints.",
                violations=binding,
                minimum_feasible_budget=min_budget,
                telemetry=telemetry.as_dict(),
            )

        plan = candidate.value
        extra_notes = []
        unrec = unrecognized_restrictions(request.dietary_restrictions)
        if unrec:
            extra_notes.append(
                "Heads-up: we could not auto-verify "
                + ", ".join(f"'{u}'" for u in unrec)
                + " against catalog data — a coordinator should confirm these by hand.")
        text = request.dietary_restrictions.lower()
        if any(k in text for k in ("kosher", "halal", "jain")):
            extra_notes.append(
                "Menu is fully vegetarian as the safe approximation for your "
                "dietary tradition; certified vendors can be arranged on request.")
        if request.special_requests.strip():
            extra_notes.append("Special requests noted for your coordinator: "
                               + request.special_requests.strip())
        if plan.total_cost < request.budget * 0.35 and request.budget >= 1000:
            extra_notes.append(
                f"We built the richest package our verified catalog offers "
                f"(${plan.total_cost:,.2f}); your budget allows more — a coordinator "
                f"can source premium vendors beyond the standard catalog.")
        if extra_notes:
            plan.notes = " ".join(filter(None, [plan.notes] + extra_notes)).strip()

        return PlanResult(
            status="verified",
            request=request,
            plan=candidate.value,
            verification=report,
            telemetry=telemetry.as_dict(),
            backend=self.client.name,
        )
