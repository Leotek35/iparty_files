"""Application settings. Single source of truth, env-overridable.

Two LLM backends are supported: a deterministic offline `mock` (so the repo
runs with zero secrets and CI stays green) and `anthropic`.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "iParty"
    APP_VERSION: str = "1.0.0"
    ENV: Literal["dev", "prod", "test"] = "dev"

    LLM_BACKEND: Literal["mock", "anthropic"] = "mock"
    ANTHROPIC_API_KEY: str | None = None
    ANTHROPIC_MODEL: str = "claude-sonnet-4-6"
    ANTHROPIC_MAX_TOKENS: int = 2000

    # Circuit Breaker
    CB_FAILURE_THRESHOLD: int = Field(default=5, ge=1)
    CB_SUCCESS_THRESHOLD: int = Field(default=2, ge=1)
    CB_COOLDOWN_SECONDS: float = Field(default=30.0, gt=0)

    # Verifier-gated best-of-N (TMR analogue) + breaker
    PLAN_CANDIDATES_N: int = Field(default=4, ge=1, le=10)
    CB_CONSECUTIVE_FAILS: int = Field(default=3, ge=1)

    # Watchdog (graduated timeouts, malformed retry)
    SOFT_TIMEOUT_SECONDS: float = Field(default=20.0, gt=0)
    HARD_TIMEOUT_SECONDS: float = Field(default=40.0, gt=0)
    WATCHDOG_MAX_RETRIES: int = Field(default=1, ge=0)

    # Overall per-request wall-clock budget across ALL candidates/retries.
    REQUEST_DEADLINE_SECONDS: float = Field(default=90.0, gt=0)

    # JEPA-TTL bridge: predictive candidate budgeting, preemptive repair
    # hints, energy-based continuation, online learning from the verifier.
    JEPA_BRIDGE_ENABLED: bool = True

    # Verifier tolerances
    BUDGET_TOLERANCE: float = Field(default=0.0, ge=0, le=0.25)
    BUDGET_FLOOR_FRACTION: float = Field(default=0.25, ge=0, le=1)

    HOST: str = "0.0.0.0"
    PORT: int = Field(default=8000, ge=1, le=65535)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
