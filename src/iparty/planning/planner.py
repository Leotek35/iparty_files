"""TTLPartyPlanner — verifier-gated, TTL-orchestrated party planning."""
from __future__ import annotations

from ..core.logging import get_logger
from ..llm.client import LLMClient
from ..orchestration.ttl_engine import TTLOrchestrator
from .models import PartyPlan, PartyRequest, PlanResult
from .prompts import SYSTEM_PROMPT, build_user_prompt
from .verifier import verify_plan

logger = get_logger("planner")


class TTLPartyPlanner:
    """Generate a plan that is *guaranteed* (when possible) to pass verification.

    Pipeline per request:
      produce(i) -> LLM candidate plan (watchdog-wrapped, breaker-routed)
      verify     -> constraint verifier (objective gate)
      orchestrator returns the first passing candidate, else the best-scoring one.
    """

    def __init__(self, client: LLMClient) -> None:
        self.client = client
        self.orchestrator = TTLOrchestrator(name="party")

    async def plan(self, request: PartyRequest) -> PlanResult:
        system = SYSTEM_PROMPT
        user = build_user_prompt(request)

        async def produce(i: int) -> PartyPlan:
            # vary temperature slightly across candidates for diversity
            temperature = 0.4 + 0.15 * i
            return await self.client.generate_plan(system, user, request, temperature=temperature)

        def verify(plan: PartyPlan):
            report = verify_plan(plan, request)
            return report.passed, report.score, report

        candidate, telemetry = await self.orchestrator.run_verified(produce, verify)
        report = candidate.detail  # VerificationReport from verify()

        if not candidate.passed:
            logger.warning(
                f"No fully-valid plan for {request.honoree_name}; "
                f"returning best-effort (score {candidate.score:.2f})."
            )

        return PlanResult(
            request=request,
            plan=candidate.value,
            verification=report,
            telemetry=telemetry.as_dict(),
            backend=self.client.name,
        )
