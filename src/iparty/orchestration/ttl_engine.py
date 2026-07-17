"""TTL-inspired orchestration engine.

Hardware reliability patterns applied to LLM orchestration:

- CircuitBreaker  : fail fast after repeated failures (NAND-gate analogue),
                    auto-probe recovery after a cooldown (CLOSED/OPEN/HALF_OPEN).
- WatchdogTimer   : graduated soft/hard timeouts with bounded retries.
- verified_best_of_n : the planning-time realisation of TMR — generate N
                    candidates, gate each through a verifier, return the first
                    that passes; a consecutive-failure breaker bounds cost.
- TTLOrchestrator : composes the above and emits telemetry describing which
                    patterns fired (so the UI can render the reliability ledger).

This is a clean, dependency-light async implementation faithful to the
production foundation's CircuitState / TMR / Watchdog semantics.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Awaitable, Callable, Generic, TypeVar

from ..core.config import settings
from ..core.exceptions import (
    CircuitBreakerOpenError,
    RetryExhaustedError,
    WatchdogTimeoutError,
)
from ..core.logging import get_logger

logger = get_logger("ttl")

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Circuit Breaker
# ---------------------------------------------------------------------------
class CircuitState(str, Enum):
    CLOSED = "closed"       # normal
    OPEN = "open"           # rejecting fast
    HALF_OPEN = "half_open"  # probing recovery


class CircuitBreaker:
    def __init__(
        self,
        name: str = "default",
        failure_threshold: int | None = None,
        success_threshold: int | None = None,
        cooldown_seconds: float | None = None,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold or settings.CB_FAILURE_THRESHOLD
        self.success_threshold = success_threshold or settings.CB_SUCCESS_THRESHOLD
        self.cooldown_seconds = cooldown_seconds or settings.CB_COOLDOWN_SECONDS
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: float | None = None
        self.total_calls = 0
        self.total_failures = 0
        self._probe_in_flight = False  # HALF_OPEN admits exactly one probe

    def _should_attempt_reset(self) -> bool:
        return (
            self.last_failure_time is not None
            and (time.monotonic() - self.last_failure_time) >= self.cooldown_seconds
        )

    async def call(self, func: Callable[..., Awaitable[T]], *args, **kwargs) -> T:
        self.total_calls += 1
        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self.state = CircuitState.HALF_OPEN
                logger.info(f"[{self.name}] circuit HALF_OPEN (probing recovery)")
            else:
                raise CircuitBreakerOpenError(f"circuit '{self.name}' is OPEN")
        if self.state == CircuitState.HALF_OPEN:
            # Admit exactly ONE in-flight probe; reject the rest fast so a
            # recovering provider is not hammered by every queued request.
            if self._probe_in_flight:
                raise CircuitBreakerOpenError(
                    f"circuit '{self.name}' is HALF_OPEN (probe in flight)"
                )
            self._probe_in_flight = True
        try:
            result = await func(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            self._on_failure(exc)
            raise
        self._on_success()
        return result

    def _on_success(self) -> None:
        if self.state == CircuitState.HALF_OPEN:
            self._probe_in_flight = False
            self.success_count += 1
            if self.success_count >= self.success_threshold:
                self._close()
        else:
            self.failure_count = 0

    def _on_failure(self, exc: Exception) -> None:
        self.total_failures += 1
        self.last_failure_time = time.monotonic()
        if self.state == CircuitState.HALF_OPEN:
            self._probe_in_flight = False
            self._open()
            return
        self.failure_count += 1
        if self.failure_count >= self.failure_threshold:
            self._open()

    def _open(self) -> None:
        self.state = CircuitState.OPEN
        self.success_count = 0
        logger.warning(f"[{self.name}] circuit OPEN after {self.failure_count} failures")

    def _close(self) -> None:
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        logger.info(f"[{self.name}] circuit CLOSED (recovered)")

    def metrics(self) -> dict:
        return {
            "name": self.name,
            "state": self.state.value,
            "total_calls": self.total_calls,
            "total_failures": self.total_failures,
            "failure_count": self.failure_count,
        }


# ---------------------------------------------------------------------------
# Watchdog Timer
# ---------------------------------------------------------------------------
class WatchdogTimer:
    """Graduated timeout with bounded retries.

    soft_timeout : log a warning but keep waiting.
    hard_timeout : cancel the attempt and (optionally) retry.
    """

    def __init__(
        self,
        name: str = "default",
        soft_timeout: float | None = None,
        hard_timeout: float | None = None,
        max_retries: int | None = None,
    ) -> None:
        self.name = name
        self.soft_timeout = soft_timeout or settings.SOFT_TIMEOUT_SECONDS
        self.hard_timeout = hard_timeout or settings.HARD_TIMEOUT_SECONDS
        self.max_retries = settings.WATCHDOG_MAX_RETRIES if max_retries is None else max_retries
        self.retries_used = 0
        self.timeouts = 0

    async def execute(self, func: Callable[..., Awaitable[T]], *args, **kwargs) -> T:
        attempt = 0
        last_exc: Exception | None = None
        while attempt <= self.max_retries:
            try:
                return await asyncio.wait_for(func(*args, **kwargs), timeout=self.hard_timeout)
            except asyncio.TimeoutError:
                self.timeouts += 1
                last_exc = WatchdogTimeoutError(
                    f"watchdog '{self.name}' hard timeout ({self.hard_timeout}s)"
                )
                logger.warning(str(last_exc))
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
            attempt += 1
            if attempt <= self.max_retries:
                self.retries_used += 1
        assert last_exc is not None
        raise last_exc

    def metrics(self) -> dict:
        return {"name": self.name, "timeouts": self.timeouts, "retries_used": self.retries_used}


# ---------------------------------------------------------------------------
# Telemetry
# ---------------------------------------------------------------------------
@dataclass
class Telemetry:
    """Record of which TTL patterns fired during one orchestrated request."""

    candidates_generated: int = 0
    candidates_verified_pass: int = 0
    watchdog_retries: int = 0
    circuit_state: str = "closed"
    circuit_breaker_tripped: bool = False
    llm_calls: int = 0
    elapsed_seconds: float = 0.0
    pattern_log: list[str] = field(default_factory=list)
    # JEPA-TTL bridge (None when the bridge is disabled)
    jepa_enabled: bool = False
    jepa_difficulty: float | None = None
    jepa_candidate_budget: int | None = None
    jepa_energy_trace: list[dict] = field(default_factory=list)
    jepa_calibration: float | None = None
    jepa_examples_seen: int | None = None

    def event(self, msg: str) -> None:
        self.pattern_log.append(msg)

    def as_dict(self) -> dict:
        return {
            "candidates_generated": self.candidates_generated,
            "candidates_verified_pass": self.candidates_verified_pass,
            "watchdog_retries": self.watchdog_retries,
            "circuit_state": self.circuit_state,
            "circuit_breaker_tripped": self.circuit_breaker_tripped,
            "llm_calls": self.llm_calls,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
            "pattern_log": self.pattern_log,
            "jepa": {
                "enabled": self.jepa_enabled,
                "difficulty": self.jepa_difficulty,
                "candidate_budget": self.jepa_candidate_budget,
                "energy_trace": self.jepa_energy_trace,
                "calibration_accuracy": self.jepa_calibration,
                "examples_seen": self.jepa_examples_seen,
            },
        }


# ---------------------------------------------------------------------------
# Orchestrator — verifier-gated best-of-N (TMR) + breaker + watchdog
# ---------------------------------------------------------------------------
@dataclass
class Candidate(Generic[T]):
    value: T
    passed: bool
    score: float
    detail: object = None


class TTLOrchestrator:
    """Compose the patterns into one reliable call.

    `run_verified` generates up to N candidates via `produce` (each wrapped in
    the watchdog and routed through the circuit breaker), gates each through
    `verify`, and returns the first candidate that passes. A consecutive-failure
    breaker stops early to bound cost (the planning realisation of the circuit
    breaker). If none pass, the best-scoring candidate is returned, annotated.
    """

    def __init__(self, name: str = "main") -> None:
        self.name = name
        self.breaker = CircuitBreaker(name=f"{name}.cb")
        self.watchdog = WatchdogTimer(name=f"{name}.wd")

    async def run_verified(
        self,
        produce: Callable[[int], Awaitable[T]],
        verify: Callable[[T], "tuple[bool, float, object]"],
        n: int | None = None,
        consecutive_fail_limit: int | None = None,
        deadline_seconds: float | None = None,
        advisor: object | None = None,
    ) -> "tuple[Candidate[T], Telemetry]":
        n = n or settings.PLAN_CANDIDATES_N
        consecutive_fail_limit = consecutive_fail_limit or settings.CB_CONSECUTIVE_FAILS
        deadline = deadline_seconds or settings.REQUEST_DEADLINE_SECONDS
        tel = Telemetry()
        start = time.monotonic()
        best: Candidate[T] | None = None
        best_pass: Candidate[T] | None = None
        consecutive = 0

        # JEPA bridge: predicted difficulty sets the candidate budget BEFORE
        # any generation is spent (anticipatory, not reactive).
        if advisor is not None:
            difficulty = advisor.difficulty()
            n = advisor.candidate_budget(n)
            tel.jepa_enabled = True
            tel.jepa_difficulty = round(difficulty, 3)
            tel.jepa_candidate_budget = n
            tel.event(f"jepa: predicted difficulty {difficulty:.2f} -> candidate budget {n}")

        for i in range(n):
            if time.monotonic() - start >= deadline:
                tel.event(f"request deadline ({deadline:.0f}s) reached — stopping")
                break
            try:
                value = await self.breaker.call(self.watchdog.execute, produce, i)
            except CircuitBreakerOpenError:
                tel.circuit_breaker_tripped = True
                tel.event("circuit OPEN — stopped generating (fail fast)")
                break
            except WatchdogTimeoutError:
                tel.watchdog_retries = self.watchdog.retries_used
                tel.event(f"candidate {i}: watchdog timeout")
                consecutive += 1
                if consecutive >= consecutive_fail_limit:
                    tel.circuit_breaker_tripped = True
                    tel.event("consecutive-failure breaker tripped")
                    break
                continue
            except Exception as exc:  # noqa: BLE001
                # Provider/transport error on ONE candidate must not abort the
                # request: count it as a failed candidate and keep sampling.
                # (The breaker above has already recorded the failure.)
                tel.event(f"candidate {i}: produce error ({type(exc).__name__})")
                consecutive += 1
                if consecutive >= consecutive_fail_limit:
                    tel.circuit_breaker_tripped = True
                    tel.event("consecutive-failure breaker tripped")
                    break
                continue

            tel.candidates_generated += 1
            tel.llm_calls += 1

            predicted_energy: float | None = None
            if advisor is not None:
                predicted_energy = advisor.assess(value)

            passed, score, detail = verify(value)
            cand = Candidate(value=value, passed=passed, score=score, detail=detail)
            if best is None or score > best.score:
                best = cand

            if advisor is not None:
                advisor.observe(value, detail)
                if predicted_energy is not None:
                    verdict = "PASS" if passed else "FAIL"
                    tel.jepa_energy_trace.append({
                        "candidate": i,
                        "predicted_energy": round(predicted_energy, 3),
                        "verifier": verdict,
                        "score": round(score, 3),
                    })
                    tel.event(f"jepa: candidate {i} predicted energy "
                              f"{predicted_energy:.2f}, verifier says {verdict}")

            if passed:
                tel.candidates_verified_pass += 1
                tel.event(f"candidate {i}: verified PASS (score {score:.2f})")
                if best_pass is None or score > best_pass.score:
                    best_pass = cand
                if advisor is not None and advisor.should_continue(best_pass.score, i + 1, n):
                    tel.event(f"jepa: pass score {score:.2f} mediocre on a hard "
                              f"request — sampling for a better candidate")
                    consecutive = 0
                    continue
                tel.watchdog_retries = self.watchdog.retries_used
                tel.circuit_state = self.breaker.state.value
                tel.elapsed_seconds = time.monotonic() - start
                _stamp_jepa(tel, advisor)
                return best_pass, tel

            tel.event(f"candidate {i}: verify FAIL (score {score:.2f})")
            consecutive += 1
            if consecutive >= consecutive_fail_limit:
                tel.circuit_breaker_tripped = True
                tel.event("consecutive-failure breaker tripped (cost bound)")
                break

        tel.watchdog_retries = self.watchdog.retries_used
        tel.circuit_state = self.breaker.state.value
        tel.elapsed_seconds = time.monotonic() - start
        _stamp_jepa(tel, advisor)
        if best_pass is not None:
            return best_pass, tel
        if best is None:
            raise RetryExhaustedError("no candidate could be produced")
        return best, tel


def _stamp_jepa(tel: "Telemetry", advisor: object | None) -> None:
    """Copy the shared predictor's live self-assessment onto the telemetry so
    the UI can show how well the bridge is calibrated to this workload."""
    if advisor is None:
        return
    predictor = getattr(advisor, "predictor", None)
    if predictor is None:
        return
    m = predictor.metrics()
    tel.jepa_calibration = m.get("calibration_accuracy")
    tel.jepa_examples_seen = m.get("examples_seen")
