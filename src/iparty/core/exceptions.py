"""Exception hierarchy (app-scoped subset of the production foundation)."""
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
    """Raised when all retries/candidates are exhausted without success."""


class PlanGenerationError(IPartyError):
    pass


class MalformedPlanError(PlanGenerationError):
    """LLM returned output that could not be parsed into a PartyPlan."""


class NoValidPlanError(PlanGenerationError):
    """No candidate plan passed verification within the attempt budget."""
