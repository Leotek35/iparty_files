"""TTLPartyPlanner — verifier-gated, catalog-grounded, honest about failure."""
from __future__ import annotations

from ..core.exceptions import NoValidPlanError
from ..core.logging import get_logger
from ..llm.client import LLMClient
from ..orchestration.ttl_engine import TTLOrchestrator
from ..pricing.catalog import Catalog
from .feasibility import minimum_feasible_budget
from .grounding import ground_draft
from .models import PartyRequest, PlanResult
from .verifier import verify_plan

logger = get_logger("planner")


class TTLPartyPlanner:
    """Returns a *verified* plan, or raises NoValidPlanError. It never silently
    ships an invalid plan as if it were valid.

    A shared orchestrator (with a process-wide circuit breaker) is injected so
    cross-request protection actually works.
    """

    def __init__(self, client: LLMClient, catalog: Catalog, orchestrator: TTLOrchestrator) -> None:
        self.client = client
        self.catalog = catalog
        self.orchestrator = orchestrator

    async def plan(self, request: PartyRequest) -> PlanResult:
        async def produce(i: int):
            temperature = 0.4 + 0.15 * i
            draft = await self.client.generate_draft(request, self.catalog, temperature=temperature)
            return ground_draft(draft, self.catalog, request.guest_count)

        def verify(plan):
            report = verify_plan(plan, request, self.catalog)
            return report.passed, report.score, report

        candidate, telemetry = await self.orchestrator.run_verified(produce, verify)
        report = candidate.detail

        if not candidate.passed:
            # Honest failure: do NOT present an invalid plan as shippable.
            min_budget = minimum_feasible_budget(request, self.catalog)
            binding = [v for v in report.violations if v.severity == "error"]
            raise NoValidPlanError(
                message="No plan could satisfy all constraints.",
                violations=[v.model_dump() for v in binding],
                minimum_feasible_budget=min_budget,
                telemetry=telemetry.as_dict(),
            )

        return PlanResult(
            status="verified",
            request=request,
            plan=candidate.value,
            verification=report,
            telemetry=telemetry.as_dict(),
            backend=self.client.name,
        )
