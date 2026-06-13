"""Exception hierarchy (app-scoped)."""
from __future__ import annotations


class IPartyError(Exception):
    """Base for all iParty errors."""


class AgentExecutionError(IPartyError):
    pass


class CircuitBreakerOpenError(AgentExecutionError):
    """Raised when the circuit is OPEN and a call is rejected fast."""


class WatchdogTimeoutError(AgentExecutionError):
    """Raised when a call exceeds the hard timeout."""


class RetryExhaustedError(AgentExecutionError):
    """Raised when all retries/candidates are exhausted without a candidate."""


class PlanGenerationError(IPartyError):
    pass


class MalformedPlanError(PlanGenerationError):
    """LLM returned output that could not be parsed into a draft."""


class NoValidPlanError(PlanGenerationError):
    """No candidate passed verification. Carries the binding constraints and the
    minimum feasible budget so the caller can respond honestly."""

    def __init__(self, message: str, violations: list | None = None,
                 minimum_feasible_budget: float | None = None,
                 telemetry: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.violations = violations or []
        self.minimum_feasible_budget = minimum_feasible_budget
        self.telemetry = telemetry or {}
