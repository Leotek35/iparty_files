"""LLM client protocol + Anthropic and Mock backends.

Backends return a PlanDraft (catalog SELECTIONS, never prices). The Mock is
offline and deterministic so the repo runs and CI passes with zero secrets.
"""
from __future__ import annotations

import json
import random
import re
from typing import Protocol

from ..core.config import settings
from ..core.exceptions import MalformedPlanError
from ..core.logging import get_logger
from ..pricing.catalog import Catalog
from ..planning.feasibility import cheapest_compliant_draft
from ..planning.models import PartyRequest, PlanDraft, Selection
from ..planning.prompts import SYSTEM_PROMPT, build_user_prompt

logger = get_logger("llm")


class LLMClient(Protocol):
    name: str

    async def generate_draft(
        self, request: PartyRequest, catalog: Catalog,
        temperature: float = 0.5, feedback: "str | None" = None,
    ) -> PlanDraft: ...


def _parse_draft_json(text: str) -> PlanDraft:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise MalformedPlanError("no JSON object found in model output")
    try:
        return PlanDraft.model_validate(json.loads(match.group(0)))
    except Exception as exc:  # noqa: BLE001
        raise MalformedPlanError(f"could not parse draft: {exc}") from exc


class AnthropicClient:
    name = "anthropic"

    def __init__(self) -> None:
        from anthropic import AsyncAnthropic

        if not settings.ANTHROPIC_API_KEY:
            raise RuntimeError("ANTHROPIC_API_KEY not set but LLM_BACKEND=anthropic")
        self._client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        self._model = settings.ANTHROPIC_MODEL

    async def generate_draft(self, request, catalog, temperature=0.5, feedback=None) -> PlanDraft:
        user = build_user_prompt(request, catalog)
        if feedback:
            user += ("\n\nIMPORTANT — your previous selection failed verification:\n"
                     + feedback + "\nReturn a corrected JSON selection.")
        resp = await self._client.messages.create(
            model=self._model, max_tokens=settings.ANTHROPIC_MAX_TOKENS,
            temperature=min(1.0, temperature), system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(b.text for b in resp.content if b.type == "text")
        return _parse_draft_json(text)


class MockClient:
    """Offline planner. Starts from the cheapest compliant draft, then sometimes
    upgrades items (and occasionally overshoots budget) to exercise the verifier
    and the best-of-N / circuit-breaker path."""

    name = "mock"

    def __init__(self, seed: int = 0, flaw_rate: float = 0.35) -> None:
        self._seed = seed
        self._flaw_rate = flaw_rate
        self._call = 0

    async def generate_draft(self, request, catalog, temperature=0.5, feedback=None) -> PlanDraft:
        self._call += 1
        rng = random.Random(
            hash((request.honoree_name, request.guest_count, self._seed, self._call)) & 0xFFFFFFFF
        )
        base = cheapest_compliant_draft(request, catalog)
        if base is None:
            # Even the floor is impossible (e.g. no age-appropriate activity) -> empty draft
            return PlanDraft(theme=request.theme or "Party", venue_sku="VEN-HOME")

        theme = request.theme or rng.choice(
            ["Dinosaurs", "Space Explorers", "Under the Sea", "Superheroes", "Rainbow Magic"]
        )
        base = base.model_copy(update={"theme": theme})

        # Verifier-guided repair: with concrete feedback, the mock (like a real
        # model told exactly what to fix) returns the compliant base plan.
        if feedback:
            return base

        flawed = rng.random() < self._flaw_rate
        if not flawed:
            # Optionally upgrade one activity if budget clearly allows (kept simple/safe).
            nicer = [a for a in catalog.by_category("activities")
                     if a.min_age <= request.honoree_age <= a.max_age]
            if nicer and rng.random() < 0.5:
                pick = rng.choice(nicer)
                base = base.model_copy(update={"activities": [Selection(sku=pick.sku, quantity=1)]})
            return base

        # Flawed candidate: blow the budget with an expensive add-on (verifier rejects).
        expensive = max(catalog.by_category("activities"), key=lambda i: i.price_for(1, request.guest_count))
        return base.model_copy(update={
            "activities": base.activities + [Selection(sku=expensive.sku, quantity=2)],
        })


def build_client() -> LLMClient:
    if settings.LLM_BACKEND == "anthropic":
        logger.info("Using Anthropic backend")
        return AnthropicClient()
    logger.info("Using Mock backend (offline)")
    return MockClient()
