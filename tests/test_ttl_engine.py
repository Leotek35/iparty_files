import asyncio

import pytest

from iparty.core.exceptions import CircuitBreakerOpenError, WatchdogTimeoutError
from iparty.orchestration.ttl_engine import CircuitBreaker, TTLOrchestrator, WatchdogTimer


@pytest.mark.asyncio
async def test_circuit_opens_after_threshold():
    cb = CircuitBreaker(name="t", failure_threshold=3, cooldown_seconds=10)

    async def boom():
        raise ValueError("nope")

    for _ in range(3):
        with pytest.raises(ValueError):
            await cb.call(boom)
    assert cb.state.value == "open"
    with pytest.raises(CircuitBreakerOpenError):
        await cb.call(boom)


@pytest.mark.asyncio
async def test_watchdog_times_out():
    wd = WatchdogTimer(name="t", hard_timeout=0.05, max_retries=0)

    async def slow():
        await asyncio.sleep(1.0)

    with pytest.raises(WatchdogTimeoutError):
        await wd.execute(slow)


@pytest.mark.asyncio
async def test_best_of_n_returns_first_pass():
    orch = TTLOrchestrator(name="t")
    calls = {"n": 0}

    async def produce(i):
        calls["n"] += 1
        return i

    def verify(v):
        # only candidate index 2 passes
        return (v == 2, 1.0 if v == 2 else 0.1, None)

    cand, tel = await orch.run_verified(produce, verify, n=5, consecutive_fail_limit=10)
    assert cand.passed and cand.value == 2
    assert tel.candidates_verified_pass == 1
    assert calls["n"] == 3  # stopped as soon as it passed
