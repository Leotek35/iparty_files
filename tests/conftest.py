import os

os.environ["LLM_BACKEND"] = "mock"
os.environ["ENV"] = "test"

import pytest

from iparty.core.config import settings
from iparty.core.ratelimit import limiter


@pytest.fixture(autouse=True)
def _isolate_rate_limits():
    """Most tests should not be throttled. Reset buckets and lift limits high;
    tests that specifically exercise limits set their own low values."""
    limiter._buckets.clear()
    settings.PLAN_RATE_PER_MIN = 100_000
    settings.EVENTS_RATE_PER_MIN = 100_000
    yield
    limiter._buckets.clear()
